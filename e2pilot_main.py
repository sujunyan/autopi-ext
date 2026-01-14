import json
import logging
import threading
import time
from pathlib import Path
import argparse

import csv
import can
import j1939
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from display_manager import DisplayManager
from h11_listener import H11Listener
from embed_acc_listener import EmbedAccListener
from embed_gps_listener import EmbedGpsListener
from logger import config_logger, logger
from j1939Listener import J1939Listener
from obd2_listener import Obd2Listener
from uds_listener import UdsListener
from route_matcher import RouteMatcher
from utils import haversine
import route_matcher

# Configure logging for j1939 and can libraries
logging.getLogger("j1939").setLevel(logging.DEBUG)
logging.getLogger("can").setLevel(logging.DEBUG)

# USE_1939 = True
# Use location simulation mode


class E2PilotAutopi:
    def __init__(self, virtual_sim_mode=False, obd_mode="UDS"):
        self.obd_mode = obd_mode
        if self.obd_mode == "J1939":
            self.obd_listener = J1939Listener()
        elif self.obd_mode == "OBD2":
            self.obd_listener = Obd2Listener()
        elif self.obd_mode == "UDS":
            self.obd_listener = UdsListener()
       

        # If true, we will simulate by publishing virtual location messages on mqtt
        self.virtual_sim_mode = VIRTUAL_SIMULATION_MODE
        if self.virtual_sim_mode:
            logger.info("Using virtual simulation mode for location...")

        self.mqtt_broker = "localhost"
        self.mqtt_port = 1883

        self.display_manager = DisplayManager()
        self.h11_listener = H11Listener(mqtt_broker=self.mqtt_broker)
        self.embed_acc_listener = EmbedAccListener(mqtt_broker=self.mqtt_broker)
        self.embed_gps_listener = EmbedGpsListener(mqtt_broker=self.mqtt_broker)
        self.route_matcher = RouteMatcher()
        self.trip_distance = 0.0
        self.veh_trip_distance = 0.0
        self.init_vehicle_distance = None
        self.follow_range = 0.0
        self.follow_rate = 0.0

    def setup(self):
        # heartbeat related threshold
        self.update_time_threshold = 3.0
        self.last_obd_speed_time = time.time()
        self.last_h11_location_time = time.time()
        self.last_embed_gps_time = time.time()
        self.last_heart_beat_time = time.time()
        self.heart_beat_delta = 1.0
        self.last_publish_virtual_location_time = time.time()

        self.current_speed = -1
        self.suggest_speed = -10
        # The tolerance for following suggested speed
        self.suggest_speed_tol = 5
        self.grade = 0.0
        self.lat = None; self.lon = None
        self.last_lat = None; self.last_lon = None
        self.last_trip_distance = 0.0
        self.gps_total_distance_m = 0.0
        self.min_move_threshold_m = 10.0  # Minimum movement to consider for distance tracking
        self.max_move_threshold_m = 1000_000.0  # Maximum movement to consider for distance tracking, I guess there is no tunnel with 1000km long...


        self.obd_listener.setup()
        self.display_manager.setup(); 
        # logger.warning("Disable display manager and OBD listener.")
        self.setup_mqtt_speed_client()
        self.setup_mqtt_location_client()
        self.setup_mqtt_distance_client()

        if not self.virtual_sim_mode:
            self.h11_listener.setup()
            self.embed_gps_listener.setup()

        self.embed_acc_listener.setup()
       
        if self.virtual_sim_mode:
            route_name = route_matcher.route_name_subset[-1]
            self.route_matcher.load_route_from_json(route_name)

    def loop_start(self):
        self.obd_listener.loop_start()
        self.h11_listener.loop_start()
        self.embed_acc_listener.loop_start()
        self.embed_gps_listener.loop_start()

    def main_loop(self):
        self.loop_start()
        while True:
            if (time.time() - self.last_heart_beat_time) > self.heart_beat_delta:
                logger.info("Heartbeat msg..........................................")
                logger.info(f"Current state: speed: {self.current_speed:.2f}km/h, suggest speed: {self.suggest_speed:.2f}km/h, grade: {self.grade:.2f}%, trip distance: {self.trip_distance:.3f}km, follow range: {self.follow_range:.3f}km, follow rate: {self.follow_rate*100:.2f}%, ipt: {self.route_matcher.current_pt_index}, projection dist {self.route_matcher.projection_dist:.2f}m")
                if self.lat != None and self.lon != None:
                    logger.info(f"latlon: ({self.lat:.6f}, {self.lon:.6f})")
                self.last_heart_beat_time = time.time()
            if self.virtual_sim_mode:
                self.publish_virtual_location()

            # Slow down and filter the heartbeat msg
            if not self.virtual_sim_mode:
                if self.current_speed < 1.0:
                    self.heart_beat_delta = 10
                elif self.current_speed < 5.0:
                    self.heart_beat_delta = 5
                else:
                    self.heart_beat_delta = 2

            time.sleep(0.1)

    def close(self):
        for ls in [
            self.obd_listener,
            self.h11_listener,
            self.embed_acc_listener,
            self.embed_gps_listener,
        ]:
            if ls:
                ls.close()

        for client in [
            self.mqtt_distance_client,
            self.mqtt_speed_client,
            self.mqtt_location_client,
            
        ]:
            if client:
                client.loop_stop()
                client.disconnect()

        self.display_manager.close()

    def is_h11_alive(self):
        if self.h11_listener.enable == False:
            return False

        flag = (time.time() - self.last_h11_location_time) < self.update_time_threshold
        return flag

    def is_obd_alive(self):
        if self.obd_listener.enable == False:
            return False
        flag = (time.time() - self.last_obd_speed_time) < self.update_time_threshold
        return flag

    def on_speed_message(self, client, userdata, msg):
        payload = msg.payload.decode()
        data = json.loads(payload)  # Parse JSON payload

        if msg.topic == "j1939/Wheel-Based_Vehicle_Speed":
            speed = data["value"]
            self.current_speed = speed
            self.last_obd_speed_time = time.time()
        elif msg.topic == "obd2/speed":
            self.current_speed = data["value"]
            logger.debug(f"Got speed from obd2/speed: {self.current_speed}")
            self.last_obd_speed_time = time.time()
        elif msg.topic == "uds/speed":
            self.current_speed = data["value"]
            self.last_obd_speed_time = time.time()
        elif msg.topic == "h11gps/speed":
            speed = data["speed_kmh"]
            if not self.is_obd_alive():
                logger.debug(
                    f"OBD might not be alive, got speed from h11gps: {self.current_speed}"
                )
                self.current_speed = speed

        self.display_manager.set_speed(self.current_speed)

    def setup_mqtt_speed_client(self):
        self.mqtt_speed_client = mqtt.Client(CallbackAPIVersion.VERSION2)
        self.mqtt_speed_client.on_message = self.on_speed_message
        self.mqtt_speed_client.connect(self.mqtt_broker, self.mqtt_port)
        self.mqtt_speed_client.subscribe(
            [
                ("j1939/Wheel-Based_Vehicle_Speed", 0),
                ("obd2/speed", 0),
                ("h11gps/speed", 0),
                ("uds/speed", 0)
            ]
        )
        # Start the MQTT client loop in the background
        self.mqtt_speed_client.loop_start()

    def setup_mqtt_distance_client(self):
        self.mqtt_distance_client = mqtt.Client(CallbackAPIVersion.VERSION2)
        self.mqtt_distance_client.on_message = self.on_distance_message
        self.mqtt_distance_client.connect(self.mqtt_broker, self.mqtt_port)
        self.mqtt_distance_client.subscribe(
            [
                ("j1939/High_Resolution_Total_Vehicle_Distance", 0),
                ("j1939/Total_Vehicle_Distance", 0),
                ("obd2/distance_since_dtc_clear", 0),
                ("gps/distance", 0),
                ("sim/distance", 0)
            ]
        )
        # Start the MQTT client loop in the background
        self.mqtt_distance_client.loop_start()

    def on_distance_message(self, client, userdata, msg):
        payload = msg.payload.decode()
        data = json.loads(payload)
        if self.virtual_sim_mode:
            # In virtual simulation mode, we manually set distance...
            if msg.topic == "sim/distance":
                self.trip_distance = data["total_distance_m"] / 1000.0
            else:
                return
        else:
            ## distance in km
            if msg.topic == "j1939/High_Resolution_Total_Vehicle_Distance":
                self.hr_vehicle_distance = data["value"] / 1000.0
                self.vehicle_distance = self.hr_vehicle_distance
            elif msg.topic == "j1939/Total_Vehicle_Distance" and not hasattr(
                self, "hr_vehicle_distance"
            ):
                self.vehicle_distance = data["value"]
            elif msg.topic == "obd/distance_since_dtc_clear":
                self.vehicle_distance = data["value"]

            if self.init_vehicle_distance == None and hasattr(self, 'vehicle_distance'):
                self.init_vehicle_distance = self.vehicle_distance
                logger.info(f"Setting init vehicle distance {self.init_vehicle_distance}...")

            if msg.topic == "gps/distance" and "total_distance_m" in data:
                self.trip_distance = data["total_distance_m"] / 1000.0
            elif not self.is_h11_alive() and hasattr(self, "vehicle_distance"):
                self.veh_trip_distance = self.vehicle_distance - self.init_vehicle_distance

        logger.debug(f"Got trip distance: {self.trip_distance:.3f}")

        if self.last_trip_distance != 0.0:
            delta_d = self.trip_distance - self.last_trip_distance
            if delta_d > 0 and self.is_within_suggest_speed():
                self.follow_range += delta_d
                # self.display_manager.set_follow_range(self.follow_range)
                logger.debug(f"Got follow range {self.follow_range:.3f}")

            # Do not compute follow rate at the beginning
            if self.trip_distance > 0.1:
                self.follow_rate = (
                    (1.0 * self.follow_range) / self.trip_distance
                    if self.trip_distance > 0
                    else 0.0
                )
                self.display_manager.set_follow_rate(self.follow_rate * 100)

        self.last_trip_distance = self.trip_distance
        self.display_manager.set_distance(self.trip_distance)

    def on_location_message(self, client, userdata, msg):
        payload = msg.payload.decode()
        data = json.loads(payload)
        if self.virtual_sim_mode:
            if msg.topic == "sim/position":
                self.lat = data["lat"]
                self.lon = data["lon"]
            else:
                return
        else:
            if msg.topic == "h11gps/position":
                self.last_h11_location_time = time.time()
                if data["lat"] != 0 and data["lon"] != 0:
                    self.lat = data["lat"]
                    self.lon = data["lon"]
            elif msg.topic == "track/pos":
                self.last_embed_gps_time = time.time()
                if not self.is_h11_alive():
                    pos_data = data.get("loc", {})
                    self.lat = pos_data.get("lat", self.lat)
                    self.lon = pos_data.get("lon", self.lon)

        if self.last_lat is not None and self.last_lon is not None:
            dist = haversine(self.lat, self.lon, self.last_lat, self.last_lon)
            if dist > self.min_move_threshold_m and dist < self.max_move_threshold_m:
                self.gps_total_distance_m += dist
                self.last_lat = self.lat
                self.last_lon = self.lon
            logger.debug(f"Update delta_dis: {dist:.3f}, latlon: ({self.lat:.8f}, {self.lon:.8f})")
        else:
            self.last_lat = self.lat
            self.last_lon = self.lon

        if not self.route_matcher.route_selected and self.lat is not None and self.lon is not None:
            self.route_matcher.select_closest_route(self.lat, self.lon)
        
        self.mqtt_distance_client.publish(
            "gps/distance",
            json.dumps({"total_distance_m": self.gps_total_distance_m})
        )
            
        pt = self.route_matcher.update_pt(self.lat, self.lon)

        sug_spd, g = self.route_matcher.get_suggest_speed_and_grade()
        if sug_spd >= 0:
            sug_spd = sug_spd * 3.6
            self.suggest_speed = sug_spd
            self.display_manager.set_suggest_speed(sug_spd)

        self.grade = g * 100
        self.display_manager.set_grade(self.grade)
            
    def is_within_suggest_speed(self):
        if self.suggest_speed < 0:
            return False
        if self.current_speed < 0:
            return False

        if abs(self.current_speed - self.suggest_speed) <= self.suggest_speed_tol:
            return True
        return False

    def setup_mqtt_location_client(self):
        self.mqtt_location_client = mqtt.Client(CallbackAPIVersion.VERSION2)
        self.mqtt_location_client.on_message = self.on_location_message
        self.mqtt_location_client.connect(self.mqtt_broker, self.mqtt_port)
        self.mqtt_location_client.subscribe(
            [
                ("h11gps/position", 0),  # provided by h11_listener
                ("track/pos", 0),  # provided by track_manager inside autopi
                ("sim/position", 0) # virtual location for simulation
            ]
        )
        self.mqtt_location_client.loop_start()

    def publish_virtual_location(self):
        if (time.time() - self.last_publish_virtual_location_time) < 0.2:
            return

        idx = self.route_matcher.current_pt_index
        if idx == -1:
            idx = 0
            self.route_matcher.current_pt_index = 0

        pt1 = self.route_matcher.all_speedplan_points[idx]
        pt2 = self.route_matcher.get_next_speedplan_point()
        lat1 = pt1.get("lat", 0.0)
        lon1 = pt1.get("lon", 0.0)
        lat2 = pt2.get("lat", 0.0)
        lon2 = pt2.get("lon", 0.0)
        if self.lat == None or self.lon == None:
            self.lat, self.lon = lat1, lon1

        increment = 0.20
        next_lat = self.lat + (lat2 - lat1) * increment
        next_lon = self.lon + (lon2 - lon1) * increment
        delta_dis = haversine(self.lat, self.lon, next_lat, next_lon)
        if delta_dis < 1e-6:
            logger.warning("Got duplicate point, force moving forward")
            self.route_matcher.current_pt_index += 1
            return
        logger.debug(f"Update delta_dis: {delta_dis:.3f}, latlon: ({self.lat:.8f}, {self.lon:.8f}), next latlon {next_lat:.8f}, {next_lon:.8f}")
        self.lat = next_lat
        self.lon = next_lon

        distance = self.trip_distance * 1000.0 + delta_dis

        self.mqtt_location_client.publish(
            "sim/position",
            json.dumps({
                    "lat": self.lat,
                    "lon": self.lon,
                }),
        )
        self.mqtt_location_client.publish(
            "sim/distance",
            json.dumps({"total_distance_m": distance})
        )

        self.last_publish_virtual_location_time = time.time()


def parse_args():
    parser = argparse.ArgumentParser(description="E2PilotAutopi Main")
    parser.add_argument("--obd_mode", choices=["J1939", "OBD2", "UDS"], default="UDS", help="OBD mode to use")
    parser.add_argument("--virtual_sim_mode", action="store_true", help="Enable virtual simulation mode")
    parser.add_argument("--no-virtual_sim_mode", dest="virtual_sim_mode", action="store_false", help="Disable virtual simulation mode")
    parser.set_defaults(virtual_sim_mode=False)
    return parser.parse_args()

def main():
    args = parse_args()
    # OBD_MODE = args.obd_mode
    # VIRTUAL_SIMULATION_MODE = args.virtual_sim_mode
    # VIRTUAL_SIMULATION_MODE = True
    # OBD_MODE = ["J1939", "OBD2", "UDS"][2]

    if VIRTUAL_SIMULATION_MODE:
        config_logger(logging.INFO)
    else:
        config_logger(logging.INFO)


    logger.info("-----------------------------------------------")
    logger.info("-----------------------------------------------")
    logger.info("E2Pilot application with args: " + str(args))

    app = None
    try:
        app = E2PilotAutopi(virtual_sim_mode=args.virtual_sim_mode, obd_mode=args.obd_mode)
        app.setup()
        app.main_loop()
    except can.exceptions.CanError as e:
        logger.error(f"CAN bus error: {e}", exc_info=True)
    except KeyboardInterrupt:
        logger.info("E2Pilot Application stopped by user.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        time.sleep(5)
    finally:
        if app:
            app.close()
        logger.info("Application exit successfully.")


if __name__ == "__main__":
    main()

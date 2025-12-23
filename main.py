import json
import logging
import threading
import time
from pathlib import Path

import csv
import can
import j1939
import paho.mqtt.client as mqtt

from display_manager import DisplayManager
from h11_listener import H11Listener
from embed_gps_listener import EmbedGpsListener
from logger import config_logger, logger
from j1939Listener import J1939Listener
from obd2_listener import Obd2Listener
from route_matcher import RouteMatcher
from utils import haversine

# Configure logging for j1939 and can libraries
logging.getLogger("j1939").setLevel(logging.DEBUG)
logging.getLogger("can").setLevel(logging.DEBUG)

USE_1939 = True
route_name = [
    "test.2025-07-04.opt.JuMP.route.json",
    "20251222_waichen_in.opt.JuMP.route.json",   # from outside to back to waichen
    "20251222_waichen_out.opt.JuMP.route.json", # from waichen to go outside
][1]


class E2PilotAutopi:
    def __init__(self):
        self.use_1939 = USE_1939
        if self.use_1939:
            self.obd_listener = J1939Listener()
        else:
            self.obd_listener = Obd2Listener()

        self.mqtt_broker = "localhost"
        self.mqtt_port = 1883

        self.display_manager = DisplayManager()
        self.h11_listener = H11Listener(mqtt_broker=self.mqtt_broker)
        self.embed_gps_listener = EmbedGpsListener(mqtt_broker=self.mqtt_broker)
        self.route_matcher = RouteMatcher()
        self.trip_distance = 0.0
        self.init_vehicle_distance = -1
        self.follow_range = 0.0
        self.follow_rate = 0.0

    def setup(self):
        self.obd_listener.setup()
        self.display_manager.setup()
        self.setup_mqtt_speed_client()
        self.setup_mqtt_location_client()
        self.setup_mqtt_distance_client()

        self.h11_listener.setup()
        self.embed_gps_listener.setup()

        # heartbeat related threshold
        self.update_time_threshold = 3.0
        self.last_obd_speed_time = time.time()
        self.last_h11_location_time = time.time()
        self.last_embed_gps_time = time.time()
        self.last_heart_beat_time = time.time()

        self.current_speed = -1
        self.suggest_speed = -10
        # The tolerance for following suggested speed
        self.suggest_speed_tol = 5
        self.lat = -1
        self.lon = -1

        self.route_matcher.load_route_from_json(route_name)

    def loop_start(self):
        self.obd_listener.loop_start()
        self.h11_listener.loop_start()
        self.embed_gps_listener.loop_start()

    def main_loop(self):
        self.loop_start()
        while True:
            if (time.time() - self.last_heart_beat_time) > 10.0:
                logger.info("Heartbeat msg...")
                self.last_heart_beat_time = time.time()
            time.sleep(0.5)

    def close(self):
        for ls in [
            self.obd_listener,
            self.h11_listener,
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

    def is_h11_alive(self):
        if self.h11_listener.enable == False:
            return False

        flag = (time.time() - self.last_h11_location_time) < self.update_time_threshold
        return flag

    def is_obd_alive(self):
        flag = (time.time() - self.last_obd_speed_time) < self.update_time_threshold
        return flag

    def on_speed_message(self, client, userdata, msg):
        payload = msg.payload.decode()
        data = json.loads(payload)  # Parse JSON payload

        if msg.topic == "j1939/Wheel-Based_Vehicle_Speed":
            speed = data["value"]
            self.current_speed = speed
            self.last_obd_speed_time = time.time()
        elif msg.topic == "obd/speed":
            self.current_speed = data["value"]
            logger.debug(f"Got speed from obd/speed: {self.current_speed}")
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
        self.mqtt_speed_client = mqtt.Client()
        self.mqtt_speed_client.on_message = self.on_speed_message
        self.mqtt_speed_client.connect(self.mqtt_broker, self.mqtt_port)
        self.mqtt_speed_client.subscribe(
            [
                ("j1939/Wheel-Based_Vehicle_Speed", 0),
                ("obd/speed", 0),
                ("h11gps/speed", 0),
            ]
        )
        # Start the MQTT client loop in the background
        self.mqtt_speed_client.loop_start()

    def setup_mqtt_distance_client(self):
        self.mqtt_distance_client = mqtt.Client()
        self.mqtt_distance_client.on_message = self.on_distance_message
        self.mqtt_distance_client.connect(self.mqtt_broker, self.mqtt_port)
        self.mqtt_distance_client.subscribe(
            [
                ("j1939/High_Resolution_Total_Vehicle_Distance", 0),
                ("j1939/Total_Vehicle_Distance", 0),
                ("obd/distance_since_dtc_clear", 0),
                ("h11gps/distance", 0),
            ]
        )
        # Start the MQTT client loop in the background
        self.mqtt_distance_client.loop_start()

    def on_distance_message(self, client, userdata, msg):
        payload = msg.payload.decode()
        data = json.loads(payload)
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

        if self.init_vehicle_distance == -1 and hasattr(self, 'vehicle_distance'):
            self.init_vehicle_distance = self.vehicle_distance

        if msg.topic == "h11gps/distance" and "total_distance_m" in data:
            self.trip_distance = data["total_distance_m"] / 1000.0
        elif not self.is_h11_alive():
            self.trip_distance = self.vehicle_distance - self.init_vehicle_distance
        logger.debug(f"Got trip distance: {self.trip_distance}")

        self.last_trip_distance = self.trip_distance

        if self.last_trip_distance != 0.0:
            delta_d = self.trip_distance - self.last_trip_distance
            if delta_d > 0 and self.is_within_suggest_speed():
                self.follow_range += delta_d
                self.follow_rate = (
                    (1.0 * self.follow_range) / self.trip_distance
                    if self.trip_distance > 0
                    else 0.0
                )
                self.display_manager.set_follow_rate(self.follow_rate * 100)
                self.display_manager.set_follow_range(self.follow_range)

        self.display_manager.set_distance(self.trip_distance)

    def on_location_message(self, client, userdata, msg):
        payload = msg.payload.decode()
        data = json.loads(payload)
        if msg.topic == "h11gps/position":
            self.last_h11_location_time = time.time()
            self.lat = data["lat"]
            self.lon = data["lon"]
        elif msg.topic == "track/pos":
            self.last_embed_gps_time = time.time()
            if not self.is_h11_alive():
                pos_data = data.get("loc", {})
                self.lat = pos_data.get("lat", self.lat)
                self.lon = pos_data.get("lon", self.lon)

        pt = self.route_matcher.update_pt(self.lat, self.lon)

        if pt != None:
            sug_spd = pt.get("veh_state", {}).get("speed", -1)
            self.suggest_speed = sug_spd
            self.display_manager.set_suggest_speed(sug_spd)
        else:
            logger.warn("Got an empty point in the speed plan...")

    def is_within_suggest_speed(self):
        if self.suggest_speed < 0:
            return False
        if self.current_speed < 0:
            return False

        if abs(self.current_speed - self.suggest_speed) <= self.suggest_speed_tol:
            return True
        return False

    def setup_mqtt_location_client(self):
        self.mqtt_location_client = mqtt.Client()
        self.mqtt_location_client.on_message = self.on_location_message
        self.mqtt_location_client.connect(self.mqtt_broker, self.mqtt_port)
        self.mqtt_location_client.subscribe(
            [
                ("h11gps/position", 0),  # provided by h11_listener
                ("track/pos", 0),  # provided by track_manager inside autopi
            ]
        )
        self.mqtt_location_client.loop_start()


def main():
    config_logger(logging.DEBUG)

    logger.info("-----------------------------------------------")
    logger.info("-----------------------------------------------")
    logger.info("Initializing E2Pilot Application")

    app = None
    try:
        app = E2PilotAutopi()
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

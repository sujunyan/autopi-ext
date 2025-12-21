import logging
import time
import can
import j1939
from logger import config_logger, logger
from j1939Listener import J1939Listener 
import paho.mqtt.client as mqtt
from display_manager import DisplayManager
from h11_listener import H11Listener
from route_matcher import RouteMatcher
import json
import threading

# Configure logging for j1939 and can libraries
logging.getLogger('j1939').setLevel(logging.DEBUG)
logging.getLogger('can').setLevel(logging.DEBUG)

USE_1939 = False

class E2PilotAutopi:
    def __init__(self):
        self.use_1939 = USE_1939
        if self.use_1939:
            self.j1939_listener = J1939Listener()

        
        self.mqtt_broker = "localhost"
        self.mqtt_port = 1883

        self.display_manager = DisplayManager()
        self.h11_listener = H11Listener(mqtt_broker=self.mqtt_broker)
        self.route_matcher = RouteMatcher()
    
    def setup(self):
        if self.use_1939:
            self.j1939_listener.setup()

        self.display_manager.setup()
        self.setup_mqtt_speed_client()

        self.h11_listener.setup()

        self.last_obd_speed_time = time.time()

        if self.use_1939:
            ## Note that CAN interface might need some time to setup...
            self.j1939_listener.scan_pgns()

        self.current_speed = -1
        self.route_matcher.load_route_from_json("test.2025-07-04.opt.JuMP.route.json")

    def loop_start(self):
        if self.use_1939:
            self.j1939_listener.loop_start()
        self.h11_listener.loop_start()
        
            
    def main_loop(self):
        self.loop_start()
        while True:
            time.sleep(0.1)

    def close(self):
        if self.use_1939:
            self.j1939_listener.close()
        if self.mqtt_speed_client:
            self.mqtt_speed_client.loop_stop()
            self.mqtt_speed_client.disconnect()
        if self.h11_listener:
            self.h11_listener.close()
        

    def is_obd_alive(self):
        update_time_threshold = 2.0
        flag = (time.time() - self.last_obd_speed_time) < update_time_threshold
        

        
    def on_speed_message(self, client, userdata, msg):

        payload = msg.payload.decode()
        data = json.loads(payload)  # Parse JSON payload

        if msg.topic == "j1939/Wheel-Based_Vehicle_Speed":
            speed = data['value']
            self.current_speed = speed
            self.last_obd_speed_time = time.time()
        elif msg.topic == "obd/SPEED":
            self.last_obd_speed_time = time.time()
        elif msg.topic == "h11gps/speed":
            speed = data['speed_kmh']
            if not self.is_obd_alive():
                self.current_speed = speed
            
            # self.current_speed = speed
            # print(self.current_speed)
            # logger.debug(f"Received h11gps speed: {speed} km/h")

        self.display_manager.set_speed(self.current_speed)

    def setup_mqtt_speed_client(self):
        self.mqtt_speed_client = mqtt.Client()
        self.mqtt_speed_client.on_message = self.on_speed_message
        self.mqtt_speed_client.connect(self.mqtt_broker, self.mqtt_port)
        self.mqtt_speed_client.subscribe([
            ("j1939/Wheel-Based_Vehicle_Speed", 0),
            ("obd/SPEED", 0),
            ("h11gps/speed", 0)
        ])
        # Start the MQTT client loop in the background
        self.mqtt_speed_client.loop_start()

def main():
    config_logger(logging.DEBUG)

    logger.info("Initializing J1939 Controller Application")

    # compose the name descriptor for the new ca
    
    try:
        app = E2PilotAutopi()
        app.setup()
        app.main_loop()
        # j1939_listener = J1939Listener()    
        # j1939_listener.setup()
        # j1939_listener.main_loop()
    except can.exceptions.CanError as e:
        logger.error(f"CAN bus error: {e}", exc_info=True)
        # logger.info("Retrying connection in 5 seconds...")
        # time.sleep(5)
    except KeyboardInterrupt:
        logger.info("J1939 Controller Application stopped by user.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        # logger.info("Restarting J1939 Controller Application in 5 seconds...")
        time.sleep(5)
    finally:
        if 'app' in locals():
            app.close()
        logger.info("J1939 Controller Application deinitialized.")

if __name__ == '__main__':
    main()

# Example Usage of J1939Parser (for testing purposes, can be removed later)


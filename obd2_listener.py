import subprocess
import paho.mqtt.client as mqtt
import json, time, threading, os, logging, csv
from datetime import datetime
from pathlib import Path
import autopi

logger = logging.getLogger("e2pilot_autopi")

current_dir = Path(__file__).resolve().parent
data_dir = current_dir.joinpath("data/obd")

class Obd2Listener:
    def __init__(self):
        self.enable = False

    def setup(self):
        self.enable = True

        # MQTT settings
        self.mqtt_broker = 'localhost'
        self.mqtt_port = 1883
        self.mqtt_client = mqtt.Client()
        self.mqtt_topic = 'obd2/'
        # Connect to the MQTT broker
        try:
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port)
            logger.info("Connected to MQTT broker.")
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")

    def loop_start(self):
        self.thread = threading.Thread(target=self.main_loop, daemon=True)
        self.thread.start()

    def main_loop(self):
        if not self.enable:
            logger.warn("Obd2Listener is not enabled. Call setup() first.")
            return

        cmd_list = [
            'SPEED',
            'DISTANCE_SINCE_DTC_CLEAR',
        ]

        while self.enable:
            for cmd in cmd_list:
                res = self.query_obd2(cmd)


    def query_obd2(self, command):
        try:
            response = autopi.obd.execute(['obd.query', command])
            return response
        except Exception as e:
            logger.error(f"Error querying OBD2 command {command}: {e}")
            return None

    def close(self):
        self.enable = False
        time.sleep(1)
        logger.info("Obd2Listener stopped.")


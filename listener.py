import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

logger = logging.getLogger("e2pilot_autopi")

class Listener:
    """
    Base class for sensor listeners.
    Provides common functionality for threading, MQTT communication, and data logging.
    """

    def __init__(self, name: str, mqtt_broker: str = "localhost", mqtt_port: int = 1883):
        self.name = name
        self.enable = False
        self.thread = None
        
        # MQTT Configuration
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.mqtt_client = mqtt.Client(CallbackAPIVersion.VERSION2)
        
        # Data Logging
        self.current_dir = Path(__file__).resolve().parent
        self.data_dir = self.current_dir.joinpath(f"data/{self.name.lower()}")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        self.log_file = self.data_dir.joinpath(f"{self.name.lower()}_raw_{ts}.txt")

    def setup_mqtt(self):
        """Initializes the MQTT connection."""
        try:
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.mqtt_client.loop_start()
            logger.info(f"[{self.name}] Connected to MQTT Broker: {self.mqtt_broker}")
        except Exception as e:
            logger.error(f"[{self.name}] MQTT Connection error: {e}")

    @abstractmethod
    def setup(self):
        """
        Perform sensor-specific setup (e.g., opening serial ports, CAN interfaces).
        Should set self.enable = True if successful.
        """
        pass

    def save_raw_data(self, data: str):
        """Saves raw data strings to the log file."""
        try:
            with open(self.log_file, "a") as f:
                f.write(f"{data}\n")
        except Exception as e:
            logger.error(f"[{self.name}] Error saving raw data: {e}")

    def publish_mqtt(self, topic: str, payload: dict):
        """Publishes a dictionary as JSON to the specified MQTT topic."""
        try:
            self.mqtt_client.publish(topic, json.dumps(payload))
        except Exception as e:
            logger.error(f"[{self.name}] MQTT Publish error: {e}")

    def loop_start(self):
        """Starts the main loop in a background thread."""
        if not self.enable:
            logger.warning(f"[{self.name}] Listener not enabled. Call setup() first.")
            return
        
        self.thread = threading.Thread(target=self.main_loop, daemon=True)
        self.thread.start()
        logger.info(f"[{self.name}] Background thread started.")

    def main_loop(self):
        """Main execution loop. Should be overridden or implemented using loop_once."""
        logger.info(f"[{self.name}] Starting main loop...")
        try:
            while self.enable:
                self.loop_once()
        except Exception as e:
            logger.error(f"[{self.name}] Exception in main loop: {e}")
        finally:
            self.close()

    def loop_once(self):
        """
        Logic for a single iteration of the loop. 
        Override this if using the default main_loop.
        """
        time.sleep(0.1)

    def close(self):
        """Cleans up resources and stops threads."""
        if not self.enable:
            # We seems close once in exiting the main loop, and then close mannually in the mainApp.close()... Need to resolve this issue...
            # logger.info(f"[{self.name}] Closing listener but is not enabled, skip...", stack_info=True)
            return
        logger.info(f"[{self.name}] Closing listener...", stack_info=False)
        self.enable = False
        
        # Give the thread a moment to exit if called from outside
        time.sleep(0.2)
        
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()
        logger.info(f"[{self.name}] Listener closed.")

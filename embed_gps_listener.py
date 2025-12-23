import json
import logging
import time
from pathlib import Path

from listener import Listener
from utils import haversine

logger = logging.getLogger("e2pilot_autopi")


class EmbedGpsListener(Listener):
    def __init__(self, mqtt_broker="localhost"):
        super().__init__(name="EmbedGPS", mqtt_broker=mqtt_broker)
        self.mqtt_topic = "track/pos"
        
        # Distance tracking
        self.last_lat = None
        self.last_lon = None
        self.total_distance_m = 0.0
        self.min_move_threshold_m = 20.0

        # Current state
        self.lat = None
        self.lon = None
        self.alt = None

    def setup(self):
        """Initializes the Embedded GPS listener."""
        try:
            self.setup_mqtt()
            self.mqtt_client.subscribe(self.mqtt_topic)
            self.mqtt_client.on_message = self.on_message
            self.enable = True
            logger.info("EmbedGpsListener setup complete.")
        except Exception as e:
            logger.error(f"EmbedGpsListener setup error: {e}")
            self.enable = False

    def alive(self):
        """Checks if the listener is active."""
        if not self.enable:
            return False

        return True

    def on_message(self, client, userdata, msg):
        """Handles incoming track/pos messages."""
        try:
            payload = msg.payload.decode()
            data = json.loads(payload)
            
            # Extract location data
            pos_data = data.get("loc", {})
            lat = pos_data.get("lat")
            lon = pos_data.get("lon")
            alt = data.get("alt", 0)
            
            if lat is not None and lon is not None:
                self.lat = lat
                self.lon = lon
                self.alt = alt
                
                # Save raw data (formatted as JSON string)
                line = f"{time.time()},{self.lat},{self.lon},{self.alt}"
                self.save_raw_data(line)
                
                # Track distance
                if self.last_lat is not None and self.last_lon is not None:
                    dist = haversine(self.last_lat, self.last_lon, lat, lon)
                    if dist > self.min_move_threshold_m:
                        self.total_distance_m += dist
                        self.last_lat = lat
                        self.last_lon = lon
                else:
                    self.last_lat = lat
                    self.last_lon = lon
                
                # Publish processed data back to a standardized internal topic if needed
                # or just keep state for main_loop to use.
                
        except Exception as e:
            logger.error(f"EmbedGpsListener error processing message: {e}")

    def loop_once(self):
        """
        The MQTT client runs in its own thread (loop_start), 
        so we just sleep here to keep the main_loop alive if used.
        """
        time.sleep(1.0)

if __name__ == "__main__":
    from logger import config_logger
    config_logger(logging.DEBUG)
    listener = EmbedGpsListener()
    listener.setup()
    listener.main_loop()

import json
import logging
import math
import time
from listener import Listener

logger = logging.getLogger("e2pilot_autopi")

class EmbedAccListener(Listener):
    def __init__(self, mqtt_broker="localhost"):
        super().__init__(name="EmbedACC", mqtt_broker=mqtt_broker)
        self.mqtt_topic = "acc/gyro_acc_xyz"
        
        # Current state
        self.acc = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.gyro = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.last_timestamp = None
        self.last_save_time = 0
        self.save_interval = 0.3  # Save every xx seconds

    def setup(self):
        """Initializes the Embedded Accelerometer/Gyroscope listener."""
        try:
            self.setup_mqtt()
            self.mqtt_client.subscribe(self.mqtt_topic)
            self.mqtt_client.on_message = self.on_message
            self.enable = True
            logger.info("EmbedAccListener setup complete.")
        except Exception as e:
            logger.error(f"EmbedAccListener setup error: {e}")
            self.enable = False

    def calculate_orientation(self, x, y, z):
        """
        Calculates pitch and roll from accelerometer data.
        Returns (pitch, roll) in degrees.
        """
        # Roll: Rotation around X-axis
        roll = math.atan2(y, z) * 180 / math.pi
        
        # Pitch: Rotation around Y-axis
        pitch = math.atan2(-x, math.sqrt(y * y + z * z)) * 180 / math.pi
        
        return pitch, roll

    def on_message(self, client, userdata, msg):
        """Handles incoming acc/gyro_acc_xyz messages."""
        try:
            payload = msg.payload.decode()
            data = json.loads(payload)
            
            # Extract accelerometer and gyroscope data
            self.acc = data.get("acc", self.acc)
            self.gyro = data.get("gyro", self.gyro)
            self.last_timestamp = data.get("_stamp")

            # Calculate orientation
            self.pitch, self.roll = self.calculate_orientation(self.acc['x'], self.acc['y'], self.acc['z'])
            
            # Save raw data with a timer to reduce the number of saved lines
            current_time = time.time()
            if current_time - self.last_save_time >= self.save_interval:
                line = f"{self.last_timestamp},{self.acc['x']},{self.acc['y']},{self.acc['z']},{self.gyro['x']},{self.gyro['y']},{self.gyro['z']}"
                self.save_raw_data(line)
                self.last_save_time = current_time
                logger.debug(f"Orientation - Pitch: {pitch:.2f}, Roll: {roll:.2f}")
            
            # Optional: Log significant changes or specific thresholds if needed
            # logger.debug(f"ACC: {self.acc}, GYRO: {self.gyro}")
                
        except Exception as e:
            logger.error(f"EmbedAccListener error processing message: {e}")

    def loop_once(self):
        """
        The MQTT client runs in its own thread, 
        so we just sleep here to keep the main_loop alive if used.
        """
        time.sleep(1.0)

if __name__ == "__main__":
    from logger import config_logger
    config_logger(logging.DEBUG)
    listener = EmbedAccListener()
    listener.setup()
    listener.main_loop()

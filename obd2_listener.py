import logging
import time

import autopi
from listener import Listener

logger = logging.getLogger("e2pilot_autopi")


class Obd2Listener(Listener):
    def __init__(self, mqtt_broker="localhost"):
        super().__init__(name="OBD", mqtt_broker=mqtt_broker)
        self.mqtt_topic_prefix = "obd2"
        # Dictionary mapping command to its update interval in seconds
        self.commands = {
            "SPEED": 0.2,
            "DISTANCE_SINCE_DTC_CLEAR": 10.0,
        }
        # Track the last execution time for each command
        self.last_query_time = {cmd: 0.0 for cmd in self.commands}

    def setup(self):
        """Initializes the OBD2 listener."""
        try:
            self.setup_mqtt()
            # Verify autopi connection if possible, or just enable
            self.enable = True
            logger.info("Obd2Listener setup complete.")
        except Exception as e:
            logger.error(f"Obd2Listener setup error: {e}")
            self.enable = False

    def loop_once(self):
        """Queries each OBD2 command based on its interval and publishes the result."""
        current_time = time.time()
        for cmd, interval in self.commands.items():
            if not self.enable:
                break

            if current_time - self.last_query_time[cmd] >= interval:
                res = self.query_obd2(cmd)
                self.last_query_time[cmd] = current_time

                if res:
                    self.save_raw_data(f"{cmd}: {res}")
                    topic = f"{self.mqtt_topic_prefix}/{cmd.lower()}"
                    payload = {
                        "timestamp": current_time,
                        "command": cmd,
                        # "value": res,
                    }
                    payload.update(res)  # Assuming res is a dict-like object
                    self.publish_mqtt(topic, payload)

        time.sleep(0.05)

    def query_obd2(self, command):
        """Executes an OBD2 query via autopi."""
        try:
            # Assuming autopi.obd.execute returns a result that can be JSON serialized
            # Note: Using autopi.obd.execute as per original code structure
            response = autopi.obd.execute(["obd.query", command])
            return response
        except Exception as e:
            logger.error(f"Error querying OBD2 command {command}: {e}")
            return None


if __name__ == "__main__":
    from logger import config_logger

    config_logger(logging.DEBUG)
    obd_listener = Obd2Listener()
    obd_listener.setup()
    obd_listener.main_loop()

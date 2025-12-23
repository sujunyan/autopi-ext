import logging
import subprocess
import time
from pathlib import Path

import pynmea2
import serial

from listener import Listener
from logger import config_logger
from utils import haversine

logger = logging.getLogger("e2pilot_autopi")


def bluetooth_bind(port_num, device_name):
    command = ["sudo", "rfcomm", "bind", str(port_num), device_name, "1"]
    try:
        subprocess.run(command, capture_output=True, text=True, check=True)
        logger.info(f"Success: Device bound to /dev/rfcomm{port_num}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error occurred: {e.stderr}")


class H11Listener(Listener):
    def __init__(self, port="/dev/rfcomm0", baud=9600, mqtt_broker="localhost"):
        super().__init__(name="h11", mqtt_broker=mqtt_broker)
        self.port = port
        self.baud = baud
        self.mqtt_topic_prefix = "h11gps"
        self.ser = None
        self.device_address = "4D:B4:39:2A:93:2D"
        self.port_num = 0

        # Distance tracking
        self.last_lat = None
        self.last_lon = None
        self.total_distance_m = 0.0
        self.min_move_threshold_m = 20.0  # Ignore movements smaller than 2 meters (noise)

    def setup(self):
        try:
            if not Path(self.port).exists():
                logger.info("Binding the bluetooth port.")
                bluetooth_bind(self.port_num, self.device_address)
                time.sleep(2.0)

            self.setup_mqtt()
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
            self.enable = True
        except Exception as e:
            logger.error(f"Connection error: {e}")
            self.enable = False

    def parse_and_publish(self, raw_line):
        """解析 NMEA 数据并发布到 MQTT"""
        try:
            if not raw_line.startswith("$"):
                return
            msg = pynmea2.parse(raw_line)

            data_payload = {
                "timestamp": time.time(),
                "sentence_type": msg.sentence_type,
            }
            if isinstance(msg, pynmea2.types.talker.GGA):
                lat, lon = msg.latitude, msg.longitude
                data_payload.update(
                    {
                        "lat": lat,
                        "lon": lon,
                        "alt": msg.altitude,
                        "num_sats": msg.num_sats,
                        "status": "fix" if msg.gps_qual > 0 else "no_fix",
                    }
                )

                # Track distance if we have a valid fix
                if msg.gps_qual > 0:
                    if self.last_lat is not None and self.last_lon is not None:
                        dist = haversine(self.last_lat, self.last_lon, lat, lon)
                        if dist > self.min_move_threshold_m:
                            self.total_distance_m += dist
                            self.last_lat = lat
                            self.last_lon = lon
                    else:
                        self.last_lat = lat
                        self.last_lon = lon

                # data_payload["total_distance_m"] = self.total_distance_m
                topic = f"{self.mqtt_topic_prefix}/position"
                self.publish_mqtt(f"{self.mqtt_topic_prefix}/total_distance", {"total_distance_m": self.total_distance_m})
            elif isinstance(msg, pynmea2.types.talker.VTG):
                data_payload.update(
                    {
                        "track_true": msg.true_track,
                        "track_magnetic": msg.mag_track,
                        "speed_kmh": msg.spd_over_grnd_kmph,
                    }
                )
                topic = f"{self.mqtt_topic_prefix}/speed"
            else:
                return
            self.publish_mqtt(topic, data_payload)
        except pynmea2.ParseError:
            pass
        except Exception as e:
            logger.error(f"Parsing error: {e}")

    def loop_once(self):
        if self.ser and self.ser.is_open:
            if self.ser.in_waiting > 0:
                line = self.ser.readline().decode("ascii", errors="replace").strip()
                if line:
                    self.save_raw_data(line)
                    self.parse_and_publish(line)
            else:
                time.sleep(0.1)
        else:
            self.enable = False

    def close(self):
        super().close()
        if self.ser and self.ser.is_open:
            self.ser.close()


if __name__ == "__main__":
    config_logger(logging.DEBUG)
    h11_listener = H11Listener(port="/dev/rfcomm0")
    h11_listener.setup()
    h11_listener.main_loop()

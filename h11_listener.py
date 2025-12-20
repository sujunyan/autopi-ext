import serial
import pynmea2
import paho.mqtt.client as mqtt
import json
import time
import os
import logging
from pathlib import Path
from datetime import datetime
import threading

from logger import config_logger 

logger = logging.getLogger("e2pilot_autopi")

current_dir = Path(__file__).resolve().parent
data_dir = current_dir.joinpath("data/h11")

class H11Listener:
    def __init__(self, port='/dev/rfcomm0', baud=9600, mqtt_broker="localhost"):
        self.port = port
        self.baud = baud

        ts = datetime.now().strftime("%Y%m%d_%H")
        self.log_file = data_dir.joinpath(f"h11_raw_{ts}.txt")
        
        # MQTT 配置
        self.mqtt_topic_prefix = "h11gps"
        self.client = mqtt.Client()
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = 1883
        
        self.ser = None
        self.enable = False

    def setup(self):
        try:
            # 连接 MQTT
            self.client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.client.loop_start()
            # logger.debug(f"Connected to MQTT Broker: {self.mqtt_broker}")
            
            # 连接串口
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
            # logger.debug(f"Connected to GPS on {self.port}")
            self.enable = True
        except Exception as e:
            logger.error(f"Connection error: {e}")
            self.enable = False

    def save_raw_data(self, raw_line):
        with open(self.log_file, "a") as f:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"{timestamp} - {raw_line}\n")

    def parse_and_publish(self, raw_line):
        """解析 NMEA 数据并发布到 MQTT"""
        try:
            if not raw_line.startswith('$'):
                return
            msg = pynmea2.parse(raw_line)
            
            data_payload = {
                "timestamp": time.time(),
                "sentence_type": msg.sentence_type,
            }
            if isinstance(msg, pynmea2.types.talker.GGA):
                data_payload.update({
                    "lat": msg.latitude,
                    "lon": msg.longitude,
                    "alt": msg.altitude,
                    "num_sats": msg.num_sats,
                    "status": "fix" if msg.gps_qual > 0 else "no_fix"
                })
                topic = f"{self.mqtt_topic_prefix}/position"
            elif isinstance(msg, pynmea2.types.talker.VTG):
                data_payload.update({
                    "track_true": msg.true_track,
                    "track_magnetic": msg.mag_track,
                    # "speed_knots": msg.spd_over_grnd_kts,
                    "speed_kmh": msg.spd_over_grnd_kmph
                })
                topic = f"{self.mqtt_topic_prefix}/speed"
                # print(data_payload)
            else:
                return
            self.client.publish(topic, json.dumps(data_payload))
            # logger.debug(f"Published to {topic}: Lat {data_payload.get('lat')}, Lon {data_payload.get('lon')}")
        except pynmea2.ParseError:
            pass
        except Exception as e:
            logger.error(f"Parsing error: {e}")

    def loop_start(self):
        self.thread = threading.Thread(target=self.main_loop, daemon=True)
        self.thread.start()

    def main_loop(self):
        if not self.ser and not self.enable:
            logger.warn("h11 listener is not set up properly.")
            return

        logger.info("Starting GPS Data Stream...")
        try:
            while self.enable and self.ser.is_open:
                if self.ser.in_waiting > 0:
                    line = self.ser.readline().decode('ascii', errors='replace').strip()
                    if line:
                        self.save_raw_data(line)
                        self.parse_and_publish(line)
                else:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            logger.info("\nStopping h11_listener...")
        finally:
            self.close()

    def close(self):
        self.enable = False
        # if hasattr(self, 'thread') and self.thread.is_alive():
            # self.thread.join()
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.client.loop_stop()
        self.client.disconnect()

if __name__ == "__main__":
    config_logger(logging.DEBUG)
    h11_listener = H11Listener(port='/dev/rfcomm0')
    h11_listener.setup()
    h11_listener.main_loop()
import csv
import json
import logging
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

from logger import config_logger

import j1939
from j1939Parser import J1939Parser
from listener import Listener
import utils

logger = logging.getLogger("e2pilot_autopi")

default_ca_name = j1939.Name(
    arbitrary_address_capable=0,
    industry_group=j1939.Name.IndustryGroup.Industrial,
    vehicle_system_instance=1,
    vehicle_system=1,
    function=1,
    function_instance=1,
    ecu_instance=1,
    manufacturer_code=666,
    identity_number=1234567,
)


class J1939Listener(Listener):
    def __init__(
        self,
        ca_name=default_ca_name,
        ca_address=0xF9,
        can_channel="can0",
        bustype="socketcan",
        can_rate=250000,
        mqtt_broker="localhost",
    ):
        super().__init__(name="J1939", mqtt_broker=mqtt_broker)
        self.ca_name = ca_name
        self.ca_address = ca_address
        self.can_channel = can_channel
        self.bustype = bustype
        self.can_rate = can_rate
        self.ecu = None
        self.ca = None
        self.parser = J1939Parser()
        self.available_pgns = set()
        self.all_pgns = self.parser.all_pgns
        self.current_data = {}
        self.is_scanned = False
        self.mqtt_topic = "j1939/"

        # Override log file to CSV for J1939
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        self.log_file = self.data_dir.joinpath(f"j1939_raw_data_{ts}.csv")

    def setup(self):
        """Set up the CAN interface and initialize the ECU and ControllerApplication."""
        if not self.setup_can_interface():
            self.enable = False
            return

        try:
            self.setup_mqtt()
            self.ecu = j1939.ElectronicControlUnit()
            self.ca = j1939.ControllerApplication(self.ca_name, self.ca_address)
            self.ecu.connect(bustype=self.bustype, channel=self.can_channel)
            self.ecu.add_ca(controller_application=self.ca)
            self.ca.subscribe(self.ca_receive)
            self.ca.start()
            self.enable = True
            logger.info(f"J1939Listener setup complete on {self.can_channel}.")
        except Exception as e:
            logger.error(f"J1939 setup error: {e}")
            self.enable = False

    def loop_once(self):
        if not self.is_scanned:
            self.scan_pgns()

        for pgn in self.available_pgns:
            interval = self.pgn2time_interval(pgn)
            last_ts = self.current_data.get(pgn, {}).get("timestamp", 0)
            if interval > 0 and (time.time() - last_ts) >= interval:
                self.request_pgn(pgn)
        time.sleep(0.1)

    def scan_pgns(self):
        logger.info("PGN scanning started")
        for _ in range(5):
            for pgn in self.all_pgns:
                if pgn not in self.available_pgns:
                    self.request_pgn(pgn)
                    time.sleep(0.5)
        self.is_scanned = True
        logger.info("PGN scan complete")

    def pgn2time_interval(self, pgn):
        
        pgn_dict = self.get_pgn_dict()
        tt = pgn_dict.get(pgn, (1.0, "Unknown PGN"))

        return tt[0]

    def get_pgn_dict(self):
        no_interval = -1.0
        fast_interval = 0.2
        default_interval = 1.0
        slow_interval = 60.0
        slower_interval = 300.0
        pgn_dict = {
            65265: (fast_interval,  "vehicle speed"),
            65256: (fast_interval,  "navigation speed & pitch"),
            61444: (fast_interval,  "engine speed and torque"),
            65215: (default_interval,  "front axle speed"),
            65266: (default_interval,  "fuel rate"),
            65217: (default_interval, "high resolution total vehicle distance"),
            65248: (slow_interval,  "trip distance"),
            65199: (slow_interval,  "Trip fuel (gaseous)"),
            65257: (slow_interval,  "Trip fuel (liquid)"),
            65276: (slow_interval, "fuel level"),
            65201: (slow_interval, "ECU Distance"),
            65202: (slow_interval, "trip average Fuel rate (gaseous)"),
            65253: (slower_interval, "total engine hours"),
            65255: (slower_interval, "total vehicle hours"),
            65263: (slower_interval, "engine oil level"),
            65244: (slower_interval, "total idel fuel used"),
            65262: (no_interval, "fuel temperature"),
            65194: (no_interval, "gaseous fuel correction factor"),
            61443: (no_interval, "accelerator pedal 1 low idle switch"),
            61450: (no_interval, "inlet air mass flow rate"),
            65153: (no_interval, "fuel flow rate"),
            65132: (no_interval, "tachograph vehicle speed"),
        }
        return pgn_dict

    def get_pgn_name(self, pgn):
        pgn_dict = self.get_pgn_dict()
        tt = pgn_dict.get(pgn, (-1.0, "Unknown PGN"))

        return tt[1]


    def ca_receive(self, priority, pgn, source, timestamp, data):
        if pgn not in self.available_pgns and pgn in self.all_pgns:
            self.available_pgns.add(pgn)
            logger.info(f"Discovered new PGN: {pgn} ({self.get_pgn_name(pgn)})")
        logger.debug(f"Got a PGN: {pgn} with data {data}")

        self.save_raw_data_csv(pgn, timestamp, data)
        parsed_j1939_data = self.parser.parse_data(pgn, data)
        parsed_j1939_data["timestamp"] = timestamp
        self.publish_parsed_data(parsed_j1939_data)
        self.current_data[pgn] = parsed_j1939_data

    def mqtt_topic_filter(self, topic):
        topic_subtrings = [
            "Vehicle_Speed",
            "Fuel_Level",
            "Fuel_Rate",
            "Fuel_Used",
            "Vehicle_Distance",
            "Distance",
            "Pitch",
        ]
        for substr in topic_subtrings:
            if substr in topic:
                return True
        return False

    def publish_parsed_data(self, parsed_j1939_data):
        ts = parsed_j1939_data["timestamp"]
        for key, value in parsed_j1939_data.items():
            if key == "timestamp":
                continue
            sub_topic = key.replace(" ", "_")
            if not self.mqtt_topic_filter(sub_topic):
                continue
            topic = self.mqtt_topic + sub_topic
            payload = value.copy() if isinstance(value, dict) else {"value": value}
            payload["topic"] = sub_topic
            payload["timestamp"] = ts
            self.publish_mqtt(topic, payload)

    def save_raw_data_csv(self, pgn, timestamp, data):
        file_exists = self.log_file.exists()
        with open(self.log_file, mode="a", newline="") as fd:
            writer = csv.writer(fd)
            if not file_exists:
                writer.writerow(["Timestamp", "PGN", "Data"])
            writer.writerow([timestamp, pgn, data.hex()])

    def close(self):
        if self.ecu:
             if getattr(self.ecu, '_bus', None) is not None:
                self.ecu.disconnect()
        if self.ca:
            self.ca.stop()
        super().close()
        # logger.info("J1939Listener stopped.")

    def setup_can_interface(self):
        can_channel = self.can_channel
        # can_rate = 250000
        can_rate = self.can_rate 
        utils.setup_can_interface(can_channel, can_rate)
        # cmd = f"sudo ip link set {can_channel} down && sudo ip link set {can_channel} up type can bitrate {can_rate} sample-point 0.8"
        # try:
        #     logger.info("setting up can interface...")
        #     result = subprocess.run(cmd, shell=true, capture_output=true, text=true)
        #     if result.returncode == 0:
        #         logger.info("can interface setup successfully.")
        #         return true
        #     else:
        #         logger.error(f"failed to set up can interface: {result.stderr}")
        #         return false
        # except exception as e:
        #     logger.exception(f"unexpected error setting up can interface: {e}")
        #     return false


    def request_pgn(self, pgn, data_page=0, destination=0x00, priority=6):
        if not self.ca or self.ca.state != j1939.ControllerApplication.State.NORMAL:
            return True
        data = [
            (pgn & 0xFF),
            ((pgn >> 8) & 0xFF),
            ((pgn >> 16) & 0xFF),
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
        # destination = 0x00
        # data_page = 0
        # priority = 6
        self.ca.send_pgn(
            data_page,
            (j1939.ParameterGroupNumber.PGN.REQUEST >> 8) & 0xFF,
            destination & 0xFF,
            priority,
            data,
        )
        return True

if __name__ == "__main__":
    config_logger(logging.DEBUG)
    ls = J1939Listener(can_channel="can0", can_rate=500_000)
    ls.setup()
    time.sleep(5)
    priority = 6
    des = 0x00
    logger.debug("sending requests")
    # ls.scan_pgns()
    # ls.send_heartbeat()
    # for des in range(0, 256):
    #     logger.debug(f"sending reuqests to des {des}")
    #     ls.request_pgn(65144, 0, des, priority)
    #     time.sleep(0.5)
    
    time.sleep(1000)
    ls.close() 
    time.sleep(1)

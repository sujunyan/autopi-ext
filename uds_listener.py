"""
This script is for UDS, cargobot X5000
"""

import can, isotp, udsoncan
from logger import config_logger
import subprocess, csv, time, logging
from datetime import datetime

from udsoncan.connections import IsoTPSocketConnection
from udsoncan.client import Client
from udsoncan.exceptions import *
from udsoncan.services import *
import udsoncan.configs

import struct
import utils
from listener import Listener


logger = logging.getLogger("e2pilot_autopi")

"""
The class for listening to the OBD with the UDS protocol
"""
class UdsListener(Listener):
    def __init__(self, 
        mqtt_broker="localhost",
        can_channel="can0",
        bustype="socketcan",
        can_rate=500000,
        ):
        super().__init__(name="UDS", mqtt_broker=mqtt_broker)
        self.mqtt_topic = "uds/"

        self.bustype = bustype
        self.can_rate = can_rate
        self.can_channel = can_channel

        # Override log file to CSV for J1939
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        self.log_file = self.data_dir.joinpath(f"{ts}_uds_raw_data.csv")


    def setup_uds(self):
        self.data_identifiers =  {
           # 'default' : '>H',
           0x0102 : EngineCodec,
           0x013F : FuelCodec,
           0x0173 : FuelLevelCodec
        }
        self.uds_config = dict(udsoncan.configs.default_client_config)
        self.uds_config['data_identifiers'] = self.data_identifiers

        self.isotp_address_mode =  isotp.AddressingMode.Normal_29bits 
        self.txid = 0x18DA00F1
        self.rxid = 0x18DAF100

        # self.bus = can.interface.Bus(channel=self.can_cannel, bustype=self.bustype)

        self.connection = IsoTPSocketConnection(self.can_channel, 
            isotp.Address(self.isotp_address_mode, rxid=self.rxid, txid=self.txid)
            )


        self.uds_client = Client(self.connection, config=self.uds_config)
        self.uds_client.open()

    def setup(self):
        if not utils.setup_can_interface(self.can_channel, self.can_rate):
            self.enable = False
            return

        try:
            self.setup_mqtt()
            self.setup_uds()
            self.enable = True
            logger.info("UdsListener setup complete.")
        except Exception as e:
            logger.exception(f"UdsListener setup error1: {e}")
            self.enable = False

    def save_raw_data_csv(self, d, ts):
        file_exists = self.log_file.exists()
        keys = list(d.keys())
        keys.sort()
        with open(self.log_file, mode="a", newline="") as fd:
            writer = csv.writer(fd)
            if not file_exists:
                headers = ["Timestamp"]
                headers.extend(keys)
                writer.writerow(headers)
            row = [ts]
            row.extend([d[k] for k in keys])
            writer.writerow(row)

    def loop_once(self):
        if not self.enable:
            return

        DEBUG = False
        try:
            if DEBUG:
                d = {"speed" : 72}
            else:
                self.uds_client.tester_present()
                d = dict()
                for data_id in self.data_identifiers.keys():
                    response = self.uds_client.read_data_by_identifier(data_id)
                    d.update(response.service_data.values[data_id])
            
            ts = time.time()
            self.save_raw_data_csv(d, ts)

            for key in ["speed"]:
                if key in d.keys():
                    topic = f"{self.mqtt_topic}{key}"
                    payload = {
                        "timestamp": ts,
                        "value": d[key],
                    }
                    self.publish_mqtt(topic, payload)
                    # logger.debug(f"Published {topic}: {payload}")

            time.sleep(0.2)
        except Exception as e:
            logger.error(f"loop once in UDS failed: {e}")
            time.sleep(1)

    def close(self):
        self.uds_client.close()
        self.connection.close()
        super().close()

# 0x013F
class FuelCodec(udsoncan.DidCodec):
   def encode(self, val):
        return struct.pack('<L', val) 

   def decode(self, payload):
        s = " ".join(f"{b:02X}" for b in payload)
        fuel_rate = struct.unpack('>H', payload)[0] * 0.05
        # logger.info(f"Got data {s} len={len(payload)} fuel_rate={fuel_rate}")
        logger.debug(f"fuel_rate={fuel_rate}")
        d = {
            'fuel_rate' : fuel_rate # unit kg/L
        }
        return d

   def __len__(self):
        return 2    

# 0x0173
class FuelLevelCodec(udsoncan.DidCodec):
    def encode(self, val):
        return struct.pack('<L', val) 

    def decode(self, payload):
        s = " ".join(f"{b:02X}" for b in payload)
        fuel_level = payload[11] * 0.4
        # logger.info(f"Got data {s} len={len(payload)} fuel_level={fuel_level}")
        logger.debug(f"fuel_level={fuel_level}")
        d = {
            "fuel_level" : fuel_level # unit: %
        }
        return d

    def __len__(self):
        return 20    

# 0x0102
class EngineCodec(udsoncan.DidCodec):
   def encode(self, val):
        return struct.pack('<L', val) 

   def decode(self, payload):
        for (i, b) in enumerate(payload):
            pass
        s = " ".join(f"{b:02X}" for b in payload)
        rpm_candidate = struct.unpack('>H', payload[21:23])[0]/8
        torque_perc = payload[38] - 125.0
        speed = struct.unpack('>H', payload[23:25])[0] * 0.00390625
        # logger.info(f"Got data {s} len={len(payload)} rpm={rpm_candidate}, torque_perc={torque_perc}, speed={speed}")
        logger.debug(f"rpm={rpm_candidate}, torque_perc={torque_perc}, speed={speed}")
        
        d = {
            "rpm" : rpm_candidate,
            "torque" : torque_perc,
            "speed" : speed,
        }
        return d

   def __len__(self):
        return 40    # encoded payload is 8 byte long.


if __name__ == "__main__":
    config_logger(logging.DEBUG)
    ls = UdsListener(can_channel="can0", can_rate=500_000)
    ls.setup()
    ls.loop_start()

    time.sleep(100)
    ls.close()

# with Client(connection, config=config) as client:
#     print("开始轮询车辆数据... 按 Ctrl+C 停止")
#     
#     while True:
#         try:
#             # --- 维持心跳 (Tester Present) ---
#             # 某些 ECU 需要持续收到这个才允许频繁请求
#             client.tester_present()
# 
#             # engine information
#             response = client.read_data_by_identifier(0x0102)
# 
#             # Fuel rate information
#             response = client.read_data_by_identifier(0x013F)
# 
#             # Fuel Level info
#             response = client.read_data_by_identifier(0x0173)
# 
#             # print(response.service_data.values[0x0102].hex())
#             # print(response.service_data.values[0x0102])
#             # logger.info(f"Got frame {s}")
#             time.sleep(1.0)  # 10Hz 轮询频率，自动驾驶建议不要低于 20Hz
#         except Exception as e:
#             print(f"读取失败: {e}")
#             time.sleep(1)
"""
This script is for UDS, cargobot X5000
"""

import can
import isotp
import udsoncan
import time
from udsoncan.connections import PythonIsoTpConnection
from udsoncan.client import Client
from udsoncan import configs
import logging
from logger import config_logger
import subprocess

## From the example
import udsoncan
import isotp
from udsoncan.connections import IsoTPSocketConnection
from udsoncan.client import Client
from udsoncan.exceptions import *
from udsoncan.services import *
import udsoncan.configs
import struct

config_logger(logging.DEBUG)

# 0x013F
class FuelCodec(udsoncan.DidCodec):
   def encode(self, val):
        return struct.pack('<L', val) 

   def decode(self, payload):
        s = " ".join(f"{b:02X}" for b in payload)
        fuel_rate = struct.unpack('>H', payload)[0] * 0.05
        # logger.info(f"Got data {s} len={len(payload)} fuel_rate={fuel_rate}")
        logger.info(f"fuel_rate={fuel_rate}")
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
        logger.info(f"fuel_level={fuel_level}")
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
        veh_spd = struct.unpack('>H', payload[23:25])[0] * 0.00390625
        # logger.info(f"Got data {s} len={len(payload)} rpm={rpm_candidate}, torque_perc={torque_perc}, veh_spd={veh_spd}")
        logger.info(f"rpm={rpm_candidate}, torque_perc={torque_perc}, veh_spd={veh_spd}")
        
        d = {
            "rpm" : rpm_candidate,
            "torque" : torque_perc,
        }
        return d

   def __len__(self):
        return 40    # encoded payload is 8 byte long.

def setup_can_interface():
    # can_channel = self.can_channel
    # can_rate = 250000
    # can_rate = self.can_rate 
    can_channel = "can0"
    can_rate = 500000
    cmd = f"sudo ip link set {can_channel} down && sudo ip link set {can_channel} up type can bitrate {can_rate} sample-point 0.8"
    try:
        logger.info("Setting up CAN interface...")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("CAN interface setup successfully.")
            return True
        else:
            logger.error(f"Failed to set up CAN interface: {result.stderr}")
            return False
    except Exception as e:
        logger.exception(f"Unexpected error setting up CAN interface: {e}")
        return False

logger = logging.getLogger("e2pilot_autopi")
setup_can_interface()

config = dict(udsoncan.configs.default_client_config)
config['data_identifiers'] = {
   'default' : '>H',
   0x0102 : EngineCodec,
   0x013F : FuelCodec,
   0x0173 : FuelLevelCodec
}



# 1. 配置 ISO-TP 传输层 (针对 Woodward OH6.0)
# txid: 诊断仪发送 ID, rxid: ECU 回复 ID
isotp_params = {
    'txid': 0x18DA00F1,
    'rxid': 0x18DAF100,
    'addressing_mode': isotp.AddressingMode.Normal_29bits,
}
# 2. 建立 CAN 总线连接 (此处以 Linux SocketCAN 为例)
bus = can.interface.Bus(channel='can0', bustype='socketcan')
# 3. 封装 ISO-TP 层
# socket = isotp.socket()
# socket.bind(bus, address=isotp.Address(isotp_params['addressing_mode'], rxid=isotp_params['rxid'], txid=isotp_params['txid']))
# connection = PythonIsoTpConnection(socket)

connection = IsoTPSocketConnection('can0', isotp.Address(isotp.AddressingMode.Normal_29bits, rxid=isotp_params['rxid'], txid=isotp_params['txid']))
# 4. 定义数据解析逻辑 (DID 对应关系)
# 注意：以下 DID 为 Woodward 常用或 OBD 标准 DID，具体需参考你的 DBC/协议文档

# 5. 主程序循环
with Client(connection, config=config) as client:
    print("开始轮询车辆数据... 按 Ctrl+C 停止")
    
    while True:
        try:
            # --- 维持心跳 (Tester Present) ---
            # 某些 ECU 需要持续收到这个才允许频繁请求
            client.tester_present()

            # engine information
            response = client.read_data_by_identifier(0x0102)

            # Fuel rate information
            response = client.read_data_by_identifier(0x013F)

            # Fuel Level info
            response = client.read_data_by_identifier(0x0173)

            # print(response.service_data.values[0x0102].hex())
            # print(response.service_data.values[0x0102])
            # request = bytearray([0x03, 0x22, 0x01, 0x02])
            # connection.send(request)
            # payload = connection.wait_frame(timeout=1)
            # s = " ".join(f"{b:02X}" for b in payload)
            # logger.info(f"Got frame {s}")
            # --- 读取引擎转速 ---
            # response = client.read_data_by_identifier(DIDS['ENGINE_SPEED'])
            # if response.positive:
            #     rpm = parse_engine_speed(response.service_data.raw_payload)
            #     print(f"转速: {rpm:>7} RPM", end=' | ')
            
            # --- 读取车辆速度 ---
            # response = client.read_data_by_identifier(DIDS['VEHICLE_SPEED'])
            # if response.positive:
            #     logger.info(f"Got positive response {response.service_data.raw_payload}")
                # speed = parse_vehicle_speed(response.service_data.raw_payload)
                # logger.info(f"车速: {speed:>3} km/h", end=' | ')
            # --- 读取燃料消耗 ---
            # response = client.read_data_by_identifier(DIDS['FUEL_RATE'])
            # ... 解析逻辑 ...
            # print("") # 换行
            time.sleep(1.0)  # 10Hz 轮询频率，自动驾驶建议不要低于 20Hz
        except Exception as e:
            print(f"读取失败: {e}")
            time.sleep(1)
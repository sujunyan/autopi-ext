import threading
import time
import logging
import j1939
import subprocess
from j1939Parser import J1939Parser
from pathlib import Path
from datetime import datetime
import csv
import os
import paho.mqtt.client as mqtt
import json
import threading


logger = logging.getLogger("e2pilot_autopi")

current_dir = Path(__file__).resolve().parent
data_dir = current_dir.joinpath("data/j1939")


default_ca_name = j1939.Name(
        arbitrary_address_capable=0,
        industry_group=j1939.Name.IndustryGroup.Industrial,
        vehicle_system_instance=1,
        vehicle_system=1,
        function=1,
        function_instance=1,
        ecu_instance=1,
        manufacturer_code=666,
        identity_number=1234567
        )


class J1939Listener:
    def __init__(self, ca_name = default_ca_name, ca_address=0xF9, can_channel='can0', bustype='socketcan'):
        """
        Initialize the J1939Listener with a ControllerApplication and CAN interface details.
        """
        self.ca_name = ca_name
        self.ca_address = ca_address
        self.can_channel = can_channel
        self.bustype = bustype
        self.ecu = None
        self.ca = None
        self.enable = False

    def setup(self):
        """
        Set up the CAN interface and initialize the ECU and ControllerApplication.
        """

        self.setup_can_interface()  # Set up the CAN interface
        self.ecu = j1939.ElectronicControlUnit()
        self.ca = j1939.ControllerApplication(self.ca_name, self.ca_address)
        self.ecu.connect(bustype=self.bustype, channel=self.can_channel)
        self.ecu.add_ca(controller_application=self.ca)
        self.ca.subscribe(self.ca_receive)
        self.parser = J1939Parser()


        self.ca.start()
        self.enable = True

        self.available_pgns = set()
        self.all_pgns = self.parser.all_pgns

        ## store the current data with the format pgn: data
        self.current_data = {}

        ## the path to store the raw can data
        ts = datetime.now().strftime("%Y%m%d_%H")
        self.raw_can_csv_path = data_dir.joinpath(f"j1939_raw_data_{ts}.csv")
        self.raw_can_csv_path.parent.mkdir(parents=True, exist_ok=True)
        # print(data_dir)
        # print(self.raw_can_csv_path)

        # MQTT settings
        self.mqtt_broker = 'localhost'
        self.mqtt_port = 1883
        self.mqtt_client = mqtt.Client()
        self.mqtt_topic = 'j1939/'
        # Connect to the MQTT broker
        try:
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port)
            logger.info("Connected to MQTT broker.")
        except Exception as e:
            logger.error(f"Failed to connect to MQTT broker: {e}")


        self.is_scanned = False
        logger.info("J1939Listener setup complete.")

    def main_loop_once(self):
        """
        Rune the main loop manually once. Can be called periodically from outside.
        """
        
        if self.enable:
            if not self.is_scanned:
                self.scan_pgns()

            for pgn in self.available_pgns:
                interval = self.pgn2time_interval(pgn)
                last_ts = self.current_data.get(pgn, {}).get('timestamp', 0)
                if interval > 0 and (time.time() - last_ts) >= interval:
                    self.request_pgn(pgn)
            # logger.debug(f"Current data {self.current_data}")

    def loop_start(self):
        self.thread = threading.Thread(target=self.main_loop, daemon=True)
        self.thread.start()

    def main_loop(self):
        """
        periodically send the requests for specific PGNs.
        """
        if not self.enable:
            logger.error("J1939Listener is not enabled. Please run setup() first.")
        
        while self.enable:
            self.main_loop_once()
            time.sleep(0.1)
            # logger.debug(f"Current data {self.current_data}")

        logger.info("J1939Listener main loop has exited.")
    
    def scan_pgns(self):
        logger.info("PGN scanning started")
        for i in range(5):
            for pgn in self.parser.all_pgns:
                if pgn not in self.available_pgns:
                    self.request_pgn(pgn)
                    time.sleep(0.5)  # brief pause between requests
        self.is_scanned = True

        logger.info("PGN scan complete")

    def pgn2time_interval(self, pgn):
        """
        Map PGN to time interval for periodic requests.
        """

        no_interval = -1.0  # Indicate no periodic request needed

        fast_interval = 0.2  # 0.2 seconds for fast updates
        default_interval = 1.0  # 1 second for default updates
        slow_interval = 60.0  # 60 seconds for slow updates
        slower_interval = 300.0  # 5 minutes for very slow updates

        pgn2time_d = {
            65265: fast_interval,  # Wheel-Based Vehicle Speed
            65256: fast_interval,  # Navigation-Based Vehicle Speed, Pitch, Altitude
            65215: default_interval,  # Front Axle Speed, Relative Speed; Front Axle; Left Wheel, Relative Speed; Front Axle; Right Wheel


            65266: default_interval,  # Fuel Rate (Liquid), Instantaneous Fuel Economy, Average Fuel Economy
            65199: slow_interval,  # Trip Fuel (Gaseous), Total Fuel Used (Gaseous)
            65257: slow_interval,  # Trip Fuel (Liquid), Total Fuel Used (Liquid)

            61444: slow_interval,  # ECC1: Engine performance

            65276: slow_interval,  # Fuel Level
            65201: slow_interval,  # Total ECU Distance, Total ECU Run Time
            65202: slow_interval,  # Total Engine PTO Fuel Used (Gaseous), Trip Average Fuel Rate (Gaseous)

            65253: slower_interval,  # Total Engine Hours, Total Engine Revolutions
            65255: slower_interval,  # Total Vehicle Hours, Total Power Takeoff Hours
            65263: slower_interval,  # Engine Oil Level, Engine Oil Pressure

            65244: slower_interval,  # Total Idle Fuel Used, Total Idle Hours

            65217: slower_interval,  # High Resolution Total Vehicle Distance, High Resolution Trip Distance
            65248: slower_interval,  # Trip Distance, Total Vehicle Distance

            65262: no_interval,  # Fuel Temperature

            65194: no_interval,  # Gaseous Fuel Correction Factor
            61443: no_interval,  # Accelerator Pedal 1 Low Idle Switch
            61450: no_interval,  # EGR Mass Flow Rate, Inlet Air Mass Flow Rate
            65153: no_interval,  # Fuel Flow Rate 1, Fuel Flow Rate 2

            
        }
        return pgn2time_d.get(pgn, default_interval)  # Default to 1.00 seconds if PGN not found

    def ca_receive(self, priority, pgn, source, timestamp, data):
        """Feed incoming message to this CA.
        (OVERLOADED function)
        :param int priority:
            Priority of the message
        :param int pgn:
            Parameter Group Number of the message
        :param intsa:
            Source Address of the message
        :param int timestamp:
            Timestamp of the message
        :param bytearray data:
            Data of the PDU
        """
        # print("ts {} priority {} PGN {} source {} length {} data {}".format(timestamp, priority, pgn, source, len(data), data))
        if pgn not in self.available_pgns and pgn in self.all_pgns:
            self.available_pgns.add(pgn)
            logger.info(f"Discovered new PGN: {pgn}.")
        
        self.save_one_frame(pgn, timestamp, data)
    
        parsed_j1939_data = self.parser.parse_data(pgn, data)
        parsed_j1939_data['timestamp'] = timestamp
        self.publish_one_mqtt_message(parsed_j1939_data)
        # if parsed_j1939_data['code'] == 0:
        self.current_data[pgn] = parsed_j1939_data
        # if pgn in [65265]:
        #     logger.debug(f"Parsed J1939 Data: {parsed_j1939_data}")
        #     speed = parsed_j1939_data['Wheel-Based Vehicle Speed']['value']
        #     logger.debug(f"Got speed={speed}")
    
    def mqtt_topic_filter(self, topic):
        """
        Filtering function for MQTT topics.
        """

        topic_subtrings = [
                        "Vehicle_Speed", 
                        "Fuel_Level",  
                        "Fuel_Rate",
                        "Fuel_Used",
                        "Vehicle_Distance", 
                        "Pitch"
                    ]
        for substr in topic_subtrings:
            if substr in topic:
                return True
        return False

    def publish_one_mqtt_message(self, parsed_j1939_data):
        mqtt_topic = self.mqtt_topic
         # Publish the frame to an MQTT topic
        # mqtt_payload = parsed_j1939_data
        ts = parsed_j1939_data['timestamp']
        for (key, value) in parsed_j1939_data.items():
            sub_topic = key.replace(" ", "_")
            if not self.mqtt_topic_filter(sub_topic):
                continue
            topic = mqtt_topic + sub_topic
            payload = value
            payload['topic'] = sub_topic
            payload['timestamp'] = ts
            try:
                self.mqtt_client.publish(topic, json.dumps(payload))
                # logger.debug(f"Published frame to MQTT topic '{topic}': {payload}")
            except Exception as e:
                logger.error(f"Failed to publish to MQTT: {e}")
        
    def save_one_frame(self, pgn, timestamp, data):
        # Ensure the CSV file exists and is ready for writing
        csv_file = self.raw_can_csv_path
        file_exists = os.path.isfile(csv_file)

        # Write the frame to the CSV file
        with open(csv_file, mode='a', newline='') as fd:
            writer = csv.writer(fd)
            if not file_exists:
                # Write the header only if the file is being created
                writer.writerow(["Timestamp", "PGN", "Data"])
            writer.writerow([timestamp, pgn, data.hex()])  # Convert bytearray to hex string for readability

        # logger.debug(f"Saved frame to {csv_file}: PGN={pgn}, Timestamp={timestamp}, Data={data.hex()}")

    
    def close(self):
        """
        Stop the listener and periodic requests.
        """
        self.enable = False
        self.ca.stop()
        self.ecu.disconnect()
        logger.info("J1939Listener stopped.")

    def setup_can_interface(self):
        """
        Set up the CAN interface 'can0' with a bitrate of 250000. 
    
        Note that if we want to be compatible with ISO small car OBD-II protocol, we might need to add a function to automatically detect the OBD protocol. But for now, let's focus on heavy vehicles using J1939 over CAN.
        """

        can_channel = self.can_channel
        can_rate = 250000

        cmd = f"sudo ip link set {can_channel} down && sudo ip link set {can_channel} up type can bitrate {can_rate}"
        try:
            logger.info("Setting up CAN interface...")
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)

            if result.returncode == 0:
                logger.info("CAN interface setup successfully.")
                return True
            else:
                error_message = result.stderr.lower()
                if "does not exist" in error_message:
                    logger.error("Error: CAN interface 'can0' does not exist.")
                elif "device is down" in error_message:
                    logger.error("Error: CAN interface 'can0' is down.")
                elif "is up" in error_message:
                    logger.warning("Warning: CAN interface 'can0' is already up.")
                else:
                    logger.error(f"Failed to set up CAN interface: {result.stderr}")
                return False
        except Exception as e:
            logger.exception(f"An unexpected error occurred while setting up CAN interface: {e}")
            return False

    def request_pgn(self, pgn):
        """
        Given the pgn, generate a function that send the requests of such pgn.

        Used to easily create new callback functions
        """
        # wait until we have our device_address
        if self.ca.state != j1939.ControllerApplication.State.NORMAL:
            # returning true keeps the timer event active
            return True

        logger.debug(f"Request can with pgn {pgn}")

        # def send_request(self, data_page, pgn, destination):

        # create data with 8 bytes
        # data = [j1939.ControllerApplication.FieldValue.NOT_AVAILABLE_8] * 8

        ## Note that in default ca.send_request function, the data length 3 instead of 8. We need to mannually send the raw data
        ## see also the function defined in controller_application.py:280
        ## Note 
        data = [(pgn & 0xFF), ((pgn >> 8) & 0xFF), ((pgn >> 16) & 0xFF), 0x00, 0x00, 0x00, 0x00, 0x00]

        destination = 0x00 # address for engine.
        data_page = 0
        priority = 6  # default priority for request PGN
        self.ca.send_pgn(data_page, 
                (j1939.ParameterGroupNumber.PGN.REQUEST >> 8) & 0xFF, 
                destination & 0xFF, 
                priority, 
                data)
        return True


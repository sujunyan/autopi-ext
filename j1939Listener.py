import threading
import time
import logging
import j1939
from main import setup_can_interface  # Assuming setup_can_interface is in main.py
import subprocess
from j1939Parser import J1939Parser

logger = logging.getLogger("j1939_listener")


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
        setup_can_interface()  # Set up the CAN interface
        self.ecu = j1939.ElectronicControlUnit()
        self.ca = j1939.ControllerApplication(self.ca_name, self.ca_address)
        self.ecu.connect(bustype=self.bustype, channel=self.can_channel)
        self.ecu.add_ca(controller_application=self.ca)
        self.ca.subscribe(self.ca_receive)
        self.parser = J1939Parser()

        self.ca.start()
        self.enable = True
        logger.info("J1939Listener setup complete.")

    def main_loop(self):
        """
        periodically send the requests for specific PGNs.
        """
        if not self.enable:
            logger.error("J1939Listener is not enabled. Please run setup() first.")
        pass

    def pgn2time(self, pgn):
        pgn2time_d = {
            65199: 1.00,  # Fuel consumption (gas)
            65248: 1.00,  # Trip distance
            65266: 1.00,  # Fuel economic
            65276: 1.00,  # Dash display: Fuel level...
            65201: 1.00,  # ECU information
            65202: 1.00,  # Fuel information
            65244: 1.00,  # Idle fuel and time
            65253: 1.00,  # Total engine hours and revolutions
            65255: 1.00,  # Vehicle hours
            65257: 1.00,  # Fuel consumption information (Liquid)
            65263: 1.00,  # Engine Oil level, might not be useful...
            61444: 1.00,  # ECC1: engine performance
            # 65262: 1.10,  # Uncomment if needed
            # 65265: 1.00,  # Uncomment if needed
            # 65256: 1.20,  # Uncomment if needed
            # 65266: 1.30,  # Uncomment if needed
        }
        return pgn2time_d.get(pgn, 1.00)  # Default to 1.00 seconds if PGN not found

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
    
        parsed_j1939_data = self.parser.parse_data(pgn, data)
        parsed_j1939_data['timestamp'] = timestamp
        # if parsed_j1939_data['code'] == 0:
        logger.debug(f"Parsed J1939 Data: {parsed_j1939_data}")
    

    def send_periodic_requests(self, time_pgn_vec):
        """
        Periodically send requests for specific PGNs.
        """
        def request_loop():
            while self.running:
                for interval, pgn in time_pgn_vec:
                    self.ca.request_parameter_group(pgn)
                    logger.info(f"Sent request for PGN: {pgn}")
                    time.sleep(interval)

        self.running = True
        threading.Thread(target=request_loop, daemon=True).start()

    def close(self):
        """
        Stop the listener and periodic requests.
        """
        self.ca.stop()
        self.ecu.disconnect()
        self.enable = False
        logger.info("J1939Listener stopped.")

def setup_can_interface():
    """
    Set up the CAN interface 'can0' with a bitrate of 250000. 
    
    Note that if we want to be compatible with ISO small car OBD-II protocol, we might need to add a function to automatically detect the OBD protocol. But for now, let's focus on heavy vehicles using J1939 over CAN.
    """

    cmd = "sudo ip link set can0 down && sudo ip link set can0 up type can bitrate 250000"
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
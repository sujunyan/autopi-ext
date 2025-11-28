import logging
import time
import can
import j1939
from j1939Parser import J1939Parser

logging.getLogger('j1939').setLevel(logging.DEBUG)
logging.getLogger('can').setLevel(logging.DEBUG)

# compose the name descriptor for the new ca
name = j1939.Name(
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

# create the ControllerApplications
ca = j1939.ControllerApplication(name, 128)


def ca_receive(priority, pgn, source, timestamp, data):
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
    
    # Instantiate the parser
    parser = J1939Parser()
    parsed_j1939_data = parser.parse_data(pgn, data)
    parsed_j1939_data['timestamp'] = timestamp
    # if parsed_j1939_data['code'] == 0:
    print(f"Parsed J1939 Data: {parsed_j1939_data}")


def request_pgn(cookie, pgn):
    """
    Given the pgn, generate a function that send the requests of such pgn.

    Used to easily create new callback functions
    """
    # wait until we have our device_address
    if ca.state != j1939.ControllerApplication.State.NORMAL:
        # returning true keeps the timer event active
        return True

    print(f"Timer with pgn {pgn}")

    # def send_request(self, data_page, pgn, destination):

    # create data with 8 bytes
    data = [j1939.ControllerApplication.FieldValue.NOT_AVAILABLE_8] * 8

    destination = 0x00 # address for engine.
    data_page = 0
    ca.send_request(data_page, pgn, destination)
    return True


def main():
    print("Initializing")

    # create the ElectronicControlUnit (one ECU can hold multiple ControllerApplications)
    ecu = j1939.ElectronicControlUnit()

    # Connect to the CAN bus
    # Arguments are passed to python-can's can.interface.Bus() constructor
    # (see https://python-can.readthedocs.io/en/stable/bus.html).
    ecu.connect(bustype='socketcan', channel='can0')
    # ecu.connect(bustype='socketcan', channel='vcan0')
    # ecu.connect(bustype='kvaser', channel=0, bitrate=250000)
    # ecu.connect(bustype='pcan', channel='PCAN_USBBUS1', bitrate=250000)
    # ecu.connect(bustype='ixxat', channel=0, bitrate=250000)
    # ecu.connect(bustype='vector', app_name='CANalyzer', channel=0, bitrate=250000)
    # ecu.connect(bustype='nican', channel='CAN0', bitrate=250000)
    # ecu.connect('testchannel_1', bustype='virtual')

    # add CA to the ECU
    ecu.add_ca(controller_application=ca)
    ca.subscribe(ca_receive)
    # callback every 0.5s

    time_pgn_vec = [
        (0.500, 61444) 
    ]


    # 65265: to get the wheel based vehicle speed
    # ca.add_timer(0.500, lambda cookie : request_pgn(cookie, 65265) )

    # 61444: ECC1, we can get the engine information like engine speed...
    # ca.add_timer(0.500, lambda cookie : request_pgn(cookie, 61444) )

    # 65256: to get the pitch/altitude information
    # ca.add_timer(0.500, lambda cookie : request_pgn(cookie, 65256) )

    # 65266: to get the fuel rate information
    # ca.add_timer(0.500, lambda cookie : request_pgn(cookie, 65266) )
    
    # 65217: to get the Trip fuel information
    # ca.add_timer(0.500, lambda cookie : request_pgn(cookie, 65217) )

    # callback every 5s
    # ca.add_timer(5, ca_timer_callback2)
    # by starting the CA it starts the address claiming procedure on the bus
    ca.start()

    time.sleep(100)

    print("Deinitializing")
    ca.stop()
    ecu.disconnect()

if __name__ == '__main__':
    main()

# Example Usage of J1939Parser (for testing purposes, can be removed later)


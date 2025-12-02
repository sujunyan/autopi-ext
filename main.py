import logging
import time
import can
import j1939
from j1939Parser import J1939Parser
from logger import config_logger, logger

# Configure logging for j1939 and can libraries
logging.getLogger('j1939').setLevel(logging.DEBUG)
logging.getLogger('can').setLevel(logging.DEBUG)


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
    logger.info(f"Parsed J1939 Data: {parsed_j1939_data}")


def request_pgn(cookie, pgn, ca):
    """
    Given the pgn, generate a function that send the requests of such pgn.

    Used to easily create new callback functions
    """
    # wait until we have our device_address
    if ca.state != j1939.ControllerApplication.State.NORMAL:
        # returning true keeps the timer event active
        return True

    logger.debug(f"Timer with pgn {pgn}")

    # def send_request(self, data_page, pgn, destination):

    # create data with 8 bytes
    data = [j1939.ControllerApplication.FieldValue.NOT_AVAILABLE_8] * 8

    destination = 0x00 # address for engine.
    data_page = 0
    ca.send_request(data_page, pgn, destination)
    return True

def setup_can_interface():
    cmd = "sudo ip link set can0 down && sudo ip link set can0 up type can bitrate 250000"


def main():
    config_logger(logging.DEBUG)

    logger.info("Initializing J1939 Controller Application")

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
    error_cnt = 0
    max_error_cnt = 10

    while True:
        ecu = None
        ca = None
        if error_cnt > 0:
            if error_cnt >= max_error_cnt:
                logger.error("Maximum error count reached. Exiting application.")
                break
            logger.debug(f"Restarting J1939 Controller Application (error count: {error_cnt})")
        try:
            logger.info("Attempting to connect to CAN bus...")
            # create the ElectronicControlUnit (one ECU can hold multiple ControllerApplications)
            ecu = j1939.ElectronicControlUnit()
            # create the ControllerApplications
            ca = j1939.ControllerApplication(name, 128)

            # Connect to the CAN bus
            ecu.connect(bustype='socketcan', channel='can0')
            # add CA to the ECU
            ecu.add_ca(controller_application=ca)
            ca.subscribe(ca_receive)

            time_pgn_vec = [
                (0.500, 61444),
                (0.600, 65265),
                (0.700, 65256),
                (4.00, 65266),
                (5.00, 65217)
            ]

            for time_interval, pgn in time_pgn_vec:
                ca.add_timer(time_interval, lambda cookie, pgn=pgn: request_pgn(cookie, pgn, ca))

            ca.start()
            logger.info("J1939 Controller Application started and connected.")

            while ca is not None and ca.state != j1939.ControllerApplication.State.STOPPED:
                time.sleep(1)  # Keep the main thread alive

        except can.exceptions.CanError as e:
            logger.error(f"CAN bus error: {e}", exc_info=True)
            error_cnt += 1
            logger.info("Retrying connection in 5 seconds...")
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info("J1939 Controller Application stopped by user.")
            break
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}", exc_info=True)
            logger.info("Restarting J1939 Controller Application in 5 seconds...")
            error_cnt += 1
            time.sleep(5)
        finally:
            if ca is not None and ca.state != j1939.ControllerApplication.State.STOPPED:
                ca.stop()
            if ecu is not None and ecu.is_connected:
                ecu.disconnect()
            logger.info("J1939 Controller Application deinitialized.")



if __name__ == '__main__':
    main()

# Example Usage of J1939Parser (for testing purposes, can be removed later)


import logging
import time
import can
import j1939
from logger import config_logger, logger

# Configure logging for j1939 and can libraries
logging.getLogger('j1939').setLevel(logging.DEBUG)
logging.getLogger('can').setLevel(logging.DEBUG)



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
    # data = [j1939.ControllerApplication.FieldValue.NOT_AVAILABLE_8] * 8

    ## Note that in default ca.send_request function, the data length 3 instead of 8. We need to mannually send the raw data
    ## see also the function defined in controller_application.py:280
    data = [(pgn & 0xFF), ((pgn >> 8) & 0xFF), ((pgn >> 16) & 0xFF), 0x00, 0x00, 0x00, 0x00, 0x00]

    destination = 0x00 # address for engine.
    data_page = 0
    priority = 6  # default priority for request PGN
    ca.send_pgn(data_page, 
            (j1939.ParameterGroupNumber.PGN.REQUEST >> 8) & 0xFF, 
            destination & 0xFF, 
            priority, 
            data)
    return True



def main():
    config_logger(logging.DEBUG)

    logger.info("Initializing J1939 Controller Application")

    # compose the name descriptor for the new ca
    
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
            ca = j1939.ControllerApplication(name, 0xF9)

            # Connect to the CAN bus
            ecu.connect(bustype='socketcan', channel='can0')
            # add CA to the ECU
            ecu.add_ca(controller_application=ca)
            ca.subscribe(ca_receive)
            # 
            time_pgn_vec = [
                (1.00, 61444), # ECC1: engine performance
                (1.00, 65199), # Fuel consumption (gas)
                (1.00, 65248), # Trip distance
                (1.00, 65266), # Fuel economic
                (1.00, 65276), # Dash display: Fuel level...
                (1.00, 65201), # ECU information
                (1.00, 65202), # Fuel information
                (1.00, 65244), # Idle fuel and time
                (1.00, 65253), # Total engine hours and revolutions
                (1.00, 65255), # Vehicle hours
                (1.00, 65257), # Fuel consumption information (Liquid)
                (1.00, 65263), # Engine Oil level, might not be useful...
                # (1.10, 65262),
                # (1.00, 65265),
                # (1.20, 65256),
                # (1.30, 65266),
                # (1.40, 65217)
            ]

            for time_interval, pgn in time_pgn_vec:
                ca.add_timer(time_interval, lambda cookie, pgn=pgn: request_pgn(cookie, pgn, ca))

            ca.start()
            logger.info("J1939 Controller Application started and connected.")

            while ca is not None:
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
            if ca is not None:
                ca.stop()
            if ecu is not None:
                ecu.disconnect()
            logger.info("J1939 Controller Application deinitialized.")

if __name__ == '__main__':
    main()

# Example Usage of J1939Parser (for testing purposes, can be removed later)


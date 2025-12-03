import logging
import time
import can
import j1939
from logger import config_logger, logger
from j1939Listener import J1939Listener 

# Configure logging for j1939 and can libraries
logging.getLogger('j1939').setLevel(logging.DEBUG)
logging.getLogger('can').setLevel(logging.DEBUG)


def main():
    config_logger(logging.DEBUG)

    logger.info("Initializing J1939 Controller Application")

    # compose the name descriptor for the new ca
    
    try:
        j1939_listener = J1939Listener()    
        j1939_listener.setup()
        j1939_listener.main_loop()
    except can.exceptions.CanError as e:
        logger.error(f"CAN bus error: {e}", exc_info=True)
        # logger.info("Retrying connection in 5 seconds...")
        # time.sleep(5)
    except KeyboardInterrupt:
        logger.info("J1939 Controller Application stopped by user.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        # logger.info("Restarting J1939 Controller Application in 5 seconds...")
        time.sleep(5)
    finally:
        if 'j1939_listener' in locals():
            j1939_listener.close()
        logger.info("J1939 Controller Application deinitialized.")

if __name__ == '__main__':
    main()

# Example Usage of J1939Parser (for testing purposes, can be removed later)


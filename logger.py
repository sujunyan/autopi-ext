import logging
import logging.handlers
import os

logger = logging.getLogger("e2pilot_autopi")


def config_logger(level=logging.INFO):
    """Configure the logger for the j1939_listener module."""
    log_directory = "logs"
    log_filename = "e2pilot_autopi.log"
    log_filepath = os.path.join(log_directory, log_filename)
    os.makedirs(log_directory, exist_ok=True)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    rotate_handler = logging.handlers.RotatingFileHandler(
        log_filepath,
        maxBytes=3 * 1024 * 1024,
        backupCount=10
    )
    rotate_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(rotate_handler)
    logger.addHandler(console_handler)
    logger.setLevel(level)

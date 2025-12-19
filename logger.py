

import logging
import logging.handlers
import os

logger = logging.getLogger("e2pilot_autopi")


def config_logger(level=logging.INFO):
    """Configure the logger for the j1939_listener module."""
    log_directory = "logs"
    log_filename = "j1939_listener.log"
    log_filepath = os.path.join(log_directory, log_filename)
    os.makedirs(log_directory, exist_ok=True)

    rotate_handler = logging.handlers.RotatingFileHandler(
        log_filepath,
        maxBytes= 10 * 1024 * 1024,  # 1 MB
        backupCount=5          # Keep 5 historical log files
    )
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    rotate_handler.setFormatter(formatter)
    logger.addHandler(rotate_handler)
    logger.setLevel(level)

from datetime import datetime
import logging
import logging.handlers
import os

logger = logging.getLogger("e2pilot_autopi")


def config_logger(level=logging.INFO):
    """Configure the logger for the j1939_listener module."""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    today_string = datetime.now().strftime("%Y%m%d")

    log_directory = "logs"
    log_directory = os.path.join(log_directory, today_string)

    os.makedirs(log_directory, exist_ok=True)

    info_log_filepath = os.path.join(log_directory, f"e2pilot_info_{timestamp}.log")
    debug_log_filepath = os.path.join(log_directory, f"e2pilot_debug_{timestamp}.log")

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Info handler
    info_handler = logging.handlers.RotatingFileHandler(
        info_log_filepath,
        maxBytes=1 * 1024 * 1024,
        backupCount=10
    )
    info_handler.setFormatter(formatter)
    info_handler.setLevel(logging.INFO)

    # Debug handler
    debug_handler = logging.handlers.RotatingFileHandler(
        debug_log_filepath,
        maxBytes= 3 * 1024 * 1024,
        backupCount=10
    )
    debug_handler.setFormatter(formatter)
    debug_handler.setLevel(logging.DEBUG)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    logger.addHandler(info_handler)
    logger.addHandler(debug_handler)
    logger.addHandler(console_handler)

    # Ensure the logger itself is at least at the lowest handler level
    logger.setLevel(logging.DEBUG)

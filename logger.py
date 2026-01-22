from datetime import datetime
import logging
import logging.handlers
import os

logger = logging.getLogger("e2pilot_autopi")

class ColorFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: "\033[36m",    # Cyan
        logging.INFO: "\033[32m",     # Green
        logging.WARNING: "\033[33m",  # Yellow
        logging.ERROR: "\033[31m",    # Red
        logging.CRITICAL: "\033[41m", # Red background
    }
    RESET = "\033[0m"
    GREY = "\033[90m"

    def format(self, record):
        color = self.COLORS.get(record.levelno, self.RESET)
        header = f"{self.GREY}{self.formatTime(record)}{self.RESET} - {record.name} - {color}{record.levelname}{self.RESET}"
        header = f"{self.GREY}{self.formatTime(record)}{self.RESET} - {color}{record.levelname}{self.RESET}"
        message = record.getMessage()
        return f"{header} - {message}"


def config_logger(level=logging.INFO):
    """Configure the logger for the j1939_listener module."""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    today_string = datetime.now().strftime("%Y%m%d")

    log_directory = "logs"
    log_directory = os.path.join(log_directory, today_string)

    os.makedirs(log_directory, exist_ok=True)

    info_log_name = f"e2pilot_info_{timestamp}.log"
    info_log_filepath = os.path.join(log_directory, info_log_name)
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
        backupCount=20
    )
    debug_handler.setFormatter(formatter)
    debug_handler.setLevel(logging.DEBUG)

    # Console handler
    console_handler = logging.StreamHandler()
    # console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    # Use ColorFormatter for console handler
    console_formatter = ColorFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)

    logger.addHandler(info_handler)
    logger.addHandler(debug_handler)
    logger.addHandler(console_handler)

    # Ensure the logger itself is at least at the lowest handler level
    logger.setLevel(logging.DEBUG)

    ## 
    # Create or update symlink to latest log
    symlink_path = os.path.join(log_directory, "0.info-latest.log")
    try:
        if os.path.islink(symlink_path) or os.path.exists(symlink_path):
            os.remove(symlink_path)
        os.symlink(info_log_name, symlink_path)
    except Exception as e:
        print(f"Could not create symlink for latest log: {e}")

import math
import subprocess
import logging

logger = logging.getLogger("e2pilot_autopi")

def haversine(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    """
    # convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    r = 6371000  # Radius of earth in meters.
    return c * r

def setup_can_interface(can_channel, can_rate):
    # can_channel = self.can_channel
    # can_rate = 250000
    # can_rate = self.can_rate 
    cmd = f"sudo ip link set {can_channel} down && sudo ip link set {can_channel} up type can bitrate {can_rate} sample-point 0.8"
    try:
        logger.info("setting up can interface...")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            logger.info("can interface setup successfully.")
            return True
        else:
            logger.error(f"failed to set up can interface: {result.stderr}")
            return False
    except Exception as e:
        logger.exception(f"unexpected error setting up can interface: {e}")
        return False
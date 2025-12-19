
import serial
import logging
import time
import glob
import random

logger = logging.getLogger("e2pilot_autopi")

def find_nextion_serial_port(baud_rate=115200, timeout=2):
    """
    Attempts to connect to all /dev/ttyUSB* ports, sends a Nextion display 'dp'
    query command, and checks for an expected response (containing 'dp=' and
    the Nextion end bytes).
    Args:
        baud_rate (int): The serial port baud rate (common for Nextion: 9600 or 115200).
        timeout (int): The read timeout for each serial port operation (in seconds).
    Returns:
        str: The path to the correct serial port if found, otherwise None.
    """
    serial_ports = glob.glob('/dev/ttyUSB*')
    logger.debug(f"Found potential serial devices: {serial_ports}")
    # Nextion command and response end bytes
    NEXTION_END_BYTES = b'\xff\xff\xff'
    # Test command: query current display page. 'dp' followed by end bytes.
    # TEST_COMMAND = b'prints dp,1' + NEXTION_END_BYTES
    TEST_COMMAND = b'sendme' + NEXTION_END_BYTES
    for port in serial_ports:
        logger.debug(f"\nAttempting to connect to port: {port}")
        ser = None
        try:
            # Important setup: rtscts=False, dtr=False to avoid interfering with Nextion startup
            ser = serial.Serial(port, baud_rate, timeout=timeout)
            time.sleep(1)  # Give the device and serial port some time to initialize
            # Clear input buffer to avoid reading stale data from previous operations
            ser.flushInput()
            ser.write(TEST_COMMAND)
            logger.debug(f"Sent test command: {TEST_COMMAND!r}") # !r for readable byte string representation
            start_time = time.time()
            received_data = b''
            # Wait until end bytes are received or timeout occurs
            while time.time() - start_time < timeout + 1: # Extended read time slightly
                bytes_to_read = ser.in_waiting
                if bytes_to_read > 0:
                    received_data += ser.read(bytes_to_read)
                    if NEXTION_END_BYTES in received_data:
                        logger.debug(f"Got received data {received_data} len={len(received_data)}")
                        if TEST_COMMAND in received_data:
                            logger.debug(f"Got looped data {received_data}")
                        elif received_data[0] == 0x66:
                            logger.debug(f"Got seems good data: {received_data}")
                            return port
                        # Check if the response contains the expected 'dp=' format
                        # if b'dp=' in received_data:
                        #     logger.debug(f">> Received expected response on port {port}: {received_data!r}")
                        #     return port
                        # else:
                        #     # Received end bytes, but content does not match 'dp='.
                        #     # Could be another device or an error response.
                        #     logger.debug(f"Port {port} received data but not the expected response: {received_data!r}")
                        #     break # Exiting as response doesn't match Nextion 'dp'
                time.sleep(0.05) # Short delay to avoid busy-waiting
            if received_data:
                logger.debug(f"Port {port} returned data with unexpected response: {received_data!r}")
            else:
                logger.debug(f"Port {port} did not return any data.")
        except serial.SerialException as e:
            logger.debug(f"Failed to open or communicate with port {port}: {e}")
        except Exception as e:
            logger.debug(f"An unknown error occurred on port {port}: {e}")
        finally:
            if ser and ser.is_open:
                ser.close()
                logger.debug(f"Closed port {port}")
    logger.debug("No correct Nextion serial display device found.")
    return None

class DisplayManager:
    def __init__(self):
        self.setup_serial()

    def setup_serial(self):
        logger.debug("Setup serial port for display manager")
        ser_port = find_nextion_serial_port()
        self.last_send_suggest_ts = time.time()
        if ser_port is not None:
            self.ser = serial.Serial(port=ser_port, baudrate=115200, timeout=5)
            # self.ser = seri
        else:
            self.ser = None
        # self.ser = serial.Serial(port="/dev/ttyUSB3",baudrate=115200,timeout=5)

    @property
    def is_able(self):
        flag = self.ser != None

        return flag

    def send_cmd(self, cmd):
        if self.enable:
            result = self.ser.write(cmd.encode("utf-8"))
            self.ser.write(bytes.fromhex('ff ff ff'))

    def set_suggest_speed(self, speed):
        speed = int(speed)

        # set the picture number of the display
        pic_num = speed - 60
        if pic_num <= 0:
            pic_num = 1

        logger.debug(f"Set suggest speed {speed}")
        self.send_cmd(f"speedmeter_bg.pic={pic_num}")

        
    def set_speed(self, speed):
        speed = int(speed)
        self.send_cmd(f"speed_num.val={speed}")

        min_angle = -45
        max_angle = 225

        angle= (speed  / 120) * (max_angle-min_angle) + min_angle
        if angle < 0:
            angle += 360
        angle = int(angle)

        logger.debug(f"writing speed: {speed} angle: {angle}")
        self.send_cmd(f"speedmeter.val={angle}")
        if abs(time.time() - self.last_send_suggest_ts) > 0.1:
            # delta_v = random.randint(-5, 5)
            # self.set_suggest_speed(speed + delta_v)
            self.set_suggest_speed(speed)
            self.last_send_suggest_ts = time.time()

    
    def close(self):
        if self.ser is not None:
            self.ser.close()
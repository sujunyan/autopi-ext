
import serial
import logging
import time
import glob
import random

logger = logging.getLogger("e2pilot_autopi")

def find_nextion_serial_port(baud_rate=115200, timeout=1):
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
    logger.info(f"Found potential serial devices: {serial_ports}")
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
            time.sleep(0.2)  # Give the device and serial port some time to initialize
            # Clear input buffer to avoid reading stale data from previous operations
            ser.flushInput()
            ser.write(TEST_COMMAND)
            logger.debug(f"Sent test command: {TEST_COMMAND!r}") # !r for readable byte string representation
            start_time = time.time()
            received_data = b''
            # Wait until end bytes are received or timeout occurs
            while time.time() - start_time < timeout + 0.25: # Extended read time slightly
                bytes_to_read = ser.in_waiting
                if bytes_to_read > 0:
                    received_data += ser.read(bytes_to_read)
                    if NEXTION_END_BYTES in received_data:
                        logger.debug(f"Got received data {received_data} len={len(received_data)}")
                        if TEST_COMMAND in received_data:
                            logger.debug(f"Got looped data {received_data}")
                        elif received_data[0] == 0x66:
                            logger.info(f"Got seems good data: {received_data}. Return the port.")
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
            logger.error(f"Failed to open or communicate with port {port}: {e}")
        except Exception as e:
            logger.error(f"An unknown error occurred on port {port}: {e}")
        finally:
            if ser and ser.is_open:
                ser.close()
                logger.debug(f"Closed port {port}")
    logger.warning("No correct Nextion serial display device found.")
    return None

class DisplayManager:
    def __init__(self):
        pass

    def setup(self):
        self.setup_serial()
        time.sleep(0.2)
        self.reset_display()
    
    def reset_display(self):
        if self.enable:
            self.set_grade(0.0) 
            self.set_follow_range(0.0)
            self.set_follow_rate(0.0)
            self.set_distance(0.0)
            self.set_suggest_speed(60.0)
            self.set_speed(60.0)

    def setup_serial(self):
        logger.info("Setup serial port for display manager")
        ser_port = find_nextion_serial_port()
        self.last_send_suggest_ts = time.time()
        if ser_port is not None:
            self.ser = serial.Serial(port=ser_port, baudrate=115200, timeout=5)
            # self.ser = seri
        else:
            self.ser = None
        # self.ser = serial.Serial(port="/dev/ttyUSB3",baudrate=115200,timeout=5)

    @property
    def enable(self):
        if hasattr(self, 'ser'):
            flag = (self.ser != None)
        else:
            flag = False

        return flag

    def send_cmd(self, cmd):
        if self.enable:
            result = self.ser.write(cmd.encode("utf-8"))
            self.ser.write(bytes.fromhex('ff ff ff'))
            # logger.debug(f"Sent cmd: {cmd}")

    def set_grade(self, grade):
        grade = int(grade * 10)
        self.send_cmd(f"grade.val={grade}")

    def set_distance(self, distance):
        # Convert to decimeters
        distance = int(distance * 10)
        self.send_cmd(f"distance.val={distance}")

    def set_follow_rate(self, rate):
        rate = int(rate * 10)
        self.send_cmd(f"follow_rate.val={rate}")

    def set_follow_range(self, distance):
        distance = int(distance * 10)
        self.send_cmd(f"follow_range.val={distance}")

    def set_suggest_speed(self, speed):
        speed = int(speed)

        # set the picture number of the display
        pic_num = speed - 4
        sug_speed = speed
        if pic_num <= 0 or (pic_num > 111):
            pic_num = 0
            sug_speed = 0

        # logger.debug(f"Set suggest speed {speed}")
        self.send_cmd(f"speedmeter_bg.pic={pic_num}")
        self.send_cmd(f"suggest_speed.val={sug_speed}")

        
    def set_speed(self, speed):
        if speed == None:
            logger.warning("Got a None speed in display manager.")
            return
        if not self.enable:
            return
        
        speed = int(speed)
        self.send_cmd(f"speed_num.val={speed}")

        min_angle = -45
        max_angle = 225

        angle= (speed  / 120) * (max_angle-min_angle) + min_angle
        if angle < 0:
            angle += 360
        angle = int(angle)

        # logger.debug(f"writing speed: {speed} angle: {angle}")
        self.send_cmd(f"speedmeter.val={angle}")
        if abs(time.time() - self.last_send_suggest_ts) > 0.1:
            pass
            # delta_v = random.randint(-5, 5)
            # self.set_suggest_speed(speed + delta_v)
            # self.set_suggest_speed(speed)
            # self.last_send_suggest_ts = time.time()

    
    def close(self):
        logger.info("[display manager] Closing...")
        self.reset_display()
        time.sleep(0.2)
        if self.ser is not None and self.ser.is_open:
            self.ser.close()
        logger.info("[display manager] Closed.")
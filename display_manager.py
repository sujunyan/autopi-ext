
import serial
import logging
import time
import glob

logger = logging.getLogger("j1939_listener")

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
    print(f"Found potential serial devices: {serial_ports}")
    # Nextion command and response end bytes
    NEXTION_END_BYTES = b'\xff\xff\xff'
    # Test command: query current display page. 'dp' followed by end bytes.
    TEST_COMMAND = b'sendme' + NEXTION_END_BYTES
    for port in serial_ports:
        print(f"\nAttempting to connect to port: {port}")
        ser = None
        try:
            # Important setup: rtscts=False, dtr=False to avoid interfering with Nextion startup
            ser = serial.Serial(port, baud_rate, timeout=timeout)
            time.sleep(1)  # Give the device and serial port some time to initialize
            # Clear input buffer to avoid reading stale data from previous operations
            ser.flushInput()
            ser.write(TEST_COMMAND)
            print(f"Sent test command: {TEST_COMMAND!r}") # !r for readable byte string representation
            start_time = time.time()
            received_data = b''
            # Wait until end bytes are received or timeout occurs
            while time.time() - start_time < timeout + 1: # Extended read time slightly
                bytes_to_read = ser.in_waiting
                if bytes_to_read > 0:
                    received_data += ser.read(bytes_to_read)
                    if NEXTION_END_BYTES in received_data:
                        print(f"Got received data {received_data} len={len(received_data)}")
                        if TEST_COMMAND in received_data:
                            print(f"Got looped data {received_data}")
                        elif received_data[0] == 0x66:
                            print(f"Got seems good data: {received_data}")
                            return port
                        # Check if the response contains the expected 'dp=' format
                        # if b'dp=' in received_data:
                        #     print(f">> Received expected response on port {port}: {received_data!r}")
                        #     return port
                        # else:
                        #     # Received end bytes, but content does not match 'dp='.
                        #     # Could be another device or an error response.
                        #     print(f"Port {port} received data but not the expected response: {received_data!r}")
                        #     break # Exiting as response doesn't match Nextion 'dp'
                time.sleep(0.05) # Short delay to avoid busy-waiting
            if received_data:
                print(f"Port {port} returned data with unexpected response: {received_data!r}")
            else:
                print(f"Port {port} did not return any data.")
        except serial.SerialException as e:
            print(f"Failed to open or communicate with port {port}: {e}")
        except Exception as e:
            print(f"An unknown error occurred on port {port}: {e}")
        finally:
            if ser and ser.is_open:
                ser.close()
                print(f"Closed port {port}")
    print("No correct Nextion serial display device found.")
    return None

class DisplayManager:
    def __init__(self):
        self.setup_serial()

    def setup_serial(self):
        logger.debug("Setup serial port for display manager")
        ser_port = find_nextion_serial_port()
        if ser_port is not None:
            self.ser = serial.Serial(port=ser_port, baudrate=115200, timeout=5)
            # self.ser = seri
        else:
            self.ser = None
        # self.ser = serial.Serial(port="/dev/ttyUSB3",baudrate=115200,timeout=5)

    def write_speed(self, speed):
        ser = self.ser
        speed = int(speed)
        result=ser.write(f"speed_num.val={speed}".encode("utf-8"))
        ser.write(bytes.fromhex('ff ff ff'))

        min_angle = -45
        max_angle = 225

        angle= (speed  / 120) * (max_angle-min_angle) + min_angle
        if angle < 0:
            angle += 360
        angle = int(angle)

        print(f"writing speed: {speed} angle: {angle}")
        result=ser.write(f"speedmeter.val={angle}".encode("utf-8"))
        ser.write(bytes.fromhex('ff ff ff'))
    
    def close():
        if self.ser is not None:
            self.ser.close()
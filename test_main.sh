#!/bin/bash

# Script to test the functionality of main.py

# Ensure vcan0 is set up
if ! ip link show vcan0 &> /dev/null; then
    echo "vcan0 interface not found. Please run create_vcan.sh first."
    exit 1
fi

echo "Starting main.py in the background..."
python3 main.py &
MAIN_PID=$!

# Give main.py some time to initialize and start sending/receiving
sleep 5

echo "Sending a test CAN message to vcan0..."
# This example sends a PGN 61444 (Engine Speed) message
# Data: 0x40 0x1F (representing 1000 RPM, little endian)
# The main.py script is configured to request PGN 61444, so it should process this.
# We are simulating a response from another ECU.
# cansend vcan0 0CFF0000#000000401F000000
cansend vcan0 18F00400#0000001234000000

sleep 2

echo "Checking if main.py processed the message (look for output in the console where main.py is running or in its logs if redirected)."
echo "You should see 'Parsed J1939 Data: {'Engine Speed': '1666.25 rpm'}' or similar in main.py's output."

echo "Killing main.py..."
kill $MAIN_PID

echo "Test script finished."

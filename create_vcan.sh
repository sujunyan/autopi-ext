#!/bin/bash

# Script to create a virtual CAN interface (vcan) for testing

# Check if the vcan module is loaded
if ! lsmod | grep -q vcan; then
    echo "Loading vcan module..."
    sudo modprobe vcan
    if [ $? -ne 0 ]; then
        echo "Error: Failed to load vcan module. Please ensure it's available on your system."
        exit 1
    fi
fi

# Check if vcan0 already exists
if ip link show vcan0 &> /dev/null; then
    echo "vcan0 interface already exists. Bringing it down and deleting it..."
    sudo ip link set dev vcan0 down
    sudo ip link delete vcan0 type vcan
    if [ $? -ne 0 ]; then
        echo "Error: Failed to remove existing vcan0 interface."
        exit 1
    fi
fi

echo "Creating vcan0 interface..."
sudo ip link add dev vcan0 type vcan
if [ $? -ne 0 ]; then
    echo "Error: Failed to create vcan0 interface."
    exit 1
fi

echo "Bringing vcan0 interface up..."
sudo ip link set up vcan0
if [ $? -ne 0 ]; then
    echo "Error: Failed to bring vcan0 interface up."
    exit 1
fi

echo "vcan0 virtual CAN interface created and brought up successfully."
echo "You can now use 'candump vcan0' to monitor traffic or 'cansend vcan0 123#11223344' to send messages."

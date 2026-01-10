#!/bin/bash
SESSION="e2pilot"
SCRIPT="/home/pi/autopi-ext/e2pilot_main.py"
# sleep 10  # Wait 10 seconds for devices to initialize
tmux new-session -d -s $SESSION "sleep 3 && cd /home/pi/autopi-ext/ && python3 e2pilot_main.py"
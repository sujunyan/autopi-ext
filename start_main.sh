#!/bin/bash
SESSION="e2pilot"
SCRIPT="/home/pi/autopi-ext/e2pilot_main.py"
tmux new-session -d -s $SESSION "python3 $SCRIPT"
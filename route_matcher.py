
import paho.mqtt.client as mqtt
import json, time, threading, os, logging, csv
from datetime import datetime
from pathlib import Path


logger = logging.getLogger("e2pilot_autopi")

current_dir = Path(__file__).resolve().parent
data_dir = current_dir.joinpath("data/opt_route")

class RouteMatcher:
    def __init__(self):
        pass
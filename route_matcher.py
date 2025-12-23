import json
import logging
import math
import os
from pathlib import Path

from utils import haversine

logger = logging.getLogger("e2pilot_autopi")

current_dir = Path(__file__).resolve().parent
g_data_dir = current_dir.joinpath("data/opt_route")

class RouteMatcher:
    def __init__(self, data_dir=""):
        if isinstance(data_dir, Path):
            self.data_dir = data_dir
        else:
            self.data_dir = g_data_dir.joinpath(data_dir)
        self.route_data = None
        self.pt = None

    def load_route_from_json(self, filename):
        filepath = self.data_dir.joinpath(filename)
        with open(filepath, "r") as f:
            self.route_data = json.load(f)

    def update_pt(self, lat, lon):
        """
        Update the current closest point based on the given latitude and longitude.
        """
        pt = self.find_closest_speedplan_point(lat, lon)
        if pt:
            self.pt = pt
        return self.pt

    def find_closest_speedplan_point(self, lat, lon):
        if not self.route_data:
            return None

        closest_point = None
        min_distance = float("inf")

        kleg, kstep, kpoint = 0, 0, 0
        for (ileg, leg) in enumerate(self.route_data.get("legs", [])):
            for (istep, step) in enumerate(leg.get("steps", [])):
                for (ipoint, point) in enumerate(step.get("speedplan", [])):
                    p_lat = point.get("lat")
                    p_lon = point.get("lon")
                    if p_lat is not None and p_lon is not None:
                        # Use Haversine distance instead of Euclidean
                        distance = haversine(lat, lon, p_lat, p_lon)
                        if distance < min_distance:
                            min_distance = distance
                            closest_point = point
                            kleg, kstep, kpoint = ileg, istep, ipoint
        logger.debug(f"Got closest pt {(kleg, kstep, kpoint)} with distance {min_distance:.1f} meters")
        return closest_point


def _test_route_matcher():
    # Create a dummy data directory for testing
    test_data_dir = Path("./test_data")
    test_data_dir.mkdir(exist_ok=True)

    # Create a dummy route file
    with open(test_data_dir.joinpath("test_route.json"), "w") as f:
        f.write(
            """
        {
            "legs": [
                {
                    "steps": [
                        {
                            "speedplan": [
                                {"lat": 34.052235, "lon": -118.243683, "speed": 10},
                                {"lat": 34.052235, "lon": -118.243684, "speed": 20},
                                {"lat": 34.052236, "lon": -118.243685, "speed": 30}
                            ]
                        }
                    ]
                }
            ]
        }
        """
        )

    matcher = RouteMatcher(test_data_dir)
    matcher.load_route_from_json("test_route.json")

    # Test case 1: Point exactly on a speedplan point
    closest = matcher.find_closest_speedplan_point(34.052235, -118.243683)
    print(f"Test 1 (exact match): {closest}")
    assert closest == {"lat": 34.052235, "lon": -118.243683, "speed": 10}

    # Test case 2: Point close to a speedplan point
    closest = matcher.find_closest_speedplan_point(34.052235, -118.2436835)
    print(f"Test 2 (close match): {closest}")
    assert closest == {"lat": 34.052235, "lon": -118.243683, "speed": 10}

    # Test case 3: Point closer to the second speedplan point
    closest = matcher.find_closest_speedplan_point(34.052235, -118.2436845)
    print(f"Test 3 (second point): {closest}")
    assert closest == {"lat": 34.052235, "lon": -118.243684, "speed": 20}

    # Clean up dummy data directory
    os.remove(test_data_dir.joinpath("test_route.json"))
    os.rmdir(test_data_dir)

    print("All tests passed!")


if __name__ == "__main__":
    # _test_route_matcher()
    matcher = RouteMatcher()
    matcher.load_route_from_json("test.2025-07-04.opt.JuMP.route.json")
    lat = 22.596501083333333
    lon = 113.89512528333333
    closest = matcher.find_closest_speedplan_point(lat, lon)
    print(f"Closest point to ({lat}, {lon}): {closest}")

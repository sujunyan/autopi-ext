import json
import logging
import math
import os
from pathlib import Path

from utils import haversine

logger = logging.getLogger("e2pilot_autopi")

current_dir = Path(__file__).resolve().parent
g_data_dir = current_dir.joinpath("data/opt_route")

all_route_name_vec = [
    "test.2025-07-04.opt.JuMP.route.json",
    "20251222_waichen_in.opt.JuMP.route.json",   # idx=1 from outside to back to waichen
    "20251222_waichen_out.opt.JuMP.route.json", # from waichen to go outside
    "20251223_youke_out.opt.JuMP.route.json", # idx = 3
    "20251223_youke_in.opt.JuMP.route.json", # idx = 4
    "20251223_youke_in_10hz.route.json", # idx = 5
    "20251223_youke_ont_10hz.route.json", # idx = 6
]

route_name_subset = [
    "20251222_waichen_in.opt.JuMP.route.json",   # idx=0 from outside to back to waichen
    "20251222_waichen_out.opt.JuMP.route.json", # idx=1 from waichen to go outside
    "20251223_youke_in_10hz.route.json", # idx = 2, from youke in to outside
    "20251223_youke_ont_10hz.route.json", # idx = 3
]


class RouteMatcher:
    def __init__(self, data_dir=""):
        if isinstance(data_dir, Path):
            self.data_dir = data_dir
        else:
            self.data_dir = g_data_dir.joinpath(data_dir)
        self.route_data = None
        self.pt = None
        self.current_pt_index = -1
        self.latlon = (0.0, 0.0)
        self.route_name = ""

    @property
    def route_selected(self):
        return self.route_data is not None

    def select_closest_route(self, lat, lon):
        min_dis = float("inf")
        for route_name in route_name_subset:
            (route_data, all_speedplan_points) = self.get_route_from_json(route_name)
            pt0 = all_speedplan_points[0]
            lat0, lon0 = pt0.get("lat"), pt0.get("lon")
            distance = haversine(lat, lon, lat0, lon0)
            if distance < min_dis:
                min_dis = distance
                self.route_name = route_name

        self.load_route_from_json(self.route_name)
        logger.info(f"Selected {self.route_name} with min distance {min_dis:.1f} meters.")

    def load_route_from_json(self, filename):
        (route_data, all_speedplan_points) = self.get_route_from_json(filename)
        self.route_data = route_data
        self.all_speedplan_points = all_speedplan_points
        
    def get_route_from_json(self, filename):
        filepath = self.data_dir.joinpath(filename)
        with open(filepath, "r") as f:
            route_data = json.load(f)

        all_speedplan_points = []
        for leg in self.route_data.get("legs", []):
            for step in leg.get("steps", []):
                for point in step.get("speedplan", []):
                    if point:
                        all_speedplan_points.append(point)

        return (route_data, all_speedplan_points)


    def update_pt(self, lat, lon):
        """
        Update the current closest point based on the given latitude and longitude.
        """
        # pt = self.find_closest_speedplan_point(lat, lon)
        self.pt = self.match_solution(lat, lon)
        self.latlon = (lat, lon)
        return self.pt

    def match_solution(self, lat, lon):
        """
        Match the given latitude and longitude to the closest point in the speedplan.
        
        Note that we need to make sure the layout is 

        pt1 -> gps -> pt2
        """

        max_angle = 0.0
        matched_point = None
        idx = 0

        latlon = (lat, lon)

        for i in range(len(self.all_speedplan_points)-1):
            p1 = self.all_speedplan_points[i]
            p2 = self.all_speedplan_points[i+1]

            if haversine(p1["lat"], p1["lon"], lat, lon) < 1.0:
                matched_point = p1
                idx = i
                break

            angle = self.calculate_angle(p1, p2, latlon)
            if angle > max_angle:
                max_angle = angle
                matched_point = p1
                idx = i

        logger.debug(f"Got matched point at {idx} with angle {max_angle / math.pi * 180}.")
        
        self.current_pt_index = idx

        return matched_point

    def calculate_angle(self, p1, p2, latlon):
        """
        Calculate the angle between the vector gps->p1 and gps->p2

        return angle in radians
        """
        v1 = (p1["lat"] - latlon[0], p1["lon"] - latlon[1])
        v2 = (p2["lat"] - latlon[0], p2["lon"] - latlon[1])

        dot_product = v1[0]*v2[0] + v1[1]*v2[1]
        mag_v1 = math.sqrt(v1[0]**2 + v1[1]**2)
        mag_v2 = math.sqrt(v2[0]**2 + v2[1]**2)

        if mag_v1 == 0 or mag_v2 == 0:
            return 180.0

        cos_angle = dot_product / (mag_v1 * mag_v2)
        cos_angle = max(-1.0, min(1.0, cos_angle))

        angle = math.acos(cos_angle)
        return angle


    # def find_closest_speedplan_point(self, lat, lon):

    #     closest_point = None
    #     min_distance = float("inf")

    #     kpoint = -1
    #     for (ipoint, point) in enumerate(self.all_speedplan_points):
    #         p_lat = point.get("lat")
    #         p_lon = point.get("lon")
    #         if p_lat is not None and p_lon is not None:
    #             # Use Haversine distance instead of Euclidean
    #             distance = haversine(lat, lon, p_lat, p_lon)
    #             if distance < min_distance:
    #                 min_distance = distance
    #                 closest_point = point
    #                 kpoint = ipoint

    #     if closest_point:
    #         self.current_pt_index = kpoint

    #         
    #     logger.debug(f"Got closest pt {kpoint} with distance {min_distance:.1f} meters")
    #     return closest_point

    def get_next_speedplan_point(self):
        if self.current_pt_index == -1:
            return None
        
        if self.current_pt_index < len(self.all_speedplan_points) - 1:
            return self.all_speedplan_points[self.current_pt_index + 1]
        
        return self.all_speedplan_points[self.current_pt_index]

    def get_suggest_speed_and_grade(self):
        if self.current_pt_index == -1:
            return 0.0
        if not self.route_data:
            return 0.0

        point = self.all_speedplan_points[self.current_pt_index]
        next_point = self.get_next_speedplan_point()


        sug_spd1 = point.get("veh_state", {}).get("speed", -1)
        sug_spd2 = next_point.get("veh_state", {}).get("speed", -1)

        grade1 = point.get("grade", 0.0)
        grade2 = next_point.get("grade", 0.0)

        ratio = self.get_ratio(point, next_point, self.latlon)

        spd = sug_spd1 * (1-ratio) + sug_spd2 * (ratio)
        grade = grade1 * (1-ratio) + grade2 *   (ratio)

        logger.debug(f"spd1 {sug_spd1:.2f} spd2 {sug_spd2:.2f} sug_spd {spd:.2f} ratio {ratio:.3f}")
            
        return (spd, grade)

    def get_ratio(self, point1, point2, latlon):
        """
        The two points in the speedplan might be far apart, and there might be some jumping point if the GPS frequency is high. 
        """
        lat1 = point1.get("lat")
        lon1 = point1.get("lon")

        lat2 = point2.get("lat")
        lon2 = point2.get("lon")

        if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
            return 0.0

        dist_total = haversine(lat1, lon1, lat2, lon2)
        dist_to_point1 = haversine(latlon[0], latlon[1], lat1, lon1)

        if dist_total == 0:
            return 0.0

        ratio = dist_to_point1 / dist_total
        ratio = max(0.0, min(1.0, ratio))
        return ratio


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

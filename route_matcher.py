import json
import logging
import math
import os
from pathlib import Path
from typing import Optional, Dict, Any, Union

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
    "20251227_waichen_in_10hz.route.json", # idx = 7
    "20251227_waichen_out_10hz.route.json", # idx = 8
]

route_name_subset = [
    # "20251222_waichen_in.opt.JuMP.route.json",   # idx=0 from outside to back to waichen
    # "20251222_waichen_out.opt.JuMP.route.json", # idx=1 from waichen to go outside
    # "20251223_youke_out_10hz.route.json", # 
    # "20251227_waichen_out_10hz.route.json", # from waichen to go outside
    # "20251227_waichen_in_10hz.route.json", # 
    # "20251223_youke_in_10hz.route.json", # idx = 2, from youke in to outside
    # "test.2026-01-05.H11-245157-yangchang1.opt.JuMP.route.json",
    # "test.2026-01-05.H11-245157-yangchang2.opt.JuMP.route.json",
    # "test.2026-01-06.H11-245155-ma1.opt.JuMP.route.json",
    # "test.2026-01-06.H11-245155-ma2.opt.JuMP.route.json",
    # "test.2026-01-06.H11-245155-ma2.opt.JuMP.route.v2.json",
    "test.2026-01-06.H11-245155-ma2.opt.JuMP.route.v3.json",
]


class RouteMatcher:
    def __init__(self, data_dir: Union[str, Path] = ""):
        if isinstance(data_dir, Path):
            self.data_dir = data_dir
        else:
            self.data_dir = g_data_dir.joinpath(data_dir)
        self.route_data = None
        self.pt = None
        self.current_pt_index = -1
        self.latlon = (0.0, 0.0)
        self.route_name = ""
        self.projection_dist = -1

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
        for leg in route_data.get("legs", []):
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

    def match_solution(self, lat, lon) -> Optional[Dict[str, Any]]:
        """
        Match the given latitude and longitude to the closest segment in the speedplan.
        Finds index i such that the GPS point is between point i and i+1.
        """
        if not self.all_speedplan_points:
            return None

        def find_best_in_range(index_range):
            best_i = -1
            min_d = float("inf")
            cos_l = math.cos(math.radians(lat))
            # Factor to adjust longitude degrees into equivalent latitude degrees
            # based on how far we are from the equator.
            for i in index_range:
                if i < 0 or i >= len(self.all_speedplan_points) - 1:
                    continue
                p1 = self.all_speedplan_points[i]
                p2 = self.all_speedplan_points[i+1]

                # Calculate vector components of the road segment (p1 -> p2)
                dx = (p2["lon"] - p1["lon"]) * cos_l
                dy = p2["lat"] - p1["lat"]
                mag_sq = dx * dx + dy * dy

                # If mag_sq > 0, the two points are distinct and form a line.
                # If mag_sq == 0, p1 and p2 are the same point (avoid division by zero).
                if mag_sq > 0:
                    gx = (lon - p1["lon"]) * cos_l
                    gy = lat - p1["lat"]
                    # r is the projection ratio along the line p1->p2
                    r = (gx * dx + gy * dy) / mag_sq

                    # To satisfy the requirement p1 -> gps -> p2, we prefer segments
                    # where the GPS point projects BETWEEN the two points (0 <= r <= 1).
                    if 0 <= r <= 1:
                        # GPS is naturally between p1 and p2. 
                        # Use the perpendicular distance (cross-track error).
                        proj_lat = p1["lat"] + r * (p2["lat"] - p1["lat"])
                        proj_lon = p1["lon"] + r * (p2["lon"] - p1["lon"])
                        dist = haversine(lat, lon, proj_lat, proj_lon)
                    else:
                        # GPS is "outside" (either gps -> p1 -> p2 or p1 -> p2 -> gps).
                        # We use the distance to the nearest endpoint but add a 10m penalty.
                        # This encourages the search to pick a different segment where
                        # the point is actually "inside" if one exists.
                        r_clamped = max(0.0, min(1.0, r))
                        proj_lat = p1["lat"] + r_clamped * (p2["lat"] - p1["lat"])
                        proj_lon = p1["lon"] + r_clamped * (p2["lon"] - p1["lon"])
                        dist = haversine(lat, lon, proj_lat, proj_lon) + 10.0
                else:
                    dist = haversine(lat, lon, p1["lat"], p1["lon"])

                if dist < min_d:
                    min_d = dist
                    best_i = i
            return best_i, min_d

        min_dist = -1

        # 1. Search in local window if possible
        if self.current_pt_index >= 0:
            start = max(0, self.current_pt_index - 20)
            end = min(len(self.all_speedplan_points) - 1, self.current_pt_index + 100)
            best_idx, min_dist = find_best_in_range(range(start, end))

            # 2. If not found or too far, search everywhere
            if best_idx == -1 or min_dist > 50:
                best_idx_full, min_dist_full = find_best_in_range(
                    range(len(self.all_speedplan_points) - 1)
                )
                if best_idx_full != -1 and min_dist_full < min_dist:
                    best_idx, min_dist = best_idx_full, min_dist_full
        else:
            best_idx, min_dist = find_best_in_range(
                range(len(self.all_speedplan_points) - 1)
            )

        if best_idx != -1:
            if self.current_pt_index != -1 and abs(best_idx - self.current_pt_index) > 5:
                plan = self.all_speedplan_points
                lat1 = plan[self.current_pt_index]["lat"]
                lon1 = plan[self.current_pt_index]["lon"]
                lat2 = plan[best_idx]["lat"]
                lon2 = plan[best_idx]["lon"]
                dist = haversine(lat1, lon1, lat2, lon2)
                logger.warning(
                    f"Got a jump of index in the route: cur={self.current_pt_index}, next={best_idx}, jump distance: {dist:.3f}m"
                )

            if min_dist != -1:
                self.projection_dist = min_dist

            logger.debug(
                    f"Got a index in the route: cur={self.current_pt_index}, next={best_idx}, distance: {min_dist:.3f}m"
                )
            self.current_pt_index = best_idx
            return self.all_speedplan_points[best_idx]

        return None

    def find_closest_speedplan_point(self, lat, lon):

        closest_point = None
        min_distance = float("inf")

        kpoint = -1
        for ipoint, point in enumerate(self.all_speedplan_points):
            p_lat = point.get("lat")
            p_lon = point.get("lon")
            if p_lat is not None and p_lon is not None:
                # Use Haversine distance instead of Euclidean
                distance = haversine(lat, lon, p_lat, p_lon)
                if distance < min_distance:
                    min_distance = distance
                    closest_point = point
                    kpoint = ipoint

        if closest_point:
            self.current_pt_index = kpoint

        logger.debug(f"Got closest pt {kpoint} with distance {min_distance:.1f} meters")
        return closest_point

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
        if next_point is None:
            next_point = point

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
        Calculate the projection ratio of latlon onto the segment point1->point2.
        """
        lat1, lon1 = point1.get("lat"), point1.get("lon")
        lat2, lon2 = point2.get("lat"), point2.get("lon")
        lat, lon = latlon

        if None in (lat1, lon1, lat2, lon2):
            return 0.0

        cos_lat = math.cos(math.radians(lat1))
        dx = (lon2 - lon1) * cos_lat
        dy = lat2 - lat1
        mag_sq = dx * dx + dy * dy

        if mag_sq == 0:
            return 0.0

        gx = (lon - lon1) * cos_lat
        gy = lat - lat1
        r = (gx * dx + gy * dy) / mag_sq
        return max(0.0, min(1.0, r))


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

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from app.services.amap_direction import RoutePlanningError, _extract_path_points, get_route, get_walking_route


class AmapDirectionTests(unittest.TestCase):
    def test_extract_path_points_merges_step_polylines_without_duplicate_joints(self) -> None:
        points = _extract_path_points(
            {
                "steps": [
                    {"polyline": "117.180,39.153;117.190,39.145"},
                    {"polyline": "117.190,39.145;117.201,39.136"},
                ]
            }
        )

        self.assertEqual(
            points,
            [
                {"latitude": 39.153, "longitude": 117.18},
                {"latitude": 39.145, "longitude": 117.19},
                {"latitude": 39.136, "longitude": 117.201},
            ],
        )

    def test_get_walking_route_wraps_invalid_json_response(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.side_effect = ValueError("invalid json")

        with patch.dict("os.environ", {"AMAP_API_KEY": "fake-key"}, clear=True):
            with patch("app.services.amap_direction.requests.get", return_value=response):
                with self.assertRaises(RoutePlanningError) as context:
                    get_walking_route(39.153, 117.18, 39.145, 117.19)

        self.assertIn("Failed to call Amap walking route API", str(context.exception))

    def test_get_route_requests_cost_and_polyline_for_v5_modes(self) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "status": "1",
            "route": {
                "paths": [
                    {
                        "distance": "7118",
                        "cost": {"duration": "1180"},
                        "steps": [
                            {
                                "polyline": "108.955044,34.224199;108.924306,34.258771",
                            }
                        ],
                    }
                ]
            },
        }

        with patch.dict("os.environ", {"AMAP_API_KEY": "fake-key"}, clear=True):
            with patch("app.services.amap_direction.requests.get", return_value=response) as mock_get:
                route = get_route(
                    mode="drive",
                    origin_lat=34.224199,
                    origin_lng=108.955044,
                    dest_lat=34.258771,
                    dest_lng=108.924306,
                    city="西安",
                )

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["params"]["show_fields"], "cost,polyline")
        self.assertEqual(route["distance_m"], 7118)
        self.assertEqual(route["duration_s"], 1180)
        self.assertEqual(route["source"], "amap_driving")
        self.assertEqual(len(route["path_points"]), 2)


if __name__ == "__main__":
    unittest.main()

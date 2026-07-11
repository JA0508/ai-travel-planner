from __future__ import annotations

import unittest
from unittest.mock import patch

from app.api.routes.itinerary import preview_route_segments
from app.schemas import RoutePreviewMode, RoutePreviewRequest, RouteSegmentPreviewInput
from app.services.amap_direction import RoutePlanningError


class RoutePreviewTests(unittest.TestCase):
    def test_preview_route_segments_returns_amap_walking_result(self) -> None:
        request = RoutePreviewRequest(
            segments=[
                RouteSegmentPreviewInput(
                    segment_key="day-1:a:b",
                    from_name="天津之眼",
                    from_latitude=39.153,
                    from_longitude=117.180,
                    to_name="意大利风情区",
                    to_latitude=39.136,
                    to_longitude=117.201,
                )
            ]
        )

        with patch(
            "app.api.routes.itinerary.get_route",
            return_value={
                "distance_m": 2200,
                "duration_s": 1800,
                "source": "amap_walking",
                "path_points": [
                    {"latitude": 39.153, "longitude": 117.180},
                    {"latitude": 39.136, "longitude": 117.201},
                ],
            },
        ) as mock_get_route:
            response = preview_route_segments(request)

        mock_get_route.assert_called_once_with(
            mode="walk",
            origin_lat=39.153,
            origin_lng=117.18,
            dest_lat=39.136,
            dest_lng=117.201,
            city=None,
        )
        self.assertEqual(len(response.segments), 1)
        self.assertEqual(response.segments[0].segment_key, "day-1:a:b")
        self.assertEqual(response.segments[0].distance_m, 2200)
        self.assertEqual(response.segments[0].duration_s, 1800)
        self.assertEqual(response.segments[0].source, "amap_walking")
        self.assertEqual(response.segments[0].mode, RoutePreviewMode.WALK)
        self.assertEqual(len(response.segments[0].path_points), 2)
        self.assertEqual(response.segments[0].path_points[0].latitude, 39.153)
        self.assertEqual(response.failed_segments, [])

    def test_preview_route_segments_passes_transport_mode_and_city_hint(self) -> None:
        request = RoutePreviewRequest(
            segments=[
                RouteSegmentPreviewInput(
                    segment_key="day-1:a:b",
                    mode=RoutePreviewMode.TRANSIT,
                    from_name="博物馆",
                    from_latitude=34.22,
                    from_longitude=108.95,
                    from_city="西安",
                    to_name="城墙",
                    to_latitude=34.25,
                    to_longitude=108.92,
                    to_city="西安",
                )
            ]
        )

        with patch(
            "app.api.routes.itinerary.get_route",
            return_value={
                "distance_m": 6200,
                "duration_s": 2100,
                "source": "amap_transit",
                "path_points": [],
            },
        ) as mock_get_route:
            response = preview_route_segments(request)

        mock_get_route.assert_called_once_with(
            mode="transit",
            origin_lat=34.22,
            origin_lng=108.95,
            dest_lat=34.25,
            dest_lng=108.92,
            city="西安",
        )
        self.assertEqual(response.segments[0].mode, RoutePreviewMode.TRANSIT)
        self.assertEqual(response.segments[0].source, "amap_transit")

    def test_preview_route_segments_returns_labeled_fallback_on_provider_failure(self) -> None:
        request = RoutePreviewRequest(
            segments=[
                RouteSegmentPreviewInput(
                    segment_key="day-1:a:b",
                    from_name="天津之眼",
                    from_latitude=39.153,
                    from_longitude=117.180,
                    to_name="意大利风情区",
                    to_latitude=39.136,
                    to_longitude=117.201,
                )
            ]
        )

        with patch(
            "app.api.routes.itinerary.get_route",
            side_effect=RoutePlanningError("AMAP_API_KEY is not configured."),
        ):
            response = preview_route_segments(request)

        self.assertEqual(len(response.segments), 1)
        self.assertEqual(response.segments[0].segment_key, "day-1:a:b")
        self.assertEqual(response.segments[0].source, "local_estimate_walk")
        self.assertEqual(response.segments[0].mode, RoutePreviewMode.WALK)
        self.assertGreater(response.segments[0].distance_m, 0)
        self.assertGreater(response.segments[0].duration_s, 0)
        self.assertEqual(len(response.segments[0].path_points), 2)
        self.assertEqual(len(response.failed_segments), 1)
        self.assertEqual(response.failed_segments[0].segment_key, "day-1:a:b")
        self.assertEqual(response.failed_segments[0].from_name, "天津之眼")
        self.assertEqual(response.failed_segments[0].to_name, "意大利风情区")
        self.assertIn("AMAP_API_KEY", response.failed_segments[0].reason)


if __name__ == "__main__":
    unittest.main()

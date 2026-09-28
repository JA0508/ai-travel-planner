from __future__ import annotations

import unittest
from unittest.mock import patch

from app.api.routes.itinerary import preview_poi_detail
from app.schemas import POIDetailPreviewRequest
from app.services.amap_client import GeocodingError


class POIDetailPreviewTests(unittest.TestCase):
    def test_preview_poi_detail_returns_amap_card_fields(self) -> None:
        request = POIDetailPreviewRequest(
            name="天津之眼",
            city="天津",
            latitude=39.153,
            longitude=117.180,
        )

        with patch(
            "app.api.routes.itinerary.search_place_detail_candidates",
            return_value=[
                {
                    "name": "天津之眼",
                    "address": "天津市河北区",
                    "type": "风景名胜",
                    "business_area": "天津站/意风区",
                    "rating": "4.7",
                    "cost": "80",
                    "tel": "022-00000000",
                    "photo_url": "https://example.com/tianjin-eye.jpg",
                    "latitude": 39.153,
                    "longitude": 117.180,
                }
            ],
        ):
            response = preview_poi_detail(request)

        self.assertTrue(response.found)
        self.assertEqual(response.name, "天津之眼")
        self.assertEqual(response.address, "天津市河北区")
        self.assertEqual(response.category, "风景名胜")
        self.assertEqual(response.business_area, "天津站/意风区")
        self.assertEqual(response.rating, "4.7")
        self.assertEqual(response.photo_url, "https://example.com/tianjin-eye.jpg")
        self.assertIsNotNone(response.observed_at)

    def test_preview_poi_detail_compares_an_unambiguous_daily_window_to_the_scheduled_time(self) -> None:
        request = POIDetailPreviewRequest(
            name="天津之眼",
            city="天津",
            latitude=39.153,
            longitude=117.180,
            scheduled_start_time="10:00:00",
            scheduled_end_time="11:30:00",
        )

        with patch(
            "app.api.routes.itinerary.search_place_detail_candidates",
            return_value=[{"name": "天津之眼", "open_time": "09:00-17:00"}],
        ):
            response = preview_poi_detail(request)

        self.assertEqual(response.open_time_coverage, "covers_scheduled_window")

    def test_preview_poi_detail_returns_empty_state_when_provider_unavailable(self) -> None:
        request = POIDetailPreviewRequest(
            name="天津之眼",
            city="天津",
            latitude=39.153,
            longitude=117.180,
        )

        with patch(
            "app.api.routes.itinerary.search_place_detail_candidates",
            side_effect=GeocodingError("AMAP_API_KEY is not configured."),
        ):
            response = preview_poi_detail(request)

        self.assertFalse(response.found)
        self.assertEqual(response.name, "天津之眼")
        self.assertEqual(response.source, "amap_place_detail")
        self.assertIn("AMAP_API_KEY", response.failure_reason or "")
        self.assertIsNotNone(response.observed_at)

    def test_preview_poi_detail_returns_empty_state_when_no_candidate_matches(self) -> None:
        request = POIDetailPreviewRequest(
            name="冷门地点",
            city="天津",
            latitude=39.153,
            longitude=117.180,
        )

        with patch(
            "app.api.routes.itinerary.search_place_detail_candidates",
            return_value=[],
        ):
            response = preview_poi_detail(request)

        self.assertFalse(response.found)
        self.assertEqual(response.name, "冷门地点")
        self.assertEqual(response.source, "amap_place_detail")
        self.assertEqual(response.failure_reason, "No Amap POI detail candidate found.")
        self.assertIsNotNone(response.observed_at)


if __name__ == "__main__":
    unittest.main()

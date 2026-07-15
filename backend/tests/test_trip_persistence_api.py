from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import ItineraryResponse, PlanningAnchorSource
from app.trips.dependencies import reset_trip_repository_cache_for_tests


class TripPersistenceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            "os.environ",
            {
                "TRIP_STORE_MODE": "sqlite",
                "TRIP_STORE_PATH": str(Path(self.temp_dir.name) / "api-trip-store.sqlite3"),
                "TRIP_ALLOWED_ORIGINS": "http://testserver",
                "CORS_ALLOW_ORIGINS": "http://testserver",
            },
        )
        self.env.start()
        reset_trip_repository_cache_for_tests()

    def tearDown(self) -> None:
        reset_trip_repository_cache_for_tests()
        self.env.stop()
        self.temp_dir.cleanup()

    def test_persisted_plan_sets_httponly_cookie_and_restores_current_trip(self) -> None:
        client = TestClient(app)
        with patch(
            "app.trips.service.build_itinerary_response",
            return_value=simple_itinerary(),
        ):
            created = client.post(
                "/trips/plan",
                json={
                    "itinerary_request": {
                        "city": "上海",
                        "trip_days": 1,
                        "scenic_spots": [],
                        "restaurants": [],
                    }
                },
            )

        self.assertEqual(created.status_code, 201)
        body = created.json()
        self.assertEqual(body["current_revision"]["revision_number"], 1)
        self.assertEqual(body["current_revision"]["source_type"], "planner_generation")
        self.assertNotIn("capability", str(body))
        self.assertIn("HttpOnly", created.headers["set-cookie"])

        restored = client.get(f"/trips/{body['trip']['id']}")
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(
            restored.json()["current_revision"]["id"],
            body["current_revision"]["id"],
        )

    def test_missing_cookie_is_denied_without_trip_data(self) -> None:
        client = TestClient(app)
        with patch(
            "app.trips.service.build_itinerary_response",
            return_value=simple_itinerary(),
        ):
            created = client.post(
                "/trips/plan",
                json={
                    "itinerary_request": {
                        "city": "上海",
                        "trip_days": 1,
                        "scenic_spots": [],
                        "restaurants": [],
                    }
                },
            )
        trip_id = created.json()["trip"]["id"]

        denied = TestClient(app).get(f"/trips/{trip_id}")

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["error"]["code"], "trip_access_denied")
        self.assertNotIn("itinerary", str(denied.json()))

    def test_revision_history_lists_metadata_without_snapshot_by_default(self) -> None:
        client = TestClient(app)
        with patch(
            "app.trips.service.build_itinerary_response",
            return_value=simple_itinerary(),
        ):
            created = client.post(
                "/trips/plan",
                json={
                    "itinerary_request": {
                        "city": "上海",
                        "trip_days": 1,
                        "scenic_spots": [],
                        "restaurants": [],
                    }
                },
            )
        trip_id = created.json()["trip"]["id"]

        history = client.get(f"/trips/{trip_id}/revisions")

        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.json()["revisions"]), 1)
        self.assertNotIn("itinerary", history.json()["revisions"][0])


def simple_itinerary() -> ItineraryResponse:
    return ItineraryResponse(
        trip_days=1,
        planning_anchor_source=PlanningAnchorSource(
            source_type="city",
            source_name="上海",
        ),
        days=[],
    )


if __name__ == "__main__":
    unittest.main()

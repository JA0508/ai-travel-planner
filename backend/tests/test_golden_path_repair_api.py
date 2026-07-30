from __future__ import annotations

import tempfile
import unittest
from datetime import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import (
    DayItinerary, DayTimeBlock, HotelStay, ItineraryResponse, PlanningAnchorSource,
    POIType, ScheduledPOI, ScheduledPOISourceType, TimeBlockType,
)
from app.services.planner_realism_analyzer import analyze_planner_realism
from app.trips.dependencies import reset_trip_repository_cache_for_tests


class GoldenPathRepairApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env = patch.dict("os.environ", {
            "TRIP_STORE_MODE": "sqlite", "TRIP_STORE_PATH": str(Path(self.temp_dir.name) / "golden.sqlite3"),
            "TRIP_ALLOWED_ORIGINS": "http://testserver", "CORS_ALLOW_ORIGINS": "http://testserver",
        })
        self.env.start()
        reset_trip_repository_cache_for_tests()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_trip_repository_cache_for_tests()
        self.env.stop()
        self.temp_dir.cleanup()

    def test_server_authored_relaxation_moves_only_system_suggestion_and_retries_once(self) -> None:
        itinerary = rushed_itinerary()
        with patch("app.trips.service.build_itinerary_response", return_value=itinerary):
            created = self.client.post("/trips/plan", json={"itinerary_request": {"city": "西安", "trip_days": 2, "scenic_spots": [], "restaurants": []}})
        self.assertEqual(created.status_code, 201, created.text)
        trip_id = created.json()["trip"]["id"]
        revision_id = created.json()["current_revision"]["id"]

        with patch("app.trips.service.build_itinerary_response", side_effect=AssertionError("repair must not invoke planner")) as planner:
            preview = self.client.post(
                f"/trips/{trip_id}/golden-path/repair/preview",
                json={"base_revision": revision_id, "target_day": 1, "goal": "relax_day"},
                headers={"Origin": "http://testserver"},
            )
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(planner.call_count, 0)
        proposal = preview.json()["proposal"]
        self.assertEqual(proposal["moved_activity_name"], "城墙夜骑")
        self.assertEqual(proposal["from_day"], 1)
        self.assertEqual(proposal["to_day"], 2)
        self.assertEqual(proposal["execution_evidence"], {"parser_calls": 0, "llm_calls": 0, "full_planner_calls": 0, "route_provider_calls": 0})
        self.assertIn("兵马俑", [item["name"] for day in proposal["after"]["days"] for block in day["blocks"] for item in block["items"]])

        headers = {"Origin": "http://testserver", "X-Idempotency-Key": "golden-repair-one"}
        applied = self.client.post(
            f"/trips/{trip_id}/golden-path/repair/proposals/{proposal['proposal_id']}/apply",
            json={"base_revision": revision_id, "proposal_digest": proposal["proposal_digest"]}, headers=headers,
        )
        replay = self.client.post(
            f"/trips/{trip_id}/golden-path/repair/proposals/{proposal['proposal_id']}/apply",
            json={"base_revision": revision_id, "proposal_digest": proposal["proposal_digest"]}, headers=headers,
        )
        self.assertEqual(applied.status_code, 200, applied.text)
        self.assertEqual(applied.json()["current_revision"]["revision_number"], 2)
        self.assertTrue(replay.json()["persistence"]["idempotent_replay"])
        day_one = names_for_day(applied.json()["itinerary"], 1)
        day_two = names_for_day(applied.json()["itinerary"], 2)
        self.assertNotIn("城墙夜骑", day_one)
        self.assertIn("城墙夜骑", day_two)
        self.assertIn("兵马俑", day_one)
        fixed = next(item for day in applied.json()["itinerary"]["days"] for block in day["blocks"] for item in block["items"] if item["name"] == "陕西历史博物馆")
        self.assertTrue(fixed["is_fixed"])
        self.assertIsNotNone(next(item for day in applied.json()["itinerary"]["days"] for block in day["blocks"] for item in block["items"] if item["name"] == "城墙夜骑")["travel_duration_s"])

    def test_repair_rejects_user_owned_and_stale_requests(self) -> None:
        with patch("app.trips.service.build_itinerary_response", return_value=rushed_itinerary(system_suggestion=False)):
            created = self.client.post("/trips/plan", json={"itinerary_request": {"city": "西安", "trip_days": 2, "scenic_spots": [], "restaurants": []}})
        trip_id = created.json()["trip"]["id"]
        revision_id = created.json()["current_revision"]["id"]
        denied = self.client.post(f"/trips/{trip_id}/golden-path/repair/preview", json={"base_revision": revision_id, "target_day": 1, "goal": "relax_day"}, headers={"Origin": "http://testserver"})
        self.assertEqual(denied.status_code, 422)
        stale = self.client.post(f"/trips/{trip_id}/golden-path/repair/preview", json={"base_revision": "rev_stale", "target_day": 1, "goal": "relax_day"}, headers={"Origin": "http://testserver"})
        self.assertEqual(stale.status_code, 409)


def rushed_itinerary(*, system_suggestion: bool = True) -> ItineraryResponse:
    hotel = HotelStay(name="西安钟楼酒店", city="西安", latitude=34.258, longitude=108.948)
    def item(name: str, start: time, end: time, *, fixed: bool = False, source=ScheduledPOISourceType.USER_SEED, latitude=34.25, longitude=108.95):
        return ScheduledPOI(name=name, type=POIType.SCENIC, city="西安", latitude=latitude, longitude=longitude, duration_minutes=(end.hour * 60 + end.minute) - (start.hour * 60 + start.minute), day=1, start_time=start, end_time=end, is_fixed=fixed, source_type=source, placement_reason=f"{name} 有明确安排依据。")
    first = DayItinerary(day=1, hotel=hotel, blocks=[DayTimeBlock(block_type=TimeBlockType.AFTERNOON, start_time=time(12), end_time=time(20), items=[
        # Test coordinates stay local so this fixture isolates daily load from a
        # separate long-transfer hard conflict.
        item("兵马俑", time(12), time(14), latitude=34.245, longitude=108.955),
        item("陕西历史博物馆", time(14, 30), time(16), fixed=True, source=ScheduledPOISourceType.USER_FIXED, latitude=34.23, longitude=108.96),
        item("西安城墙", time(16, 15), time(17, 15)),
        item("城墙夜骑", time(17, 30), time(18, 30), source=ScheduledPOISourceType.AUTO_FILLED if system_suggestion else ScheduledPOISourceType.USER_SEED),
        item("回民街", time(18, 45), time(19, 45)),
    ])])
    second = DayItinerary(day=2, hotel=hotel, blocks=[DayTimeBlock(block_type=TimeBlockType.AFTERNOON, start_time=time(12), end_time=time(20), items=[
        item("大雁塔", time(14), time(15), latitude=34.218, longitude=108.97),
    ])])
    itinerary = ItineraryResponse(trip_days=2, planning_anchor_source=PlanningAnchorSource(source_type="hotel", source_name=hotel.name, latitude=hotel.latitude, longitude=hotel.longitude), days=[first, second])
    return itinerary.model_copy(update={"planner_realism": analyze_planner_realism(itinerary)})


def names_for_day(snapshot: dict, day: int) -> list[str]:
    return [item["name"] for record in snapshot["days"] if record["day"] == day for block in record["blocks"] for item in block["items"]]

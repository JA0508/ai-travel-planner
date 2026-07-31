from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.trip_compiler import build_itinerary_request, compile_travel_intent
from app.trips.dependencies import reset_trip_repository_cache_for_tests
from tests.test_trip_persistence_api import simple_itinerary


HANGZHOU_TEXT = """周末去杭州玩两天，想去西湖和灵隐寺。
朋友推荐龙井村，但不是必须。
周六下午两点预约了中国茶叶博物馆。
不想太赶，想吃本地小吃。
周日晚上六点前要到杭州东站。"""


class TripCompilerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            "os.environ",
            {
                "TRIP_STORE_MODE": "sqlite",
                "TRIP_STORE_PATH": str(Path(self.temp_dir.name) / "trip-compiler.sqlite3"),
                "TRIP_ALLOWED_ORIGINS": "http://testserver",
                "CORS_ALLOW_ORIGINS": "http://testserver",
            },
        )
        self.env.start()
        reset_trip_repository_cache_for_tests()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_trip_repository_cache_for_tests()
        self.env.stop()
        self.temp_dir.cleanup()

    def test_hangzhou_text_compiles_to_typed_intent_and_scheduler_input(self) -> None:
        compiled = compile_travel_intent(HANGZHOU_TEXT)
        intent = compiled.intent

        self.assertEqual(compiled.status, "ready")
        self.assertEqual(intent.contract_version, "1")
        self.assertEqual(intent.destination, "杭州")
        self.assertEqual(intent.trip_days, 2)
        self.assertEqual(intent.pace, "relaxed")
        self.assertEqual([place.name for place in intent.must_visit_places], ["西湖", "灵隐寺"])
        self.assertEqual([place.name for place in intent.optional_places], ["龙井村"])
        self.assertEqual([(event.name, event.day, event.start_time, event.end_time) for event in intent.fixed_events], [("中国茶叶博物馆", 1, "14:00", "16:00")])
        self.assertIn("本地小吃", [item.value for item in intent.preferences])
        self.assertTrue(all(item.source_fragment_ids for item in [*intent.must_visit_places, *intent.optional_places, *intent.fixed_events]))

        request = build_itinerary_request(intent)
        self.assertEqual(request.city, "杭州")
        self.assertEqual(request.trip_days, 2)
        self.assertTrue(request.auto_fill_sparse_days)
        self.assertEqual([item.name for item in request.scenic_spots], ["西湖", "灵隐寺", "龙井村", "中国茶叶博物馆"])
        self.assertEqual(request.scenic_spots[-1].fixed_day, 1)
        self.assertEqual(request.scenic_spots[-1].resolved_duration_minutes, 120)
        self.assertEqual([item.intent_ownership for item in request.scenic_spots[:3]], ["user_must", "user_must", "user_optional"])

    def test_missing_information_stays_in_confirmation_queue(self) -> None:
        compiled = compile_travel_intent("周末想去苏州，想看看园林，别太累。")

        self.assertEqual(compiled.status, "needs_confirmation")
        self.assertEqual(compiled.intent.destination, "苏州")
        self.assertIsNone(compiled.intent.trip_days)
        self.assertIn("trip_days", [item.field for item in compiled.intent.unresolved_items])
        self.assertIn("date_window", [item.field for item in compiled.intent.unresolved_items])

    def test_arrival_after_fixed_event_is_a_hard_conflict(self) -> None:
        compiled = compile_travel_intent("下午三点到上海，下午两点到四点预约了上海博物馆。")

        self.assertEqual(compiled.status, "hard_conflict")
        self.assertIn("到达时间晚于固定安排", compiled.conflicts[0])

    def test_confirmed_compiler_intent_creates_revision_one(self) -> None:
        compiled = compile_travel_intent(HANGZHOU_TEXT)
        with patch("app.trips.service.build_itinerary_response", return_value=simple_itinerary(2)):
            response = self.client.post(
                "/trip-compiler/trips",
                json={"intent": compiled.intent.model_dump(mode="json")},
                headers={"Origin": "http://testserver", "X-Idempotency-Key": "compiler-hangzhou"},
            )

        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["current_revision"]["revision_number"], 1)
        self.assertIn("HttpOnly", response.headers["set-cookie"])


if __name__ == "__main__":
    unittest.main()

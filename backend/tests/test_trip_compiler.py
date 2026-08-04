from __future__ import annotations

import tempfile
import unittest
from sqlite3 import connect
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.trip_compiler import build_itinerary_request, compile_travel_intent
from app.trips.dependencies import get_trip_repository, reset_trip_repository_cache_for_tests
HANGZHOU_TEXT = """周末去杭州玩两天，想去西湖和灵隐寺。
朋友推荐龙井村，但不是必须。
周六下午两点预约了中国茶叶博物馆。
不想太赶，想吃本地小吃。
周日晚上六点前要到杭州东站。"""


class TripCompilerContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "trip-compiler.sqlite3"
        self.env = patch.dict(
            "os.environ",
            {
                "TRIP_STORE_MODE": "sqlite",
                "TRIP_STORE_PATH": str(self.database_path),
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

    def trip_count(self) -> int:
        get_trip_repository()
        with connect(self.database_path) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM trips").fetchone()[0])

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

    def test_four_day_language_stays_in_confirmation_instead_of_raising_a_server_error(self) -> None:
        response = self.client.post(
            "/trip-compiler/intents/compile",
            json={"text": "去杭州玩四天，想去西湖和灵隐寺，节奏轻松一些。"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "needs_confirmation")
        self.assertIsNone(body["intent"]["trip_days"])
        self.assertIn("unresolved_trip_days_v1_limit", [item["stable_id"] for item in body["intent"]["unresolved_items"]])

    def test_blocked_intent_returns_422_without_creating_a_trip(self) -> None:
        compiled = compile_travel_intent("周末想去苏州，想看看园林，别太累。")
        before = self.trip_count()
        response = self.client.post(
            "/trip-compiler/trips",
            json={"intent": compiled.intent.model_dump(mode="json")},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "compiler-blocked"},
        )

        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("destination and trip_days are required", response.json()["detail"])
        self.assertEqual(self.trip_count(), before)

    def test_out_of_range_or_inconsistent_plan_payloads_are_rejected_before_persistence(self) -> None:
        intent_payload = compile_travel_intent(HANGZHOU_TEXT).intent.model_dump(mode="json")
        invalid_payloads = []

        too_long = {**intent_payload, "trip_days": 4}
        invalid_payloads.append(too_long)

        fixed_day_outside_trip = {**intent_payload, "fixed_events": [{**intent_payload["fixed_events"][0], "day": 3}]}
        invalid_payloads.append(fixed_day_outside_trip)

        for index, payload in enumerate(invalid_payloads):
            with self.subTest(payload=index), patch("app.api.routes.trip_compiler.get_trip_persistence_service") as persistence:
                response = self.client.post(
                    "/trip-compiler/trips",
                    json={"intent": payload},
                    headers={"Origin": "http://testserver", "X-Idempotency-Key": f"compiler-invalid-{index}"},
                )

            self.assertEqual(response.status_code, 422, response.text)
            persistence.assert_not_called()

    def test_confirmed_compiler_intent_enters_the_draft_admission_boundary(self) -> None:
        compiled = compile_travel_intent(HANGZHOU_TEXT)
        response = self.client.post(
            "/trip-compiler/trips",
            json={"intent": compiled.intent.model_dump(mode="json")},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "compiler-hangzhou"},
        )

        self.assertEqual(response.status_code, 201, response.text)
        trip = response.json()["trip"]
        self.assertEqual(trip["planning_phase"], "draft")
        self.assertIsNone(trip["current_revision_id"])
        self.assertEqual(trip["revision_count"], 0)
        self.assertIn("HttpOnly", response.headers["set-cookie"])

        draft = self.client.get(f"/trips/{trip['id']}/draft")
        self.assertEqual(draft.status_code, 200, draft.text)
        self.assertIn("城市：杭州", draft.json()["direct_user_text"])
        self.assertIn("景点：西湖、灵隐寺、龙井村", draft.json()["direct_user_text"])
        self.assertIn("离开锚点：第 2 天 18:00 前需要结束行程", draft.json()["direct_user_text"])

        compiled_draft = self.client.post(
            f"/trips/{trip['id']}/preplan-intent/compile",
            json={
                "base_trip_revision_id": None,
                "base_intent_revision_id": None,
                "direct_user_text": draft.json()["direct_user_text"],
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "compiler-hangzhou-intent"},
        )
        self.assertEqual(compiled_draft.status_code, 201, compiled_draft.text)
        self.assertIsNone(compiled_draft.json()["envelope"]["base_trip_revision_id"])


if __name__ == "__main__":
    unittest.main()

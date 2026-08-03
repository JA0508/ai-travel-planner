from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from sqlite3 import connect
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.plan_candidate_store import reset_plan_candidate_store_for_tests
from app.services.trip_compiler import compile_travel_intent
from app.trips.dependencies import get_trip_repository, reset_trip_repository_cache_for_tests


HANGZHOU = "周末去杭州玩两天，想去西湖和灵隐寺。朋友推荐龙井村，但不是必须。周六下午两点预约了中国茶叶博物馆。不想太赶，想吃本地小吃。周日晚上六点前要到杭州东站。"


class PlanCandidateApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "candidate.sqlite3"
        self.env = patch.dict("os.environ", {"TRIP_STORE_MODE": "sqlite", "TRIP_STORE_PATH": str(self.database_path), "TRIP_ALLOWED_ORIGINS": "http://testserver", "CORS_ALLOW_ORIGINS": "http://testserver"})
        self.env.start()
        reset_trip_repository_cache_for_tests()
        reset_plan_candidate_store_for_tests()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        reset_plan_candidate_store_for_tests()
        reset_trip_repository_cache_for_tests()
        self.env.stop()
        self.temp_dir.cleanup()

    def trip_count(self) -> int:
        get_trip_repository()
        with connect(self.database_path) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM trips").fetchone()[0])

    def candidates(self, text: str = HANGZHOU):
        intent = compile_travel_intent(text).intent.model_dump(mode="json")
        return self.client.post("/trip-compiler/plan-candidates", json={"intent": intent})

    def test_generation_is_deterministic_and_never_creates_a_trip(self) -> None:
        before = self.trip_count()
        first = self.candidates()
        second = self.candidates()
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        first_body, second_body = first.json(), second.json()
        self.assertEqual(first_body["intent_digest"], second_body["intent_digest"])
        self.assertEqual([(item["id"], item["candidate_hash"]) for item in first_body["candidates"]], [(item["id"], item["candidate_hash"]) for item in second_body["candidates"]])
        self.assertGreaterEqual(len(first_body["candidates"]), 1)
        self.assertLessEqual(len(first_body["candidates"]), 3)
        self.assertEqual(self.trip_count(), before)

    def test_constraint_graph_keeps_only_verified_source_fragment_references(self) -> None:
        response = self.candidates()
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        source_ids = {item["stable_id"] for item in compile_travel_intent(HANGZHOU).intent.model_dump(mode="json")["source_fragments"]}
        for node in body["constraint_graph"]["nodes"]:
            self.assertTrue({ref["source_fragment_id"] for ref in node["source_refs"]}.issubset(source_ids))

    def test_arrival_conflict_returns_422_with_core_and_creates_no_trip(self) -> None:
        before = self.trip_count()
        response = self.candidates("去上海玩两天，下午三点到。下午两点到四点预约了上海博物馆。")
        self.assertEqual(response.status_code, 422, response.text)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "hard_constraint_conflict")
        self.assertEqual(detail["conflict_cores"][0]["code"], "arrival_after_fixed_event")
        self.assertEqual(self.trip_count(), before)

    def test_overlapping_fixed_events_returns_minimal_core(self) -> None:
        intent = compile_travel_intent("去杭州玩两天，下午两点到四点预约了中国茶叶博物馆。") .intent.model_dump(mode="json")
        intent["fixed_events"].append({**intent["fixed_events"][0], "stable_id": "fixed_second", "name": "灵隐寺讲解", "start_time": "15:00", "end_time": "17:00"})
        response = self.client.post("/trip-compiler/plan-candidates", json={"intent": intent})
        self.assertEqual(response.status_code, 422, response.text)
        core = response.json()["detail"]["conflict_cores"][0]
        self.assertEqual(core["code"], "fixed_event_overlap")
        self.assertEqual(len(core["node_ids"]), 2)

    def test_select_is_idempotent_and_requires_server_candidate(self) -> None:
        candidates = self.candidates()
        self.assertEqual(candidates.status_code, 200, candidates.text)
        payload = candidates.json()
        candidate = payload["candidates"][0]
        before = self.trip_count()
        headers = {"Origin": "http://testserver", "X-Idempotency-Key": "select-candidate-1"}
        selected = self.client.post(f"/trip-compiler/plan-candidates/{candidate['id']}/select", json={"candidate_hash": candidate["candidate_hash"], "intent_digest": payload["intent_digest"]}, headers=headers)
        self.assertEqual(selected.status_code, 201, selected.text)
        replay = self.client.post(f"/trip-compiler/plan-candidates/{candidate['id']}/select", json={"candidate_hash": candidate["candidate_hash"], "intent_digest": payload["intent_digest"]}, headers=headers)
        self.assertEqual(replay.status_code, 201, replay.text)
        self.assertEqual(selected.json()["trip"]["id"], replay.json()["trip"]["id"])
        self.assertIn("HttpOnly", replay.headers["set-cookie"])
        selected_names = [item["name"] for day in selected.json()["itinerary"]["days"] for block in day["blocks"] for item in block["items"]]
        preview_names = [item["name"] for day in candidate["itinerary"]["days"] for block in day["blocks"] for item in block["items"]]
        self.assertEqual(selected_names, preview_names)
        self.assertEqual(self.trip_count(), before + 1)

    def test_tampered_selection_never_creates_a_trip(self) -> None:
        candidates = self.candidates().json()
        candidate = candidates["candidates"][0]
        before = self.trip_count()
        response = self.client.post(f"/trip-compiler/plan-candidates/{candidate['id']}/select", json={"candidate_hash": "a" * 64, "intent_digest": candidates["intent_digest"]}, headers={"Origin": "http://testserver", "X-Idempotency-Key": "tampered"})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["error"]["code"], "candidate_mismatch")
        self.assertEqual(self.trip_count(), before)


if __name__ == "__main__":
    unittest.main()

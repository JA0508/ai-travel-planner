from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import PlannerRealismSummary
from app.trips.dependencies import reset_trip_repository_cache_for_tests
from tests.test_trip_persistence_api import simple_itinerary


class DraftTripPrePlanWorkspaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            "os.environ",
            {
                "TRIP_STORE_MODE": "sqlite",
                "TRIP_STORE_PATH": str(Path(self.temp_dir.name) / "draft-trip.sqlite3"),
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

    def test_draft_intent_preview_then_apply_creates_first_revision_once(self) -> None:
        created = self.client.post(
            "/trips/drafts",
            json={"direct_user_text": "我想去西安玩两天。"},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-xian-one"},
        )
        self.assertEqual(created.status_code, 201, created.text)
        trip = created.json()["trip"]
        self.assertEqual(trip["planning_phase"], "draft")
        self.assertIsNone(trip["current_revision_id"])
        self.assertEqual(trip["revision_count"], 0)
        trip_id = trip["id"]

        replayed_draft = self.client.post(
            "/trips/drafts",
            json={"direct_user_text": "我想去西安玩两天。"},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-xian-one"},
        )
        self.assertEqual(replayed_draft.status_code, 201, replayed_draft.text)
        self.assertEqual(replayed_draft.json()["trip"]["id"], trip_id)
        self.assertTrue(replayed_draft.json()["persistence"]["idempotent_replay"])

        reloaded_draft = self.client.get(f"/trips/{trip_id}/draft")
        self.assertEqual(reloaded_draft.status_code, 200, reloaded_draft.text)
        self.assertEqual(reloaded_draft.json()["direct_user_text"], "我想去西安玩两天。")

        compiled = self.client.post(
            f"/trips/{trip_id}/preplan-intent/compile",
            json={
                "base_trip_revision_id": None,
                "base_intent_revision_id": None,
                "structured_overrides": {"city": "西安", "trip_days": 2, "pace": "relaxed"},
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-intent-one"},
        )
        self.assertEqual(compiled.status_code, 201, compiled.text)
        intent_id = compiled.json()["revision"]["id"]
        self.assertIsNone(compiled.json()["envelope"]["base_trip_revision_id"])

        with patch("app.trips.service.build_itinerary_response", return_value=simple_itinerary(2)):
            preview = self.client.post(
                f"/trips/{trip_id}/preplan-handoff/preview",
                json={"draft_intent_revision_id": intent_id},
            )
        self.assertEqual(preview.status_code, 200, preview.text)
        run = preview.json()["handoff"]
        self.assertEqual(run["status"], "pending")

        with patch("app.trips.service.build_itinerary_response", side_effect=AssertionError("apply must not rerun planner")):
            applied = self.client.post(
                f"/trips/{trip_id}/preplan-handoff/runs/{run['id']}/apply",
                json={"draft_intent_revision_id": intent_id, "handoff_digest": run["trace_digest"]},
                headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-apply-one"},
            )
        self.assertEqual(applied.status_code, 200, applied.text)
        self.assertEqual(applied.json()["current_revision"]["revision_number"], 1)
        self.assertEqual(applied.json()["trip"]["planning_phase"], "planned")

        replay = self.client.post(
            f"/trips/{trip_id}/preplan-handoff/runs/{run['id']}/apply",
            json={"draft_intent_revision_id": intent_id, "handoff_digest": run["trace_digest"]},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-apply-one"},
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()["persistence"]["idempotent_replay"])

    def test_newer_draft_intent_invalidates_older_preview(self) -> None:
        created = self.client.post("/trips/drafts", json={"direct_user_text": "我想去西安玩两天。"}, headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-xian-two"})
        trip_id = created.json()["trip"]["id"]
        first = self.client.post(
            f"/trips/{trip_id}/preplan-intent/compile",
            json={"base_intent_revision_id": None, "structured_overrides": {"city": "西安", "trip_days": 2}},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-intent-two"},
        ).json()["revision"]["id"]
        with patch("app.trips.service.build_itinerary_response", return_value=simple_itinerary(2)):
            preview = self.client.post(f"/trips/{trip_id}/preplan-handoff/preview", json={"draft_intent_revision_id": first})
        second = self.client.post(
            f"/trips/{trip_id}/preplan-intent/compile",
            json={"base_intent_revision_id": first, "structured_overrides": {"city": "西安", "trip_days": 3}},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-intent-three"},
        )
        self.assertEqual(second.status_code, 201, second.text)
        run = preview.json()["handoff"]
        stale = self.client.post(
            f"/trips/{trip_id}/preplan-handoff/runs/{run['id']}/apply",
            json={"draft_intent_revision_id": first, "handoff_digest": run["trace_digest"]},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-stale-apply"},
        )
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(stale.json()["error"]["code"], "stale_intent_revision")

    def test_unstable_route_preview_cannot_create_revision_one(self) -> None:
        created = self.client.post(
            "/trips/drafts",
            json={"direct_user_text": "我想去西安玩两天。"},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-unstable"},
        )
        trip_id = created.json()["trip"]["id"]
        compiled = self.client.post(
            f"/trips/{trip_id}/preplan-intent/compile",
            json={"base_intent_revision_id": None, "structured_overrides": {"city": "西安", "trip_days": 2}},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-unstable-intent"},
        )
        intent_id = compiled.json()["revision"]["id"]
        unstable = simple_itinerary(2).model_copy(
            update={
                "planner_realism": PlannerRealismSummary(
                    status="unstable",
                    headline="这版路线存在未解决的执行冲突。",
                    issues=[],
                    suggested_actions=[],
                    daily_loads=[],
                )
            }
        )
        with patch("app.trips.service.build_itinerary_response", return_value=unstable):
            preview = self.client.post(
                f"/trips/{trip_id}/preplan-handoff/preview",
                json={"draft_intent_revision_id": intent_id},
            )
        self.assertEqual(preview.status_code, 200, preview.text)
        run = preview.json()["handoff"]
        applied = self.client.post(
            f"/trips/{trip_id}/preplan-handoff/runs/{run['id']}/apply",
            json={"draft_intent_revision_id": intent_id, "handoff_digest": run["trace_digest"]},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-unstable-apply"},
        )
        self.assertEqual(applied.status_code, 422, applied.text)
        self.assertEqual(applied.json()["error"]["code"], "invalid_revision_operation")
        self.assertEqual(self.client.get(f"/trips/{trip_id}/revisions").json()["revisions"], [])

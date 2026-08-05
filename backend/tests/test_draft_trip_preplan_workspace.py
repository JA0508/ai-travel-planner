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
from tests.test_trip_mutation_commands import command_itinerary


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

        candidate = register_verified_draft_candidate(self.client, trip_id, "first")

        compiled = self.client.post(
            f"/trips/{trip_id}/preplan-intent/compile",
            json={
                "base_trip_revision_id": None,
                "base_intent_revision_id": None,
                "structured_overrides": {"city": "西安", "trip_days": 2, "pace": "relaxed", "must_candidate_ids": [candidate["id"]]},
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-intent-one"},
        )
        self.assertEqual(compiled.status_code, 201, compiled.text)
        intent_id = compiled.json()["revision"]["id"]
        self.assertIsNone(compiled.json()["envelope"]["base_trip_revision_id"])

        planned = command_itinerary().model_copy(update={"trip_days": 2})
        planned.days[0].blocks[0].items[0].candidate_id = candidate["id"]
        planned.days[0].blocks[0].items[0].canonical_place_id = candidate["canonical_place_id"]
        planned.days[0].blocks[0].items[0].provider_place_id = candidate["provider_place_id"]
        with patch("app.trips.service.build_itinerary_response", return_value=planned) as planner:
            preview = self.client.post(
                f"/trips/{trip_id}/preplan-handoff/preview",
                json={"draft_intent_revision_id": intent_id},
            )
        self.assertEqual(preview.status_code, 200, preview.text)
        run = preview.json()["handoff"]
        self.assertEqual(run["status"], "pending")
        handoff_poi = planner.call_args.args[0].scenic_spots[0]
        self.assertEqual(handoff_poi.canonical_place_id, candidate["canonical_place_id"])
        self.assertEqual(handoff_poi.provider_place_id, candidate["provider_place_id"])
        preview_item = preview.json()["itinerary"]["days"][0]["blocks"][0]["items"][0]
        self.assertEqual(preview_item["canonical_place_id"], candidate["canonical_place_id"])
        self.assertEqual(preview_item["provider_place_id"], candidate["provider_place_id"])
        self.assertTrue(preview_item["candidate_provenance"]["authority"])
        self.assertTrue(preview_item["candidate_provenance"]["confirmed"])

        with patch("app.trips.service.build_itinerary_response", side_effect=AssertionError("apply must not rerun planner")):
            applied = self.client.post(
                f"/trips/{trip_id}/preplan-handoff/runs/{run['id']}/apply",
                json={"draft_intent_revision_id": intent_id, "handoff_digest": run["trace_digest"]},
                headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-apply-one"},
            )
        self.assertEqual(applied.status_code, 200, applied.text)
        self.assertEqual(applied.json()["current_revision"]["revision_number"], 1)
        self.assertEqual(applied.json()["trip"]["planning_phase"], "planned")
        self.assertEqual(applied.json()["current_revision"]["planner_run_id"], run["id"])

        reset_trip_repository_cache_for_tests()
        resumed = self.client.get(f"/trips/{trip_id}")
        self.assertEqual(resumed.status_code, 200, resumed.text)
        persisted_item = resumed.json()["itinerary"]["days"][0]["blocks"][0]["items"][0]
        self.assertEqual(persisted_item["canonical_place_id"], candidate["canonical_place_id"])
        self.assertEqual(persisted_item["provider_place_id"], candidate["provider_place_id"])
        self.assertEqual(
            persisted_item["candidate_provenance"]["authority"],
            preview_item["candidate_provenance"]["authority"],
        )

        saved_evidence = self.client.get(f"/trips/{trip_id}/preplan-handoff/runs/{run['id']}")
        self.assertEqual(saved_evidence.status_code, 200, saved_evidence.text)
        self.assertEqual(saved_evidence.json()["handoff"]["applied_revision_id"], applied.json()["current_revision"]["id"])
        self.assertEqual(saved_evidence.json()["review_summary"]["status"], "applied")
        self.assertEqual(saved_evidence.json()["review_summary"]["intent_revision_id"], intent_id)

        replay = self.client.post(
            f"/trips/{trip_id}/preplan-handoff/runs/{run['id']}/apply",
            json={"draft_intent_revision_id": intent_id, "handoff_digest": run["trace_digest"]},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-apply-one"},
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()["persistence"]["idempotent_replay"])

    def test_draft_without_a_schedulable_anchor_is_blocked_before_planning(self) -> None:
        created = self.client.post(
            "/trips/drafts",
            json={"direct_user_text": "我想去西安玩两天。"},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-no-anchor"},
        )
        self.assertEqual(created.status_code, 201, created.text)
        trip_id = created.json()["trip"]["id"]

        compiled = self.client.post(
            f"/trips/{trip_id}/preplan-intent/compile",
            json={
                "base_intent_revision_id": None,
                "direct_user_text": "我想去西安玩两天。",
                "structured_overrides": {"city": "西安", "trip_days": 2},
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-no-anchor-compile"},
        )
        self.assertEqual(compiled.status_code, 201, compiled.text)
        body = compiled.json()
        self.assertEqual(body["envelope"]["planner_ready_status"], "needs_clarification")
        self.assertIn("no_planner_anchor", body["envelope"]["formal_contract"]["readiness"]["blocking_issue_codes"])

        with patch("app.trips.service.build_itinerary_response", side_effect=AssertionError("no-anchor drafts must not invoke the planner")) as planner:
            preview = self.client.post(
                f"/trips/{trip_id}/preplan-handoff/preview",
                json={"draft_intent_revision_id": body["revision"]["id"]},
            )
        planner.assert_not_called()
        self.assertEqual(preview.status_code, 422, preview.text)
        self.assertEqual(preview.json()["error"]["code"], "planner_handoff_blocked")
        self.assertEqual(preview.json()["error"]["reason_code"], "intent_not_planner_ready")

    def test_newer_draft_intent_invalidates_older_preview(self) -> None:
        created = self.client.post("/trips/drafts", json={"direct_user_text": "我想去西安玩两天。"}, headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-xian-two"})
        trip_id = created.json()["trip"]["id"]
        candidate = register_verified_draft_candidate(self.client, trip_id, "stale")
        first = self.client.post(
            f"/trips/{trip_id}/preplan-intent/compile",
            json={"base_intent_revision_id": None, "structured_overrides": {"city": "西安", "trip_days": 2, "must_candidate_ids": [candidate["id"]]}},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-intent-two"},
        ).json()["revision"]["id"]
        with patch("app.trips.service.build_itinerary_response", return_value=simple_itinerary(2)):
            preview = self.client.post(f"/trips/{trip_id}/preplan-handoff/preview", json={"draft_intent_revision_id": first})
        second = self.client.post(
            f"/trips/{trip_id}/preplan-intent/compile",
            json={"base_intent_revision_id": first, "structured_overrides": {"city": "西安", "trip_days": 3, "must_candidate_ids": [candidate["id"]]}},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-intent-three"},
        )
        self.assertEqual(second.status_code, 201, second.text)
        run = preview.json()["handoff"]
        with patch("app.trips.service.build_itinerary_response", side_effect=AssertionError("summary reads must not rerun planner")) as planner:
            inspection = self.client.get(f"/trips/{trip_id}/preplan-handoff/runs/{run['id']}")
            second_inspection = self.client.get(f"/trips/{trip_id}/preplan-handoff/runs/{run['id']}")
        planner.assert_not_called()
        self.assertEqual(inspection.status_code, 200, inspection.text)
        self.assertEqual(second_inspection.status_code, 200, second_inspection.text)
        self.assertEqual(second_inspection.json()["review_summary"], inspection.json()["review_summary"])
        self.assertEqual(inspection.json()["latest_draft_intent_revision_id"], second.json()["revision"]["id"])
        self.assertEqual(inspection.json()["preview_status"], "stale")
        self.assertEqual(inspection.json()["stale_reason"], "draft_intent_advanced")
        self.assertEqual(inspection.json()["handoff"]["draft_intent_revision_id"], first)
        self.assertEqual(inspection.json()["review_summary"]["status"], "stale")
        self.assertIn("intent_revision_advanced", inspection.json()["review_summary"]["blocking_reason_codes"])
        stale = self.client.post(
            f"/trips/{trip_id}/preplan-handoff/runs/{run['id']}/apply",
            json={"draft_intent_revision_id": first, "handoff_digest": run["trace_digest"]},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-stale-apply"},
        )
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(stale.json()["error"]["code"], "stale_intent_revision")

    def test_resolving_fixed_event_clarification_updates_the_preview_blocker(self) -> None:
        created = self.client.post(
            "/trips/drafts",
            json={"direct_user_text": "去上海一天，第二天有预约。"},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-fixed-event-blocker"},
        )
        trip_id = created.json()["trip"]["id"]
        compiled = self.client.post(
            f"/trips/{trip_id}/preplan-intent/compile",
            json={
                "base_intent_revision_id": None,
                "structured_overrides": {
                    "city": "上海",
                    "trip_days": 1,
                    "fixed_events": [{"name": "第二天预约", "fixed_day": 2}],
                },
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-fixed-event-compile"},
        )
        self.assertEqual(compiled.status_code, 201, compiled.text)
        intent_id = compiled.json()["revision"]["id"]
        blocked = self.client.post(f"/trips/{trip_id}/preplan-handoff/preview", json={"draft_intent_revision_id": intent_id})
        self.assertEqual(blocked.status_code, 422, blocked.text)
        self.assertEqual(blocked.json()["error"]["code"], "planner_handoff_blocked")
        self.assertEqual(blocked.json()["error"]["reason_code"], "intent_not_planner_ready")

        question = next(
            item
            for item in compiled.json()["envelope"]["clarification_queue"]
            if item["reason_code"] == "fixed_event_outside_trip_dates"
        )
        latest = self.client.get(f"/trips/{trip_id}/preplan-intent")
        resolved = self.client.post(
            f"/trips/{trip_id}/preplan-intent/clarifications/{question['question_id']}/resolve",
            json={
                "base_intent_revision_id": intent_id,
                "base_draft_version": latest.json()["trip"]["draft_version"],
                "answer": {"answer_type": "date_policy_choice", "policy": "trip_days", "trip_days": 2},
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-fixed-event-resolve"},
        )
        self.assertEqual(resolved.status_code, 201, resolved.text)

        preview = self.client.post(
            f"/trips/{trip_id}/preplan-handoff/preview",
            json={"draft_intent_revision_id": resolved.json()["revision"]["id"]},
        )
        self.assertEqual(preview.status_code, 422, preview.text)
        self.assertEqual(preview.json()["error"]["code"], "planner_handoff_blocked")
        self.assertEqual(preview.json()["error"]["reason_code"], "fixed_event_identity_not_verified")

    def test_unstable_route_preview_cannot_create_revision_one(self) -> None:
        created = self.client.post(
            "/trips/drafts",
            json={"direct_user_text": "我想去西安玩两天。"},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-unstable"},
        )
        trip_id = created.json()["trip"]["id"]
        candidate = register_verified_draft_candidate(self.client, trip_id, "unstable")
        compiled = self.client.post(
            f"/trips/{trip_id}/preplan-intent/compile",
            json={"base_intent_revision_id": None, "structured_overrides": {"city": "西安", "trip_days": 2, "must_candidate_ids": [candidate["id"]]}},
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


def register_verified_draft_candidate(client: TestClient, trip_id: str, suffix: str) -> dict:
    response = client.post(
        f"/trips/{trip_id}/candidates",
        json={
            "candidate_type": "place",
            "display_name": f"西安城墙 {suffix}",
            "canonical_place_id": f"amap:xian-wall:{suffix}",
            "provider_place_id": f"B000XIAN{suffix}",
            "coordinates": {"latitude": 34.258, "longitude": 108.948},
            "estimated_duration_minutes": 90,
            "source_kind": "manual_entry",
        },
        headers={"Origin": "http://testserver", "X-Idempotency-Key": f"draft-verified-candidate:{suffix}"},
    )
    assert response.status_code == 201, response.text
    return response.json()["candidate"]

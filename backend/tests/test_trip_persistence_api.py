from __future__ import annotations

import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import (
    ItineraryResponse,
    PlanningAnchorSource,
    RegenerationIntentSummary,
    ReplanItineraryResponse,
    TripIntentEnvelope,
    TripIntentEnvelopeSource,
)
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

    def test_persisted_replan_creates_revision_with_idempotent_retry(self) -> None:
        client = TestClient(app)
        with patch(
            "app.trips.service.build_itinerary_response",
            return_value=simple_itinerary(1),
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
        base_revision_id = created.json()["current_revision"]["id"]

        with patch(
            "app.trips.service.execute_replan_from_itinerary",
            return_value=(
                ReplanItineraryResponse(
                    trip_intent=simple_trip_intent(2),
                    itinerary=simple_itinerary(2, with_intent=True),
                ),
                fake_trace(),
            ),
        ) as execute_replan:
            first = client.post(
                f"/trips/{trip_id}/replan",
                json={
                    "base_revision_id": base_revision_id,
                    "follow_up_text": "第二天加一个轻松街区",
                },
                headers={
                    "Origin": "http://testserver",
                    "X-Idempotency-Key": "same-replan",
                },
            )
            retried = client.post(
                f"/trips/{trip_id}/replan",
                json={
                    "base_revision_id": base_revision_id,
                    "follow_up_text": "第二天加一个轻松街区",
                },
                headers={
                    "Origin": "http://testserver",
                    "X-Idempotency-Key": "same-replan",
                },
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(first.json()["current_revision"]["source_type"], "replan_patch")
        self.assertEqual(first.json()["current_revision"]["revision_number"], 2)
        self.assertEqual(
            first.json()["current_revision"]["id"],
            retried.json()["current_revision"]["id"],
        )
        self.assertTrue(retried.json()["persistence"]["idempotent_replay"])
        self.assertEqual(execute_replan.call_count, 1)

        history = client.get(f"/trips/{trip_id}/revisions")
        self.assertEqual(len(history.json()["revisions"]), 2)

    def test_replan_preview_is_non_persistent_and_apply_rejects_mismatched_proposal(self) -> None:
        client = TestClient(app)
        with patch(
            "app.trips.service.build_itinerary_response",
            return_value=simple_itinerary(1),
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
        base_revision_id = created.json()["current_revision"]["id"]

        with patch(
            "app.trips.service.execute_replan_from_itinerary",
            return_value=(
                ReplanItineraryResponse(
                    trip_intent=simple_trip_intent(2),
                    itinerary=simple_itinerary(2, with_intent=True),
                ),
                fake_trace(),
            ),
        ):
            preview = client.post(
                f"/trips/{trip_id}/replan/preview",
                json={
                    "base_revision_id": base_revision_id,
                    "follow_up_text": "第二天加一个轻松街区",
                },
                headers={"Origin": "http://testserver"},
            )
            mismatched_apply = client.post(
                f"/trips/{trip_id}/replan",
                json={
                    "base_revision_id": base_revision_id,
                    "follow_up_text": "第二天加一个轻松街区",
                    "expected_preview_digest": "wrong-preview-digest",
                },
                headers={
                    "Origin": "http://testserver",
                    "X-Idempotency-Key": "bad-preview",
                },
            )

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["proposal"]["source_type"], "replan_patch")
        self.assertEqual(preview.json()["proposal"]["base_revision_id"], base_revision_id)
        self.assertEqual(mismatched_apply.status_code, 409)
        self.assertEqual(mismatched_apply.json()["error"]["code"], "mutation_proposal_mismatch")

        history = client.get(f"/trips/{trip_id}/revisions").json()["revisions"]
        self.assertEqual([revision["revision_number"] for revision in history], [1])

    def test_persisted_replan_rejects_stale_base_and_undo_compensates(self) -> None:
        client = TestClient(app)
        with patch(
            "app.trips.service.build_itinerary_response",
            return_value=simple_itinerary(1),
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
        base_revision_id = created.json()["current_revision"]["id"]

        with patch(
            "app.trips.service.execute_replan_from_itinerary",
            return_value=(
                ReplanItineraryResponse(
                    trip_intent=simple_trip_intent(2),
                    itinerary=simple_itinerary(2, with_intent=True),
                ),
                fake_trace(),
            ),
        ):
            applied = client.post(
                f"/trips/{trip_id}/replan",
                json={
                    "base_revision_id": base_revision_id,
                    "follow_up_text": "第二天加一个轻松街区",
                },
                headers={
                    "Origin": "http://testserver",
                    "X-Idempotency-Key": "replan-a",
                },
            )
            stale = client.post(
                f"/trips/{trip_id}/replan",
                json={
                    "base_revision_id": base_revision_id,
                    "follow_up_text": "第三天再加一个博物馆",
                },
                headers={
                    "Origin": "http://testserver",
                    "X-Idempotency-Key": "replan-b",
                },
            )

        self.assertEqual(applied.status_code, 200)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["error"]["code"], "stale_base_revision")

        revision_2 = applied.json()["current_revision"]["id"]
        undone = client.post(
            f"/trips/{trip_id}/revisions/{revision_2}/undo",
            json={"base_revision_id": revision_2},
            headers={
                "Origin": "http://testserver",
                "X-Idempotency-Key": "undo-replan-a",
            },
        )

        self.assertEqual(undone.status_code, 200)
        self.assertEqual(undone.json()["current_revision"]["revision_number"], 3)
        self.assertEqual(undone.json()["current_revision"]["source_type"], "replan_undo")
        self.assertEqual(undone.json()["current_revision"]["restored_from_revision_id"], base_revision_id)
        self.assertEqual(undone.json()["itinerary"]["trip_days"], 1)

        history = client.get(f"/trips/{trip_id}/revisions").json()["revisions"]
        self.assertEqual([revision["revision_number"] for revision in history], [3, 2, 1])


def simple_itinerary(trip_days: int = 1, *, with_intent: bool = False) -> ItineraryResponse:
    return ItineraryResponse(
        trip_days=trip_days,
        planning_anchor_source=PlanningAnchorSource(
            source_type="city",
            source_name="上海",
        ),
        trip_intent=simple_trip_intent(trip_days) if with_intent else None,
        days=[],
    )


def simple_trip_intent(trip_days: int) -> TripIntentEnvelope:
    current_intent = RegenerationIntentSummary(
        city="上海",
        trip_days=trip_days,
        suggested_trip_days=trip_days,
        trip_days_basis="explicit",
    )
    return TripIntentEnvelope(
        source=TripIntentEnvelopeSource.FOLLOW_UP,
        raw_text=None,
        latest_follow_up_text=None,
        current_intent=current_intent,
        summary_lines=[],
    )


def fake_trace():
    return SimpleNamespace(
        planner_run_id="run-replan",
        planner_version="planner-test",
        schema_version="1.0",
        trace_digest="trace-replan",
    )


if __name__ == "__main__":
    unittest.main()

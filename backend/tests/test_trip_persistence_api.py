from __future__ import annotations

import tempfile
import unittest
import sqlite3
import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.planner.trace import PlannerInputSnapshot, PlannerResultSummary, PlannerTrace
from app.schemas import (
    ItineraryResponse,
    PlanningAnchorSource,
    RegenerationIntentSummary,
    ReplanItineraryResponse,
    TripIntentEnvelope,
    TripIntentEnvelopeSource,
)
from app.trips.dependencies import reset_trip_repository_cache_for_tests
from tests.test_trip_mutation_commands import command_itinerary


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
            preview = client.post(
                f"/trips/{trip_id}/replan/preview",
                json={
                    "base_revision_id": base_revision_id,
                    "follow_up_text": "第二天加一个轻松街区",
                },
                headers={"Origin": "http://testserver"},
            )
        proposal = preview.json()["proposal"]
        with patch("app.trips.service.execute_replan_from_itinerary") as execute_replan_apply:
            execute_replan_apply.side_effect = AssertionError("apply must not execute planner")
            first = client.post(
                f"/trips/{trip_id}/replan/proposals/{proposal['id']}/apply",
                json={
                    "base_revision_id": base_revision_id,
                    "proposal_digest": proposal["proposal_digest"],
                },
                headers={
                    "Origin": "http://testserver",
                    "X-Idempotency-Key": "same-replan",
                },
            )
            retried = client.post(
                f"/trips/{trip_id}/replan/proposals/{proposal['id']}/apply",
                json={
                    "base_revision_id": base_revision_id,
                    "proposal_digest": proposal["proposal_digest"],
                },
                headers={
                    "Origin": "http://testserver",
                    "X-Idempotency-Key": "same-replan",
                },
            )

        self.assertEqual(preview.status_code, 200)
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
        self.assertEqual(execute_replan_apply.call_count, 0)

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
        proposal = preview.json()["proposal"]
        mismatched_apply = client.post(
            f"/trips/{trip_id}/replan/proposals/{proposal['id']}/apply",
            json={
                "base_revision_id": base_revision_id,
                "proposal_digest": "wrong-preview-digest",
            },
            headers={
                "Origin": "http://testserver",
                "X-Idempotency-Key": "bad-preview",
            },
        )
        rejected_raw_apply = client.post(
            f"/trips/{trip_id}/replan/proposals/{proposal['id']}/apply",
            json={
                "base_revision_id": base_revision_id,
                "follow_up_text": "第二天加一个轻松街区",
            },
            headers={
                "Origin": "http://testserver",
                "X-Idempotency-Key": "raw-apply",
            },
        )

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.json()["proposal"]["status"], "pending")
        self.assertEqual(preview.json()["proposal"]["source_type"], "replan_patch")
        self.assertEqual(preview.json()["proposal"]["base_revision_id"], base_revision_id)
        self.assertEqual(preview.json()["proposal"]["validation_report"]["critical_passed"], True)
        self.assertNotIn("第二天加一个轻松街区", str(preview.json()["replan_result"]))
        self.assertEqual(mismatched_apply.status_code, 409)
        self.assertEqual(mismatched_apply.json()["error"]["code"], "proposal_digest_mismatch")
        self.assertEqual(rejected_raw_apply.status_code, 422)

        history = client.get(f"/trips/{trip_id}/revisions").json()["revisions"]
        self.assertEqual([revision["revision_number"] for revision in history], [1])

    def test_replan_apply_rejects_expired_proposal_without_new_revision(self) -> None:
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

        with (
            patch(
                "app.trips.service.execute_replan_from_itinerary",
                return_value=(
                    ReplanItineraryResponse(
                        trip_intent=simple_trip_intent(2),
                        itinerary=simple_itinerary(2, with_intent=True),
                    ),
                    fake_trace(),
                ),
            ),
            patch("app.trips.service.get_trip_replan_proposal_ttl_seconds", return_value=-1.0),
        ):
            preview = client.post(
                f"/trips/{trip_id}/replan/preview",
                json={
                    "base_revision_id": base_revision_id,
                    "follow_up_text": "第二天加一个轻松街区",
                },
                headers={"Origin": "http://testserver"},
            )

        proposal = preview.json()["proposal"]
        expired = client.post(
            f"/trips/{trip_id}/replan/proposals/{proposal['id']}/apply",
            json={
                "base_revision_id": base_revision_id,
                "proposal_digest": proposal["proposal_digest"],
            },
            headers={
                "Origin": "http://testserver",
                "X-Idempotency-Key": "expired-proposal",
            },
        )

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(expired.status_code, 409)
        self.assertEqual(expired.json()["error"]["code"], "mutation_proposal_expired")
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
            preview = client.post(
                f"/trips/{trip_id}/replan/preview",
                json={
                    "base_revision_id": base_revision_id,
                    "follow_up_text": "第二天加一个轻松街区",
                },
                headers={"Origin": "http://testserver"},
            )
        proposal = preview.json()["proposal"]
        applied = client.post(
            f"/trips/{trip_id}/replan/proposals/{proposal['id']}/apply",
            json={
                "base_revision_id": base_revision_id,
                "proposal_digest": proposal["proposal_digest"],
            },
            headers={
                "Origin": "http://testserver",
                "X-Idempotency-Key": "replan-a",
            },
        )
        with patch(
            "app.trips.service.execute_replan_from_itinerary",
            return_value=(
                ReplanItineraryResponse(
                    trip_intent=simple_trip_intent(3),
                    itinerary=simple_itinerary(3, with_intent=True),
                ),
                fake_trace("run-replan-b"),
            ),
        ):
            stale_preview = client.post(
                f"/trips/{trip_id}/replan/preview",
                json={
                    "base_revision_id": base_revision_id,
                    "follow_up_text": "第三天再加一个博物馆",
                },
                headers={"Origin": "http://testserver"},
            )

        self.assertEqual(applied.status_code, 200)
        self.assertEqual(stale_preview.status_code, 409)
        self.assertEqual(stale_preview.json()["error"]["code"], "stale_mutation_proposal")

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
        repeat_undo = client.post(
            f"/trips/{trip_id}/revisions/{revision_2}/undo",
            json={"base_revision_id": revision_2},
            headers={
                "Origin": "http://testserver",
                "X-Idempotency-Key": "undo-replan-b",
            },
        )
        self.assertEqual(repeat_undo.status_code, 409)
        self.assertEqual(repeat_undo.json()["error"]["code"], "undo_target_not_current")

        history = client.get(f"/trips/{trip_id}/revisions").json()["revisions"]
        self.assertEqual([revision["revision_number"] for revision in history], [3, 2, 1])

    def test_route_edit_typed_mutation_preview_apply_reload_and_undo(self) -> None:
        client = TestClient(app)
        with patch(
            "app.trips.service.build_itinerary_response",
            return_value=command_itinerary(),
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
        base_names = flattened_names(created.json()["itinerary"])
        self.assertEqual(base_names, ["上海博物馆", "豫园", "外滩"])
        yu_id = stop_id_by_name(created.json()["itinerary"], "豫园")
        museum_id = stop_id_by_name(created.json()["itinerary"], "上海博物馆")

        preview = client.post(
            f"/trips/{trip_id}/mutations/preview",
            json={
                "base_revision_id": base_revision_id,
                "mutation_kind": "route_edit",
                "commands": [
                    {
                        "type": "move_stop",
                        "stop_id": yu_id,
                        "target_day": 1,
                        "target_block": "morning",
                        "placement": {"before_stop_id": museum_id},
                    }
                ],
            },
            headers={"Origin": "http://testserver"},
        )
        proposal = preview.json()["proposal"]
        applied = client.post(
            f"/trips/{trip_id}/mutation-proposals/{proposal['id']}/apply",
            json={
                "base_revision_id": base_revision_id,
                "proposal_digest": proposal["proposal_digest"],
            },
            headers={
                "Origin": "http://testserver",
                "X-Idempotency-Key": "route-edit-apply",
            },
        )
        reloaded = client.get(f"/trips/{trip_id}")
        revision_2 = applied.json()["current_revision"]["id"]
        undone = client.post(
            f"/trips/{trip_id}/revisions/{revision_2}/undo",
            json={"base_revision_id": revision_2},
            headers={
                "Origin": "http://testserver",
                "X-Idempotency-Key": "route-edit-undo",
            },
        )

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(proposal["source_type"], "route_edit")
        self.assertEqual(proposal["execution_kind"], "typed_command")
        self.assertEqual(proposal["command_schema_version"], "1.0")
        self.assertEqual(proposal["mutation_kind"], "route_edit")
        self.assertEqual(proposal["commands"][0]["type"], "move_stop")
        self.assertIn("route_segments", proposal["invalidated_surfaces"])
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(applied.json()["current_revision"]["source_type"], "route_edit")
        self.assertEqual(applied.json()["current_revision"]["content_digest"], proposal["preview_content_digest"])
        self.assertEqual(
            operation_metadata_for_revision(
                Path(self.temp_dir.name) / "api-trip-store.sqlite3",
                applied.json()["current_revision"]["id"],
            )["command_digest"],
            proposal["command_digest"],
        )
        self.assertEqual(flattened_names(applied.json()["itinerary"]), ["豫园", "上海博物馆", "外滩"])
        self.assertEqual(flattened_names(reloaded.json()["itinerary"]), ["豫园", "上海博物馆", "外滩"])
        self.assertEqual(undone.status_code, 200)
        self.assertEqual(undone.json()["current_revision"]["source_type"], "mutation_undo")
        self.assertEqual(flattened_names(undone.json()["itinerary"]), base_names)
        self.assertEqual(undone.json()["current_revision"]["restored_from_revision_id"], base_revision_id)

    def test_swap_typed_mutation_is_idempotent_and_preserves_stable_identity(self) -> None:
        client = TestClient(app)
        with patch(
            "app.trips.service.build_itinerary_response",
            return_value=command_itinerary(),
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
        museum_id = stop_id_by_name(created.json()["itinerary"], "上海博物馆")
        bund_id = stop_id_by_name(created.json()["itinerary"], "外滩")

        preview = client.post(
            f"/trips/{trip_id}/mutations/preview",
            json={
                "base_revision_id": base_revision_id,
                "mutation_kind": "swap",
                "commands": [
                    {"type": "swap_stops", "first_stop_id": museum_id, "second_stop_id": bund_id}
                ],
            },
            headers={"Origin": "http://testserver"},
        )
        proposal = preview.json()["proposal"]
        first = client.post(
            f"/trips/{trip_id}/mutation-proposals/{proposal['id']}/apply",
            json={
                "base_revision_id": base_revision_id,
                "proposal_digest": proposal["proposal_digest"],
            },
            headers={
                "Origin": "http://testserver",
                "X-Idempotency-Key": "swap-apply",
            },
        )
        retried = client.post(
            f"/trips/{trip_id}/mutation-proposals/{proposal['id']}/apply",
            json={
                "base_revision_id": base_revision_id,
                "proposal_digest": proposal["proposal_digest"],
            },
            headers={
                "Origin": "http://testserver",
                "X-Idempotency-Key": "swap-apply",
            },
        )
        duplicate_with_new_key = client.post(
            f"/trips/{trip_id}/mutation-proposals/{proposal['id']}/apply",
            json={
                "base_revision_id": base_revision_id,
                "proposal_digest": proposal["proposal_digest"],
            },
            headers={
                "Origin": "http://testserver",
                "X-Idempotency-Key": "swap-apply-after-lost-response",
            },
        )
        revision_2 = first.json()["current_revision"]["id"]
        undone = client.post(
            f"/trips/{trip_id}/revisions/{revision_2}/undo",
            json={"base_revision_id": revision_2},
            headers={
                "Origin": "http://testserver",
                "X-Idempotency-Key": "undo-swap",
            },
        )

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(proposal["source_type"], "swap")
        self.assertEqual(proposal["mutation_kind"], "swap")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["current_revision"]["source_type"], "swap")
        museum = find_item(first.json()["itinerary"], "上海博物馆")
        bund = find_item(first.json()["itinerary"], "外滩")
        self.assertEqual(museum["stable_id"], museum_id)
        self.assertEqual(bund["stable_id"], bund_id)
        self.assertEqual(museum["start_time"], "14:30:00")
        self.assertEqual(bund["start_time"], "09:00:00")
        self.assertEqual(first.json()["current_revision"]["id"], retried.json()["current_revision"]["id"])
        self.assertTrue(retried.json()["persistence"]["idempotent_replay"])
        self.assertEqual(first.json()["current_revision"]["id"], duplicate_with_new_key.json()["current_revision"]["id"])
        self.assertEqual(undone.status_code, 200)
        self.assertEqual(undone.json()["current_revision"]["source_type"], "mutation_undo")
        self.assertEqual(undone.json()["current_revision"]["restored_from_revision_id"], base_revision_id)
        history = client.get(f"/trips/{trip_id}/revisions").json()["revisions"]
        self.assertEqual([revision["revision_number"] for revision in history], [3, 2, 1])

    def test_typed_mutation_rejects_fixed_item_and_stale_base_without_revision(self) -> None:
        client = TestClient(app)
        with patch(
            "app.trips.service.build_itinerary_response",
            return_value=command_itinerary(fixed_museum=True),
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
        museum_id = stop_id_by_name(created.json()["itinerary"], "上海博物馆")
        yu_id = stop_id_by_name(created.json()["itinerary"], "豫园")
        fixed_preview = client.post(
            f"/trips/{trip_id}/mutations/preview",
            json={
                "base_revision_id": base_revision_id,
                "mutation_kind": "route_edit",
                "commands": [{"type": "remove_stop", "stop_id": museum_id}],
            },
            headers={"Origin": "http://testserver"},
        )
        valid_preview = client.post(
            f"/trips/{trip_id}/mutations/preview",
            json={
                "base_revision_id": base_revision_id,
                "mutation_kind": "route_edit",
                "commands": [{"type": "remove_stop", "stop_id": yu_id}],
            },
            headers={"Origin": "http://testserver"},
        )
        proposal = valid_preview.json()["proposal"]
        applied = client.post(
            f"/trips/{trip_id}/mutation-proposals/{proposal['id']}/apply",
            json={
                "base_revision_id": base_revision_id,
                "proposal_digest": proposal["proposal_digest"],
            },
            headers={
                "Origin": "http://testserver",
                "X-Idempotency-Key": "remove-yu",
            },
        )
        stale_preview = client.post(
            f"/trips/{trip_id}/mutations/preview",
            json={
                "base_revision_id": base_revision_id,
                "mutation_kind": "route_edit",
                "commands": [{"type": "remove_stop", "stop_id": yu_id}],
            },
            headers={"Origin": "http://testserver"},
        )

        self.assertEqual(fixed_preview.status_code, 422)
        self.assertEqual(fixed_preview.json()["error"]["code"], "mutation_command_failed")
        self.assertEqual(
            fixed_preview.json()["error"]["reason_code"],
            "fixed_event_mutation_forbidden",
        )
        self.assertEqual(valid_preview.status_code, 200)
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(stale_preview.status_code, 409)
        self.assertEqual(stale_preview.json()["error"]["code"], "stale_mutation_proposal")
        self.assertEqual(len(client.get(f"/trips/{trip_id}/revisions").json()["revisions"]), 2)


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


def flattened_names(itinerary: dict) -> list[str]:
    return [
        item["name"]
        for day in itinerary["days"]
        for block in day["blocks"]
        for item in block["items"]
    ]


def find_item(itinerary: dict, name: str) -> dict:
    return next(
        item
        for day in itinerary["days"]
        for block in day["blocks"]
        for item in block["items"]
        if item["name"] == name
    )


def stop_id_by_name(itinerary: dict, name: str) -> str:
    return find_item(itinerary, name)["stable_id"]


def operation_metadata_for_revision(database_path: Path, revision_id: str) -> dict:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT operation_metadata_json FROM revision_operations WHERE revision_id = ?",
            (revision_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise AssertionError(f"Missing operation metadata for revision {revision_id}")
    return json.loads(row["operation_metadata_json"])


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


def fake_trace(planner_run_id: str = "run-replan") -> PlannerTrace:
    return PlannerTrace(
        planner_run_id=planner_run_id,
        planner_version="planner-test",
        schema_version="1.0",
        trace_digest=f"trace-{planner_run_id}",
        input_summary=PlannerInputSnapshot(city="上海", trip_days=1),
        result_summary=PlannerResultSummary(
            status="ok",
            trip_days=1,
            scheduled_item_count=0,
        ),
    )


if __name__ == "__main__":
    unittest.main()

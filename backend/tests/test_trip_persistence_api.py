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
    CompletionTaskActionResponse,
    ExecutionTrustSummary,
    ItineraryCompletionOption,
    ItineraryResponse,
    PlanningAnchorSource,
    RegenerationIntentSummary,
    ReplanItineraryResponse,
    ScheduledPOI,
    POIType,
    TimeBlockType,
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

    def test_persisted_trip_retains_execution_trust_fact_boundaries(self) -> None:
        client = TestClient(app)
        itinerary = simple_itinerary().model_copy(
            update={
                "execution_trust": ExecutionTrustSummary.model_validate(
                    {
                        "status": "needs_attention",
                        "headline": "路线仍有待核实的执行事实。",
                        "blocking_reasons": [],
                        "warning_reasons": ["部分路线没有可验证的 provider 数据。"],
                        "facts": [
                            {
                                "key": "route-data",
                                "category": "route",
                                "status": "missing",
                                "source_kind": "missing_data",
                                "verification_status": "unavailable",
                                "freshness_status": "unknown",
                                "label": "路线数据",
                                "detail": "两段路线只使用了本地估算。",
                                "count": 2,
                            },
                            {
                                "key": "system-suggestions",
                                "category": "schedule",
                                "status": "heuristic",
                                "source_kind": "heuristic",
                                "verification_status": "not_applicable",
                                "freshness_status": "not_applicable",
                                "label": "系统补充",
                                "detail": "这些停留点是系统建议。",
                                "count": 1,
                            },
                        ],
                    }
                )
            }
        )
        with patch("app.trips.service.build_itinerary_response", return_value=itinerary):
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

        self.assertEqual(created.status_code, 201, created.text)
        restored = client.get(f"/trips/{created.json()['trip']['id']}")

        self.assertEqual(restored.status_code, 200, restored.text)
        trust = restored.json()["itinerary"]["execution_trust"]
        self.assertEqual(trust["status"], "needs_attention")
        self.assertEqual(trust["facts"][0]["status"], "missing")
        self.assertEqual(trust["facts"][0]["freshness_status"], "unknown")
        self.assertEqual(trust["facts"][1]["status"], "heuristic")

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

    def test_local_repair_preview_is_non_persistent_and_apply_creates_one_child_revision(self) -> None:
        client = TestClient(app)
        with patch(
            "app.trips.service.build_itinerary_response",
            return_value=command_itinerary(system_yu=True),
        ):
            created = client.post(
                "/trips/plan",
                json={"itinerary_request": {"city": "上海", "trip_days": 1, "scenic_spots": [], "restaurants": []}},
            )
        trip_id = created.json()["trip"]["id"]
        base_revision_id = created.json()["current_revision"]["id"]
        yu_id = stop_id_by_name(created.json()["itinerary"], "豫园")

        preview = client.post(
            f"/trips/{trip_id}/mutations/preview",
            json={
                "base_revision_id": base_revision_id,
                "mutation_kind": "route_edit",
                "repair": {"target_day": 1, "goal": "relax_day"},
                "commands": [{"type": "remove_stop", "stop_id": yu_id}],
            },
            headers={"Origin": "http://testserver"},
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        proposal = preview.json()["proposal"]
        self.assertEqual(len(client.get(f"/trips/{trip_id}/revisions").json()["revisions"]), 1)
        self.assertNotIn("豫园", flattened_names(preview.json()["itinerary"]))
        self.assertEqual(
            preview.json()["impact_summary"]["execution_evidence"],
            {"planner_calls": 0, "parser_calls": 0, "llm_calls": 0, "route_provider_calls": 0},
        )

        with patch("app.trips.service.build_itinerary_response", side_effect=AssertionError("local repair must not invoke planner")):
            applied = client.post(
                f"/trips/{trip_id}/mutation-proposals/{proposal['id']}/apply",
                json={"base_revision_id": base_revision_id, "proposal_digest": proposal["proposal_digest"]},
                headers={"Origin": "http://testserver", "X-Idempotency-Key": "local-repair-apply"},
            )
        self.assertEqual(applied.status_code, 200, applied.text)
        self.assertEqual(applied.json()["current_revision"]["revision_number"], 2)
        self.assertEqual(applied.json()["current_revision"]["parent_revision_id"], base_revision_id)
        self.assertNotIn("豫园", flattened_names(applied.json()["itinerary"]))
        replay = client.post(
            f"/trips/{trip_id}/mutation-proposals/{proposal['id']}/apply",
            json={"base_revision_id": base_revision_id, "proposal_digest": proposal["proposal_digest"]},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "local-repair-apply"},
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()["persistence"]["idempotent_replay"])
        metadata = operation_metadata_for_revision(
            Path(self.temp_dir.name) / "api-trip-store.sqlite3",
            applied.json()["current_revision"]["id"],
        )
        self.assertEqual(metadata["impact_summary"]["repair"], {"target_day": 1, "goal": "relax_day"})

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

    def test_candidate_registration_persists_without_revision_and_deduplicates(self) -> None:
        client, trip_id, base_revision_id = create_command_trip()

        first = register_candidate(client, trip_id, "思南书局")
        duplicate = register_candidate(client, trip_id, "思南书局", key="candidate-duplicate")
        candidates = client.get(f"/trips/{trip_id}/candidates")
        history = client.get(f"/trips/{trip_id}/revisions")

        self.assertEqual(first.status_code, 201)
        self.assertFalse(first.json()["deduplicated"])
        self.assertEqual(duplicate.status_code, 201)
        self.assertTrue(duplicate.json()["deduplicated"])
        self.assertEqual(first.json()["candidate"]["id"], duplicate.json()["candidate"]["id"])
        self.assertEqual(candidates.status_code, 200)
        self.assertEqual(len(candidates.json()["candidates"]), 1)
        self.assertEqual(candidates.json()["candidates"][0]["workflow_state"], "pending")
        self.assertEqual([revision["id"] for revision in history.json()["revisions"]], [base_revision_id])

    def test_candidate_reject_and_defer_are_workflow_decisions_without_revision(self) -> None:
        client, trip_id, base_revision_id = create_command_trip()
        candidate = register_candidate(client, trip_id, "外白渡桥").json()["candidate"]

        rejected = client.post(
            f"/trips/{trip_id}/candidates/{candidate['id']}/decisions",
            json={
                "decision": "reject",
                "reason_code": "NOT_INTERESTED",
                "base_revision_id": base_revision_id,
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "reject-candidate"},
        )
        restored = client.post(
            f"/trips/{trip_id}/candidates/{candidate['id']}/decisions",
            json={
                "decision": "restore_pending",
                "reason_code": "RESTORED_TO_PENDING",
                "base_revision_id": base_revision_id,
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "restore-candidate"},
        )
        deferred = client.post(
            f"/trips/{trip_id}/candidates/{candidate['id']}/decisions",
            json={
                "decision": "defer",
                "reason_code": "USER_DEFERRED",
                "base_revision_id": base_revision_id,
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "defer-candidate"},
        )

        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.json()["candidate"]["workflow_state"], "rejected")
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()["candidate"]["workflow_state"], "pending")
        self.assertEqual(deferred.status_code, 200)
        self.assertEqual(deferred.json()["candidate"]["workflow_state"], "deferred")
        self.assertEqual(len(client.get(f"/trips/{trip_id}/revisions").json()["revisions"]), 1)

    def test_candidate_decision_idempotent_retry_returns_same_decision_without_revision(self) -> None:
        client, trip_id, base_revision_id = create_command_trip()
        candidate = register_candidate(client, trip_id, "武康大楼").json()["candidate"]

        first = client.post(
            f"/trips/{trip_id}/candidates/{candidate['id']}/decisions",
            json={
                "decision": "reject",
                "reason_code": "NOT_INTERESTED",
                "base_revision_id": base_revision_id,
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "reject-wukang"},
        )
        retried = client.post(
            f"/trips/{trip_id}/candidates/{candidate['id']}/decisions",
            json={
                "decision": "reject",
                "reason_code": "NOT_INTERESTED",
                "base_revision_id": base_revision_id,
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "reject-wukang"},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(first.json()["decision"]["id"], retried.json()["decision"]["id"])
        self.assertTrue(retried.json()["idempotent_replay"])
        self.assertEqual(len(client.get(f"/trips/{trip_id}/revisions").json()["revisions"]), 1)

    def test_rejected_candidate_admission_is_rejected_without_revision(self) -> None:
        client, trip_id, base_revision_id = create_command_trip()
        candidate = register_candidate(client, trip_id, "思南公馆", with_facts=True).json()["candidate"]
        client.post(
            f"/trips/{trip_id}/candidates/{candidate['id']}/decisions",
            json={
                "decision": "reject",
                "reason_code": "NOT_INTERESTED",
                "base_revision_id": base_revision_id,
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "reject-before-admit"},
        )
        preview = preview_candidate_admission(client, trip_id, base_revision_id, candidate["id"])

        self.assertEqual(preview.status_code, 422)
        self.assertEqual(preview.json()["error"]["reason_code"], "candidate_rejected")
        self.assertEqual(len(client.get(f"/trips/{trip_id}/revisions").json()["revisions"]), 1)

    def test_cross_trip_candidate_admission_is_rejected_without_revision(self) -> None:
        source_client, source_trip_id, _source_revision_id = create_command_trip()
        target_client, target_trip_id, target_revision_id = create_command_trip()
        source_candidate = register_candidate(
            source_client,
            source_trip_id,
            "徐家汇书院",
            key="source-candidate",
            with_facts=True,
        ).json()["candidate"]

        preview = preview_candidate_admission(
            target_client,
            target_trip_id,
            target_revision_id,
            source_candidate["id"],
        )

        self.assertEqual(preview.status_code, 404)
        self.assertEqual(preview.json()["error"]["code"], "candidate_not_found")
        self.assertEqual(len(target_client.get(f"/trips/{target_trip_id}/revisions").json()["revisions"]), 1)

    def test_valid_candidate_admission_creates_revision_and_scheduled_decision(self) -> None:
        client, trip_id, base_revision_id = create_command_trip()
        candidate = register_candidate(client, trip_id, "思南公馆", with_facts=True).json()["candidate"]
        preview = preview_candidate_admission(client, trip_id, base_revision_id, candidate["id"])
        proposal = preview.json()["proposal"]
        applied = client.post(
            f"/trips/{trip_id}/mutation-proposals/{proposal['id']}/apply",
            json={
                "base_revision_id": base_revision_id,
                "proposal_digest": proposal["proposal_digest"],
            },
            headers={
                "Origin": "http://testserver",
                "X-Idempotency-Key": "candidate-admission",
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
                "X-Idempotency-Key": "candidate-admission",
            },
        )
        candidates = client.get(f"/trips/{trip_id}/candidates").json()["candidates"]
        metadata = operation_metadata_for_revision(
            Path(self.temp_dir.name) / "api-trip-store.sqlite3",
            applied.json()["current_revision"]["id"],
        )

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(proposal["source_type"], "candidate_admission")
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(applied.json()["current_revision"]["source_type"], "candidate_admission")
        self.assertIn("思南公馆", flattened_names(applied.json()["itinerary"]))
        self.assertEqual(applied.json()["current_revision"]["id"], retried.json()["current_revision"]["id"])
        self.assertTrue(retried.json()["persistence"]["idempotent_replay"])
        self.assertEqual(candidates[0]["workflow_state"], "scheduled")
        self.assertEqual(metadata["candidate_admission"]["candidate_id"], candidate["id"])

    def test_missing_location_candidate_admission_returns_repair_required_without_revision(self) -> None:
        client, trip_id, base_revision_id = create_command_trip()
        candidate = register_candidate(client, trip_id, "只有名字的咖啡馆").json()["candidate"]
        preview = preview_candidate_admission(client, trip_id, base_revision_id, candidate["id"])

        self.assertEqual(preview.status_code, 409)
        self.assertEqual(preview.json()["error"]["code"], "candidate_admission_repair_required")
        self.assertIn("candidate_missing_location", str(preview.json()["error"]["repair"]))
        self.assertNotIn("(0, 0)", str(preview.json()))
        self.assertEqual(len(client.get(f"/trips/{trip_id}/revisions").json()["revisions"]), 1)

    def test_completion_undo_creates_compensating_revision(self) -> None:
        client, trip_id, base_revision_id = create_command_trip()
        inserted = ScheduledPOI.model_validate(find_item(command_itinerary().model_dump(mode="json"), "豫园"))
        selected_candidate = ItineraryCompletionOption(
            name="豫园",
            type=POIType.SCENIC,
            suggested_day=1,
            suggested_block=TimeBlockType.AFTERNOON,
            reasoning_summary="Fits the requested afternoon repair.",
            itinerary_relation_summary="A deterministic candidate selected from the preview.",
        )
        next_itinerary = command_itinerary().model_copy(
            update={
                "days": command_itinerary().days,
            }
        )
        with patch(
            "app.trips.service.execute_completion_task_action",
            return_value=CompletionTaskActionResponse(
                task_id="fill-afternoon",
                applied=True,
                summary="Inserted completion item.",
                inserted_item=inserted,
                itinerary=next_itinerary,
            ),
        ):
            applied = client.post(
                f"/trips/{trip_id}/completion-task",
                json={
                    "base_revision_id": base_revision_id,
                    "task_id": "fill-afternoon",
                    "task_instance_key": "fill-afternoon-1",
                    "day": 1,
                    "block_type": "afternoon",
                    "selected_candidate": selected_candidate.model_dump(mode="json"),
                    "completion_candidate_history": [selected_candidate.model_dump(mode="json")],
                },
                headers={
                    "Origin": "http://testserver",
                    "X-Idempotency-Key": "completion-apply",
                },
            )
        revision_2 = applied.json()["current_revision"]["id"]
        undone = client.post(
            f"/trips/{trip_id}/revisions/{revision_2}/undo",
            json={"base_revision_id": revision_2},
            headers={
                "Origin": "http://testserver",
                "X-Idempotency-Key": "completion-undo",
            },
        )
        retried = client.post(
            f"/trips/{trip_id}/revisions/{revision_2}/undo",
            json={"base_revision_id": revision_2},
            headers={
                "Origin": "http://testserver",
                "X-Idempotency-Key": "completion-undo",
            },
        )

        self.assertEqual(applied.status_code, 200)
        self.assertEqual(applied.json()["current_revision"]["source_type"], "completion_patch")
        self.assertEqual(undone.status_code, 200)
        self.assertEqual(undone.json()["current_revision"]["source_type"], "completion_undo")
        self.assertEqual(undone.json()["current_revision"]["restored_from_revision_id"], base_revision_id)
        self.assertEqual(undone.json()["current_revision"]["id"], retried.json()["current_revision"]["id"])
        self.assertEqual([revision["revision_number"] for revision in client.get(f"/trips/{trip_id}/revisions").json()["revisions"]], [3, 2, 1])


def create_command_trip() -> tuple[TestClient, str, str]:
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
    return client, created.json()["trip"]["id"], created.json()["current_revision"]["id"]


def register_candidate(
    client: TestClient,
    trip_id: str,
    name: str,
    *,
    key: str = "candidate-register",
    with_facts: bool = False,
):
    payload = {
        "candidate_type": "place",
        "display_name": name,
        "category": "scenic",
        "source_kind": "manual_entry",
    }
    if with_facts:
        payload.update(
            {
                "coordinates": {"latitude": 31.214, "longitude": 121.454},
                "estimated_duration_minutes": 75,
                "preferred_time_block": "afternoon",
                "explicit_day_reference": "1",
                "address_summary": "上海市黄浦区",
            }
        )
    return client.post(
        f"/trips/{trip_id}/candidates",
        json=payload,
        headers={"Origin": "http://testserver", "X-Idempotency-Key": key},
    )


def preview_candidate_admission(
    client: TestClient,
    trip_id: str,
    base_revision_id: str,
    candidate_id: str,
):
    return client.post(
        f"/trips/{trip_id}/mutations/preview",
        json={
            "base_revision_id": base_revision_id,
            "mutation_kind": "candidate_admission",
            "commands": [
                {
                    "type": "add_candidate_stop",
                    "candidate_id": candidate_id,
                    "target_day": 1,
                    "target_block": "afternoon",
                    "requested_start_time": "16:15:00",
                    "placement": {"at_end": True},
                }
            ],
        },
        headers={"Origin": "http://testserver"},
    )


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

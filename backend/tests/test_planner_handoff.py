from __future__ import annotations

import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.routes.itinerary import build_itinerary_response
from app.main import app
from app.trips.access import hash_idempotency_key
from app.trips.dependencies import get_trip_repository, reset_trip_repository_cache_for_tests
from app.trips.digests import request_digest
from app.trips.intent_contracts import PlaceIdentity, SourceLinkedTripIntentEnvelope
from app.trips.planner_handoff import build_planner_handoff_input
from app.trips.service import format_utc
from tests.test_trip_mutation_commands import command_itinerary
from tests.test_trip_persistence_api import simple_itinerary


class PlannerHandoffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            "os.environ",
            {
                "TRIP_STORE_MODE": "sqlite",
                "TRIP_STORE_PATH": str(Path(self.temp_dir.name) / "planner-handoff.sqlite3"),
                "TRIP_ALLOWED_ORIGINS": "http://testserver",
                "CORS_ALLOW_ORIGINS": "http://testserver",
            },
        )
        self.env.start()
        reset_trip_repository_cache_for_tests()
        self.client = TestClient(app)
        self.trip_id, self.base_revision_id = create_saved_trip(self.client)

    def tearDown(self) -> None:
        reset_trip_repository_cache_for_tests()
        self.env.stop()
        self.temp_dir.cleanup()

    def test_confirmed_intent_preview_applies_frozen_snapshot_and_reloads(self) -> None:
        candidate = register_verified_candidate(self.client, self.trip_id)
        intent = compile_ready_intent(self.client, self.trip_id, self.base_revision_id, candidate["id"])
        planned = command_itinerary()
        planned.days[0].blocks[0].items[0].candidate_id = candidate["id"]

        with patch("app.trips.service.build_itinerary_response", return_value=planned) as planner:
            preview = self.client.post(
                f"/trips/{self.trip_id}/planner-handoff/preview",
                json={"base_revision_id": self.base_revision_id, "intent_revision_id": intent["id"]},
                headers={"Origin": "http://testserver"},
            )
        self.assertEqual(preview.status_code, 200, preview.text)
        body = preview.json()
        self.assertEqual(body["planner_run"]["intent_revision_id"], intent["id"])
        self.assertEqual(body["planner_run"]["status"], "pending")
        self.assertEqual(body["proposal"]["execution_kind"], "planner_handoff_snapshot")
        self.assertTrue(body["source_links"])
        scheduled = body["itinerary"]["days"][0]["blocks"][0]["items"][0]
        self.assertEqual(scheduled["candidate_id"], candidate["id"])
        self.assertEqual(scheduled["candidate_provenance"]["intent_field_path"], "poi.must_candidates")
        self.assertEqual(planner.call_args.kwargs["trace_collector"].planner_run_id, body["planner_run"]["id"])

        with patch("app.trips.service.build_itinerary_response", side_effect=AssertionError("apply must not rerun planner")):
            applied = self.client.post(
                f"/trips/{self.trip_id}/planner-handoff/proposals/{body['proposal']['id']}/apply",
                json={
                    "base_revision_id": self.base_revision_id,
                    "intent_revision_id": intent["id"],
                    "proposal_digest": body["proposal"]["proposal_digest"],
                },
                headers={"Origin": "http://testserver", "X-Idempotency-Key": "handoff-apply-one"},
            )
        self.assertEqual(applied.status_code, 200, applied.text)
        applied_body = applied.json()
        self.assertEqual(applied_body["current_revision"]["source_type"], "planner_intent_handoff")
        self.assertEqual(applied_body["planner_run"]["status"], "applied")
        self.assertEqual(applied_body["planner_run"]["applied_revision_id"], applied_body["current_revision"]["id"])

        replay = self.client.post(
            f"/trips/{self.trip_id}/planner-handoff/proposals/{body['proposal']['id']}/apply",
            json={
                "base_revision_id": self.base_revision_id,
                "intent_revision_id": intent["id"],
                "proposal_digest": body["proposal"]["proposal_digest"],
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "handoff-apply-one"},
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()["persistence"]["idempotent_replay"])
        current = self.client.get(f"/trips/{self.trip_id}")
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.json()["current_revision"]["id"], applied_body["current_revision"]["id"])

    def test_unresolved_contract_does_not_create_handoff_run(self) -> None:
        compiled = self.client.post(
            f"/trips/{self.trip_id}/intent-envelope/compile",
            json={
                "base_revision_id": self.base_revision_id,
                "base_intent_revision_id": None,
                "structured_overrides": {"city": "上海"},
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "handoff-unresolved"},
        )
        self.assertEqual(compiled.status_code, 201, compiled.text)
        preview = self.client.post(
            f"/trips/{self.trip_id}/planner-handoff/preview",
            json={
                "base_revision_id": self.base_revision_id,
                "intent_revision_id": compiled.json()["revision"]["id"],
            },
            headers={"Origin": "http://testserver"},
        )
        self.assertEqual(preview.status_code, 422)
        self.assertEqual(preview.json()["error"]["code"], "planner_handoff_blocked")

    def test_stale_intent_cannot_apply_a_preview(self) -> None:
        candidate = register_verified_candidate(self.client, self.trip_id)
        intent = compile_ready_intent(self.client, self.trip_id, self.base_revision_id, candidate["id"])
        with patch("app.trips.service.build_itinerary_response", return_value=simple_itinerary(2)):
            preview = self.client.post(
                f"/trips/{self.trip_id}/planner-handoff/preview",
                json={"base_revision_id": self.base_revision_id, "intent_revision_id": intent["id"]},
                headers={"Origin": "http://testserver"},
            )
        self.assertEqual(preview.status_code, 200, preview.text)
        newer = self.client.post(
            f"/trips/{self.trip_id}/intent-envelope/{intent['id']}/edit",
            json={
                "base_revision_id": self.base_revision_id,
                "base_intent_revision_id": intent["id"],
                "field_updates": {"pace": "balanced"},
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "handoff-make-stale"},
        )
        self.assertEqual(newer.status_code, 201, newer.text)
        body = preview.json()
        applied = self.client.post(
            f"/trips/{self.trip_id}/planner-handoff/proposals/{body['proposal']['id']}/apply",
            json={
                "base_revision_id": self.base_revision_id,
                "intent_revision_id": intent["id"],
                "proposal_digest": body["proposal"]["proposal_digest"],
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "handoff-stale-apply"},
        )
        self.assertEqual(applied.status_code, 409, applied.text)
        self.assertEqual(applied.json()["error"]["code"], "stale_intent_revision")

    def test_candidate_without_canonical_identity_is_blocked(self) -> None:
        registered = self.client.post(
            f"/trips/{self.trip_id}/candidates",
            json={"candidate_type": "place", "display_name": "未核验地点", "source_kind": "manual_entry"},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "handoff-unverified-candidate"},
        )
        self.assertEqual(registered.status_code, 201, registered.text)
        intent = compile_ready_intent(self.client, self.trip_id, self.base_revision_id, registered.json()["candidate"]["id"])
        preview = self.client.post(
            f"/trips/{self.trip_id}/planner-handoff/preview",
            json={"base_revision_id": self.base_revision_id, "intent_revision_id": intent["id"]},
            headers={"Origin": "http://testserver"},
        )
        self.assertEqual(preview.status_code, 422)
        self.assertEqual(preview.json()["error"]["reason_code"], "intent_candidate_identity_not_verified")

    def test_handoff_maps_fixed_events_and_boundaries_without_name_resolution(self) -> None:
        candidate = register_verified_candidate(self.client, self.trip_id)
        compiled = self.client.post(
            f"/trips/{self.trip_id}/intent-envelope/compile",
            json={
                "base_revision_id": self.base_revision_id,
                "base_intent_revision_id": None,
                "structured_overrides": {
                    "city": "上海",
                    "trip_days": 2,
                    "start_date": "2026-08-01",
                    "timezone": "Asia/Shanghai",
                    "arrival_boundary": {
                        "local_datetime": "2026-08-01T10:00:00",
                        "timezone": "Asia/Shanghai",
                    },
                    "departure_boundary": {
                        "local_datetime": "2026-08-02T18:00:00",
                        "timezone": "Asia/Shanghai",
                    },
                    "availability_windows": [
                        {
                            "date": "2026-08-01",
                            "start_time": "11:00:00",
                            "end_time": "21:00:00",
                            "timezone": "Asia/Shanghai",
                        }
                    ],
                    "must_candidate_ids": [candidate["id"]],
                    "fixed_events": [
                        {
                            "event_id": "reservation-1",
                            "name": "外滩预约",
                            "place_candidate_id": candidate["id"],
                            "start_at": "2026-08-01T14:00:00",
                            "end_at": "2026-08-01T15:30:00",
                            "timezone": "Asia/Shanghai",
                        }
                    ],
                },
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "handoff-boundaries"},
        )
        self.assertEqual(compiled.status_code, 201, compiled.text)
        repository = get_trip_repository()
        revision = repository.get_intent_revision(trip_id=self.trip_id, revision_id=compiled.json()["revision"]["id"])
        result = build_planner_handoff_input(
            envelope=SourceLinkedTripIntentEnvelope.model_validate(revision.envelope),
            candidates=repository.list_candidates(trip_id=self.trip_id),
        )
        windows = {(window.day, window.available_start, window.available_end) for window in result.handoff.itinerary_request.availability_windows}
        self.assertIn((1, "10:00", None), windows)
        self.assertIn((1, "11:00", "21:00"), windows)
        self.assertIn((2, None, "18:00"), windows)
        fixed = result.handoff.itinerary_request.scenic_spots[0]
        self.assertEqual(len(result.handoff.itinerary_request.scenic_spots), 1)
        self.assertEqual(fixed.candidate_id, candidate["id"])
        self.assertEqual(fixed.fixed_day, 1)
        self.assertEqual(fixed.fixed_time_start.strftime("%H:%M"), "14:00")
        self.assertEqual(fixed.fixed_time_end.strftime("%H:%M"), "15:30")
        self.assertEqual(fixed.resolved_duration_minutes, 90)

    def test_handoff_reuses_verified_fixed_place_identity_with_its_reserved_time(self) -> None:
        candidate = register_verified_candidate(self.client, self.trip_id)
        compiled = self.client.post(
            f"/trips/{self.trip_id}/intent-envelope/compile",
            json={
                "base_revision_id": self.base_revision_id,
                "base_intent_revision_id": None,
                "structured_overrides": {
                    "city": "上海",
                    "trip_days": 2,
                    "start_date": "2026-08-01",
                    "timezone": "Asia/Shanghai",
                    "fixed_events": [{
                        "event_id": "museum-reservation",
                        "name": "上海博物馆预约",
                        "place_candidate_id": candidate["id"],
                        "fixed_day": 2,
                        "start_at": "2026-08-02T14:00:00",
                        "end_at": "2026-08-02T15:30:00",
                        "timezone": "Asia/Shanghai",
                    }],
                },
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "handoff-canonical-fixed"},
        )
        self.assertEqual(compiled.status_code, 201, compiled.text)
        repository = get_trip_repository()
        revision = repository.get_intent_revision(trip_id=self.trip_id, revision_id=compiled.json()["revision"]["id"])
        envelope = SourceLinkedTripIntentEnvelope.model_validate(revision.envelope)
        fixed_event = envelope.formal_contract.fixed_events[0].model_copy(update={"place_candidate_id": None})
        verified_identity = PlaceIdentity(
            stable_id="museum-reservation",
            original_name="上海博物馆",
            canonical_name="上海博物馆（人民广场馆）",
            city="上海",
            ownership="fixed",
            fixed_event_id="museum-reservation",
            resolution_status="verified",
            provider="amap",
            provider_place_id="fixture-shanghai-museum",
            latitude=31.2304,
            longitude=121.4737,
            category="museum",
            source_fragment_ids=["source_direct"],
        )
        formal = envelope.formal_contract.model_copy(update={
            "must_visit_places": [],
            "fixed_events": [fixed_event],
            "place_identities": [verified_identity],
        })
        result = build_planner_handoff_input(
            envelope=envelope.model_copy(update={"formal_contract": formal}),
            candidates=[],
        )
        fixed = result.handoff.itinerary_request.scenic_spots[0]
        self.assertEqual(fixed.candidate_id, "museum-reservation")
        self.assertEqual(fixed.canonical_place_id, "fixture-shanghai-museum")
        self.assertEqual(fixed.resolved_duration_minutes, 90)
        self.assertEqual(fixed.fixed_day, 2)
        self.assertEqual(fixed.fixed_time_start.strftime("%H:%M"), "14:00")
        self.assertEqual(fixed.fixed_time_end.strftime("%H:%M"), "15:30")
        self.assertIsNotNone(fixed.verified_place)

    def test_handoff_reuses_verified_direct_must_places_without_import_candidates(self) -> None:
        candidate = register_verified_candidate(self.client, self.trip_id)
        intent = compile_ready_intent(self.client, self.trip_id, self.base_revision_id, candidate["id"])
        repository = get_trip_repository()
        revision = repository.get_intent_revision(trip_id=self.trip_id, revision_id=intent["id"])
        envelope = SourceLinkedTripIntentEnvelope.model_validate(revision.envelope)
        hongyadong = PlaceIdentity(
            stable_id="must-hongyadong",
            original_name="洪崖洞",
            canonical_name="洪崖洞民俗风貌区",
            city="重庆",
            ownership="must",
            resolution_status="verified",
            provider="amap",
            provider_place_id="fixture-hongyadong",
            latitude=29.5630,
            longitude=106.5720,
            category="scenic",
            source_fragment_ids=["source_direct"],
        )
        shancheng = hongyadong.model_copy(update={
            "stable_id": "must-shancheng",
            "original_name": "山城步道",
            "canonical_name": "山城步道",
            "provider_place_id": "fixture-shancheng-walkway",
            "latitude": 29.5510,
            "longitude": 106.5690,
        })
        formal = envelope.formal_contract.model_copy(update={
            "must_visit_places": [],
            "fixed_events": [],
            "place_identities": [hongyadong, shancheng],
        })

        result = build_planner_handoff_input(
            envelope=envelope.model_copy(update={"formal_contract": formal}),
            candidates=[],
        )

        scenic = result.handoff.itinerary_request.scenic_spots
        self.assertEqual([item.name for item in scenic], ["洪崖洞民俗风貌区", "山城步道"])
        self.assertEqual([item.candidate_id for item in scenic], ["must-hongyadong", "must-shancheng"])
        self.assertTrue(all(item.verified_place is not None for item in scenic))

        itinerary = build_itinerary_response(result.handoff.itinerary_request)
        scheduled_names = [item.name for day in itinerary.days for block in day.blocks for item in block.items]
        self.assertTrue({"洪崖洞民俗风貌区", "山城步道"}.issubset(scheduled_names))

    def test_fixed_event_without_verified_place_is_blocked_before_planning(self) -> None:
        compiled = self.client.post(
            f"/trips/{self.trip_id}/intent-envelope/compile",
            json={
                "base_revision_id": self.base_revision_id,
                "base_intent_revision_id": None,
                "structured_overrides": {
                    "city": "上海",
                    "trip_days": 2,
                    "fixed_events": [{"name": "未核验预约", "fixed_day": 1, "location_text": "未知地点"}],
                },
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "handoff-unverified-fixed-event"},
        )
        self.assertEqual(compiled.status_code, 201, compiled.text)
        with patch("app.trips.service.build_itinerary_response") as planner:
            preview = self.client.post(
                f"/trips/{self.trip_id}/planner-handoff/preview",
                json={"base_revision_id": self.base_revision_id, "intent_revision_id": compiled.json()["revision"]["id"]},
                headers={"Origin": "http://testserver"},
            )
        self.assertEqual(preview.status_code, 422)
        self.assertEqual(preview.json()["error"]["reason_code"], "fixed_event_identity_not_verified")
        planner.assert_not_called()

    def test_two_sqlite_connections_apply_one_handoff_revision(self) -> None:
        candidate = register_verified_candidate(self.client, self.trip_id)
        intent = compile_ready_intent(self.client, self.trip_id, self.base_revision_id, candidate["id"])
        with patch("app.trips.service.build_itinerary_response", return_value=command_itinerary()):
            preview = self.client.post(
                f"/trips/{self.trip_id}/planner-handoff/preview",
                json={"base_revision_id": self.base_revision_id, "intent_revision_id": intent["id"]},
                headers={"Origin": "http://testserver"},
            )
        self.assertEqual(preview.status_code, 200, preview.text)
        proposal = preview.json()["proposal"]
        repository = get_trip_repository()
        trip = repository.get_trip(self.trip_id)
        start = threading.Barrier(2)
        results = []
        failures = []

        def apply_from_connection(index: int) -> None:
            try:
                start.wait(timeout=5)
                result = repository.apply_mutation_proposal(
                    trip_id=self.trip_id,
                    capability_hash=trip.capability_hash,
                    proposal_id=proposal["id"],
                    base_revision_id=self.base_revision_id,
                    proposal_digest=proposal["proposal_digest"],
                    now=format_utc(datetime.now(timezone.utc)),
                    operation_summary="Concurrent planner handoff test.",
                    operation_metadata={"operation_type": "apply_planner_intent_handoff", "test": True},
                    request_digest=request_digest({"operation": "concurrent_handoff", "attempt": index}),
                    idempotency_key_hash=hash_idempotency_key(f"handoff-concurrent-{index}"),
                    expected_intent_revision_id=intent["id"],
                )
                results.append(result)
            except BaseException as error:  # pragma: no cover - asserted below
                failures.append(error)

        threads = [threading.Thread(target=apply_from_connection, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertFalse(failures, failures)
        self.assertEqual(len(results), 2)
        self.assertEqual(len({result.revision.id for result in results}), 1)
        self.assertEqual(len(repository.list_revisions(self.trip_id)), 2)
        run = repository.get_planner_handoff_run(trip_id=self.trip_id, run_id=proposal["planner_run_id"])
        self.assertEqual(run.status, "applied")
        self.assertEqual(run.applied_revision_id, results[0].revision.id)


def create_saved_trip(client: TestClient) -> tuple[str, str]:
    with patch("app.trips.service.build_itinerary_response", return_value=simple_itinerary()):
        response = client.post(
            "/trips/plan",
            json={"itinerary_request": {"city": "上海", "trip_days": 1, "scenic_spots": [], "restaurants": []}},
        )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["trip"]["id"], body["current_revision"]["id"]


def register_verified_candidate(client: TestClient, trip_id: str) -> dict:
    response = client.post(
        f"/trips/{trip_id}/candidates",
        json={
            "candidate_type": "place",
            "display_name": "外滩",
            "canonical_place_id": "amap:bund",
            "coordinates": {"latitude": 31.2401, "longitude": 121.4903},
            "estimated_duration_minutes": 90,
            "source_kind": "manual_entry",
        },
        headers={"Origin": "http://testserver", "X-Idempotency-Key": "handoff-verified-candidate"},
    )
    assert response.status_code == 201, response.text
    return response.json()["candidate"]


def compile_ready_intent(client: TestClient, trip_id: str, base_revision_id: str, candidate_id: str) -> dict:
    response = client.post(
        f"/trips/{trip_id}/intent-envelope/compile",
        json={
            "base_revision_id": base_revision_id,
            "base_intent_revision_id": None,
            "structured_overrides": {"city": "上海", "trip_days": 2, "must_candidate_ids": [candidate_id], "pace": "relaxed"},
        },
        headers={"Origin": "http://testserver", "X-Idempotency-Key": f"handoff-compile-{candidate_id}"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["envelope"]["formal_contract"]["readiness"]["status"] in {"ready_for_planning", "ready_with_assumptions"}
    return body["revision"]

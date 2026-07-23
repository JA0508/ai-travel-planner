from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.persistence.database import SQLiteConnectionFactory
from app.persistence.sqlite_trip_repository import SQLiteTripRepository
from app.persistence.memory_trip_repository import MemoryTripRepository
from app.trips.draft_intent_edits import DraftClarificationResolveRequest, DraftIntentEditRequest
from app.trips.dependencies import get_trip_repository, reset_trip_repository_cache_for_tests
from app.trips.errors import StaleDraftRevisionError, StaleIntentRevisionError
from app.trips.service import TripPersistenceService
from app.trips.intent_contracts import CompileTripIntentRequest


class DraftIntentEditingApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            "os.environ",
            {
                "TRIP_STORE_MODE": "sqlite",
                "TRIP_STORE_PATH": str(Path(self.temp_dir.name) / "draft-intent-edits.sqlite3"),
                "TRIP_ALLOWED_ORIGINS": "http://testserver",
                "CORS_ALLOW_ORIGINS": "http://testserver",
            },
        )
        self.env.start()
        reset_trip_repository_cache_for_tests()
        self.client = TestClient(app)
        self.trip_id, self.intent_id, self.draft_version = create_compiled_draft(self.client)

    def tearDown(self) -> None:
        reset_trip_repository_cache_for_tests()
        self.env.stop()
        self.temp_dir.cleanup()

    def test_typed_edit_creates_child_revision_without_planning_or_parser(self) -> None:
        repository = get_trip_repository()
        old = repository.get_draft_intent_revision(trip_id=self.trip_id, revision_id=self.intent_id)
        with patch("app.trips.service.build_untrusted_llm_intent_proposal", side_effect=AssertionError("LLM must not run")), patch(
            "app.trips.service.build_itinerary_response", side_effect=AssertionError("planner must not run")
        ):
            response = self.edit(
                "days-three",
                {"base_intent_revision_id": self.intent_id, "base_draft_version": self.draft_version, "operations": [{"operation": "update_trip_days", "trip_days": 3}]},
            )
        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertTrue(body["changed"])
        self.assertEqual(body["previous_intent_revision_id"], self.intent_id)
        self.assertEqual(body["draft_version"], self.draft_version + 1)
        self.assertEqual(body["envelope"]["formal_contract"]["date_policy"]["trip_days"], 3)
        self.assertEqual(repository.get_draft_intent_revision(trip_id=self.trip_id, revision_id=self.intent_id).envelope, old.envelope)
        self.assertEqual(repository.get_trip(self.trip_id).revision_count, 0)
        self.assertIsNone(repository.get_trip(self.trip_id).current_revision_id)

    def test_destination_date_policy_and_pace_are_compiled_as_user_edits(self) -> None:
        response = self.edit("destination-date-pace", {
            "base_intent_revision_id": self.intent_id,
            "base_draft_version": self.draft_version,
            "operations": [
                {"operation": "update_destination", "city": "上海", "timezone": "Asia/Shanghai"},
                {"operation": "update_date_policy", "start_date": "2026-10-01", "end_date": "2026-10-03", "timezone": "Asia/Shanghai"},
                {"operation": "update_pace", "pace": "balanced"},
            ],
        })
        self.assertEqual(response.status_code, 201, response.text)
        formal = response.json()["envelope"]["formal_contract"]
        self.assertEqual(formal["destinations"][0]["city_name"], "上海")
        self.assertEqual(formal["date_policy"]["start_date"], "2026-10-01")
        self.assertEqual(formal["date_policy"]["trip_days"], 3)
        self.assertEqual(formal["pace"]["value"], "balanced")
        selected = [field for field in response.json()["envelope"]["fields"] if field["status"] == "selected"]
        self.assertTrue(any(field["field_path"] == "trip.city" and field["confirmed_by_user"] for field in selected))

    def test_noop_replay_and_stale_protection_are_distinct(self) -> None:
        same_payload = {"base_intent_revision_id": self.intent_id, "base_draft_version": self.draft_version, "operations": [{"operation": "update_trip_days", "trip_days": 2}]}
        no_op = self.edit("days-noop", same_payload)
        self.assertEqual(no_op.status_code, 201, no_op.text)
        self.assertFalse(no_op.json()["changed"])
        self.assertEqual(no_op.json()["latest_intent_revision_id"], self.intent_id)
        replay = self.edit("days-noop", same_payload)
        self.assertEqual(replay.status_code, 201, replay.text)
        self.assertTrue(replay.json()["idempotent_replay"])
        self.assertFalse(replay.json()["changed"])

        advanced = self.edit("pace-change", {"base_intent_revision_id": self.intent_id, "base_draft_version": self.draft_version, "operations": [{"operation": "update_pace", "pace": "balanced"}]})
        self.assertEqual(advanced.status_code, 201, advanced.text)
        replay_after_advance = self.edit("days-noop", same_payload)
        self.assertEqual(replay_after_advance.status_code, 201, replay_after_advance.text)
        self.assertTrue(replay_after_advance.json()["idempotent_replay"])
        conflict = self.edit("days-noop", {"base_intent_revision_id": self.intent_id, "base_draft_version": self.draft_version, "operations": [{"operation": "update_trip_days", "trip_days": 4}]})
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(conflict.json()["error"]["code"], "idempotency_conflict")
        stale = self.edit("stale-edit", {"base_intent_revision_id": self.intent_id, "base_draft_version": self.draft_version, "operations": [{"operation": "update_pace", "pace": "intensive"}]})
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertIn(stale.json()["error"]["code"], {"stale_draft_revision", "stale_intent_revision"})

    def test_fixed_event_operations_are_stable_and_atomic(self) -> None:
        added = self.edit("event-add", {"base_intent_revision_id": self.intent_id, "base_draft_version": self.draft_version, "operations": [{"operation": "add_fixed_event", "event": {"title": "博物馆预约", "fixed_day": 2, "location_text": "人民广场"}}]})
        self.assertEqual(added.status_code, 201, added.text)
        event = added.json()["envelope"]["formal_contract"]["fixed_events"][0]
        self.assertTrue(event["event_id"].startswith("draft_fixed_event_"))
        updated = self.edit("event-update", {"base_intent_revision_id": added.json()["latest_intent_revision_id"], "base_draft_version": added.json()["draft_version"], "operations": [{"operation": "update_fixed_event", "fixed_event_id": event["event_id"], "event": {"title": "博物馆预约", "fixed_day": 1, "location_text": "人民广场"}}]})
        self.assertEqual(updated.status_code, 201, updated.text)
        self.assertEqual(updated.json()["envelope"]["formal_contract"]["fixed_events"][0]["fixed_day"], 1)
        removed = self.edit("event-remove", {"base_intent_revision_id": updated.json()["latest_intent_revision_id"], "base_draft_version": updated.json()["draft_version"], "operations": [{"operation": "remove_fixed_event", "fixed_event_id": event["event_id"]}]})
        self.assertEqual(removed.status_code, 201, removed.text)
        self.assertEqual(removed.json()["envelope"]["formal_contract"]["fixed_events"], [])
        before_invalid = removed.json()["latest_intent_revision_id"]
        invalid = self.edit("event-invalid", {"base_intent_revision_id": before_invalid, "base_draft_version": removed.json()["draft_version"], "operations": [{"operation": "add_fixed_event", "event": {"title": "超出范围", "fixed_day": 3}}]})
        self.assertEqual(invalid.status_code, 422, invalid.text)
        self.assertEqual(invalid.json()["error"]["code"], "fixed_event_outside_trip")
        self.assertEqual(get_trip_repository().get_latest_draft_intent_revision(trip_id=self.trip_id).id, before_invalid)

    def test_place_policy_move_preserves_candidate_identity(self) -> None:
        candidate = self.client.post(
            f"/trips/{self.trip_id}/candidates",
            json={"candidate_type": "place", "display_name": "灵隐寺", "source_kind": "manual_entry"},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-place-candidate"},
        )
        self.assertEqual(candidate.status_code, 201, candidate.text)
        candidate_id = candidate.json()["candidate"]["id"]
        added = self.edit("place-must", {"base_intent_revision_id": self.intent_id, "base_draft_version": self.draft_version, "operations": [{"operation": "add_must_place", "candidate_id": candidate_id}]})
        self.assertEqual(added.status_code, 201, added.text)
        self.assertEqual(added.json()["envelope"]["formal_contract"]["must_visit_places"][0]["trip_candidate_id"], candidate_id)
        moved = self.edit("place-move", {"base_intent_revision_id": added.json()["latest_intent_revision_id"], "base_draft_version": added.json()["draft_version"], "operations": [{"operation": "move_place_policy", "candidate_id": candidate_id, "from_policy": "must", "to_policy": "avoid"}]})
        self.assertEqual(moved.status_code, 201, moved.text)
        formal = moved.json()["envelope"]["formal_contract"]
        self.assertEqual(formal["must_visit_places"], [])
        self.assertEqual(formal["avoid_places"][0]["trip_candidate_id"], candidate_id)
        removed = self.edit("place-remove", {"base_intent_revision_id": moved.json()["latest_intent_revision_id"], "base_draft_version": moved.json()["draft_version"], "operations": [{"operation": "remove_place", "candidate_id": candidate_id, "policy": "avoid"}]})
        self.assertEqual(removed.status_code, 201, removed.text)
        self.assertEqual(removed.json()["envelope"]["formal_contract"]["avoid_places"], [])

    def test_sqlite_concurrent_edits_allow_one_append_only_child(self) -> None:
        factory = SQLiteConnectionFactory(Path(self.temp_dir.name) / "draft-intent-edits.sqlite3")
        factory.initialize()
        start = threading.Barrier(2)
        successes: list[object] = []
        stale: list[BaseException] = []

        def edit_from_separate_connection(index: int) -> None:
            service = TripPersistenceService(SQLiteTripRepository(factory.connect))
            payload = DraftIntentEditRequest(
                base_intent_revision_id=self.intent_id,
                base_draft_version=self.draft_version,
                operations=[{"operation": "update_pace", "pace": "balanced" if index == 0 else "intensive"}],
            )
            try:
                start.wait(timeout=5)
                successes.append(service.edit_draft_intent(
                    trip_id=self.trip_id,
                    capability="draft-capability:draft-edit-create",
                    idempotency_key=f"concurrent-draft-edit-{index}",
                    payload=payload,
                ))
            except (StaleDraftRevisionError, StaleIntentRevisionError) as error:
                stale.append(error)

        threads = [threading.Thread(target=edit_from_separate_connection, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(stale), 1)
        revisions = get_trip_repository().list_draft_intent_revisions(trip_id=self.trip_id)
        self.assertEqual(len(revisions), 2)
        self.assertEqual(len({revision.revision_number for revision in revisions}), 2)
        self.assertEqual(revisions[0].parent_draft_intent_revision_id, self.intent_id)
        self.assertEqual(get_trip_repository().get_trip(self.trip_id).draft_version, self.draft_version + 1)

    def test_memory_repository_matches_revision_and_noop_behavior(self) -> None:
        repository = MemoryTripRepository()
        service = TripPersistenceService(repository)
        created = service.create_draft_trip(direct_user_text="去杭州玩两天", idempotency_key="memory-draft")
        trip_id = created.response.trip.id
        compiled = service.compile_draft_intent_envelope(
            trip_id=trip_id,
            capability=created.capability,
            idempotency_key="memory-compile",
            payload=CompileTripIntentRequest(base_intent_revision_id=None, structured_overrides={"city": "杭州", "trip_days": 2}),
        )
        version = repository.get_trip(trip_id).draft_version
        changed = service.edit_draft_intent(
            trip_id=trip_id,
            capability=created.capability,
            idempotency_key="memory-edit",
            payload=DraftIntentEditRequest(base_intent_revision_id=compiled.revision.id, base_draft_version=version, operations=[{"operation": "update_pace", "pace": "balanced"}]),
        )
        self.assertTrue(changed.changed)
        self.assertEqual(changed.draft_version, version + 1)
        no_op = service.edit_draft_intent(
            trip_id=trip_id,
            capability=created.capability,
            idempotency_key="memory-noop",
            payload=DraftIntentEditRequest(base_intent_revision_id=changed.latest_intent_revision_id, base_draft_version=changed.draft_version, operations=[{"operation": "update_pace", "pace": "balanced"}]),
        )
        self.assertFalse(no_op.changed)
        self.assertEqual(len(repository.list_draft_intent_revisions(trip_id=trip_id)), 2)

    def test_typed_destination_clarification_reuses_draft_revision_transaction(self) -> None:
        created = self.client.post(
            "/trips/drafts",
            json={"direct_user_text": "周末玩两天，轻松一点。"},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "clarification-create"},
        )
        self.assertEqual(created.status_code, 201, created.text)
        trip_id = created.json()["trip"]["id"]
        compiled = self.client.post(
            f"/trips/{trip_id}/preplan-intent/compile",
            json={"base_intent_revision_id": None, "direct_user_text": "周末玩两天，轻松一点。", "use_llm_proposal_adapter": False},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "clarification-compile"},
        )
        self.assertEqual(compiled.status_code, 201, compiled.text)
        original_id = compiled.json()["revision"]["id"]
        question = next(item for item in compiled.json()["envelope"]["clarification_queue"] if item["reason_code"] in {"missing_destination", "destination_missing"})
        latest = self.client.get(f"/trips/{trip_id}/preplan-intent")
        self.assertEqual(latest.status_code, 200, latest.text)
        payload = {
            "base_intent_revision_id": original_id,
            "base_draft_version": latest.json()["trip"]["draft_version"],
            "answer": {"answer_type": "destination", "city": "杭州"},
        }
        with patch("app.trips.service.build_untrusted_llm_intent_proposal", side_effect=AssertionError("LLM must not run")), patch(
            "app.trips.service.build_itinerary_response", side_effect=AssertionError("planner must not run")
        ):
            resolved = self.client.post(
                f"/trips/{trip_id}/preplan-intent/clarifications/{question['question_id']}/resolve",
                json=payload,
                headers={"Origin": "http://testserver", "X-Idempotency-Key": "clarification-destination"},
            )
        self.assertEqual(resolved.status_code, 201, resolved.text)
        body = resolved.json()
        self.assertEqual(body["envelope"]["formal_contract"]["destinations"][0]["city_name"], "杭州")
        self.assertEqual(body["revision"]["parent_draft_intent_revision_id"], original_id)
        self.assertEqual(body["envelope"]["validation_report"]["clarification_resolution"]["question_id"], question["question_id"])
        self.assertFalse(any(item["question_id"] == question["question_id"] for item in body["envelope"]["clarification_queue"]))
        self.assertEqual(get_trip_repository().get_trip(trip_id).revision_count, 0)

        replay = self.client.post(
            f"/trips/{trip_id}/preplan-intent/clarifications/{question['question_id']}/resolve",
            json=payload,
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "clarification-destination"},
        )
        self.assertEqual(replay.status_code, 201, replay.text)
        self.assertTrue(replay.json()["idempotent_replay"])
        duplicate = self.client.post(
            f"/trips/{trip_id}/preplan-intent/clarifications/{question['question_id']}/resolve",
            json=payload,
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "clarification-destination-new-key"},
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        self.assertEqual(duplicate.json()["error"]["code"], "clarification_already_resolved")

    def test_clarification_schema_rejects_untyped_answer_and_stale_base(self) -> None:
        latest = self.client.get(f"/trips/{self.trip_id}/preplan-intent")
        self.assertEqual(latest.status_code, 200, latest.text)
        invalid = self.client.post(
            f"/trips/{self.trip_id}/preplan-intent/clarifications/unknown/resolve",
            json={"base_intent_revision_id": self.intent_id, "base_draft_version": latest.json()["trip"]["draft_version"], "answer": {"answer": "杭州"}},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "clarification-invalid"},
        )
        self.assertEqual(invalid.status_code, 422, invalid.text)

    def test_typed_clarification_answers_have_no_free_form_payload(self) -> None:
        base = {"base_intent_revision_id": "intent_1", "base_draft_version": 2}
        for answer in [
            {"answer_type": "destination", "city": "杭州"},
            {"answer_type": "trip_days", "trip_days": 3},
            {"answer_type": "date_range", "start_date": "2026-10-01", "end_date": "2026-10-03"},
            {"answer_type": "date_policy_choice", "policy": "trip_days", "trip_days": 3},
            {"answer_type": "date_policy_choice", "policy": "date_range", "start_date": "2026-10-01", "end_date": "2026-10-03"},
        ]:
            DraftClarificationResolveRequest.model_validate({**base, "answer": answer})
        with self.assertRaises(Exception):
            DraftClarificationResolveRequest.model_validate({**base, "answer": {"answer": "杭州"}})

    def edit(self, key: str, payload: dict) -> object:
        return self.client.post(
            f"/trips/{self.trip_id}/preplan-intent/edits",
            json=payload,
            headers={"Origin": "http://testserver", "X-Idempotency-Key": key},
        )


def create_compiled_draft(client: TestClient) -> tuple[str, str, int]:
    created = client.post("/trips/drafts", json={"direct_user_text": "周末去杭州玩两天，轻松一点。"}, headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-edit-create"})
    assert created.status_code == 201, created.text
    trip_id = created.json()["trip"]["id"]
    compiled = client.post(
        f"/trips/{trip_id}/preplan-intent/compile",
        json={"base_intent_revision_id": None, "structured_overrides": {"city": "杭州", "trip_days": 2, "pace": "relaxed"}},
        headers={"Origin": "http://testserver", "X-Idempotency-Key": "draft-edit-compile"},
    )
    assert compiled.status_code == 201, compiled.text
    draft = client.get(f"/trips/{trip_id}/draft")
    assert draft.status_code == 200, draft.text
    return trip_id, compiled.json()["revision"]["id"], draft.json()["trip"]["draft_version"]

from __future__ import annotations

import concurrent.futures
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.imports.dependencies import reset_import_dependencies_for_tests
from app.main import app
from app.schemas.intent import ParsedTripIntentResponse
from app.trips.dependencies import get_trip_repository, reset_trip_repository_cache_for_tests
from app.trips.errors import StaleIntentRevisionError
from app.trips.intent_contracts import TripIntentRevisionRecord
from tests.test_trip_persistence_api import simple_itinerary


class TripIntentContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store_path = Path(self.temp_dir.name) / "intent-contract.sqlite3"
        self.env = patch.dict(
            "os.environ",
            {
                "TRIP_STORE_MODE": "sqlite",
                "TRIP_STORE_PATH": str(self.store_path),
                "TRIP_ALLOWED_ORIGINS": "http://testserver",
                "CORS_ALLOW_ORIGINS": "http://testserver",
                "IMPORT_ARTIFACT_STORE_MODE": "memory",
                "IMPORT_TEXT_MAX_BYTES": "102400",
            },
        )
        self.env.start()
        reset_trip_repository_cache_for_tests()
        reset_import_dependencies_for_tests()

    def tearDown(self) -> None:
        reset_trip_repository_cache_for_tests()
        reset_import_dependencies_for_tests()
        self.env.stop()
        self.temp_dir.cleanup()

    def test_compile_intent_links_reviewed_candidate_user_text_and_llm_conflict(self) -> None:
        client, trip_id, base_revision_id = create_saved_trip()
        candidate = create_reviewed_candidate(client, trip_id, "景点：豫园")

        response = client.post(
            f"/trips/{trip_id}/intent-envelope/compile",
            json={
                "base_revision_id": base_revision_id,
                "direct_user_text": "城市：上海\n天数：2\n偏好：不要太赶",
                "candidate_ids": [candidate["id"]],
                "llm_proposal": {
                    "city": "北京",
                    "trip_days": 3,
                    "pace": "intensive",
                    "must_candidate_ids": [candidate["id"]],
                    "explanation": "The old LLM proposal preferred Beijing.",
                },
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "compile-one"},
        )

        self.assertEqual(response.status_code, 201, response.text)
        envelope = response.json()["envelope"]
        selected_city = selected_field(envelope, "trip.city")
        selected_days = selected_field(envelope, "trip.trip_days")
        selected_pace = selected_field(envelope, "trip.pace")
        selected_candidate = selected_field(envelope, "poi.must_candidates")
        self.assertEqual(selected_city["value"], {"type": "destination_city", "city": "上海"})
        self.assertEqual(selected_city["semantic_type"], "destination_city")
        self.assertEqual(selected_city["semantic_value"], {"type": "destination_city", "city": "上海"})
        self.assertEqual(selected_city["kind"], "hard")
        self.assertTrue(selected_city["confirmed_by_user"])
        self.assertEqual(selected_city["source_refs"][0]["source_type"], "direct_user_language")
        self.assertEqual(selected_city["source_refs"][0]["authority"], "user_confirmed")
        self.assertEqual(selected_days["value"], {"type": "trip_days", "days": 2})
        self.assertEqual(selected_pace["value"], {"type": "pace", "pace": "relaxed"})
        self.assertEqual(selected_pace["kind"], "soft")
        self.assertEqual(selected_candidate["value"]["candidate_id"], candidate["id"])
        self.assertEqual(selected_candidate["value"]["display_name"], candidate["display_name"])
        self.assertEqual(selected_candidate["semantic_type"], "must_candidate")
        self.assertEqual(selected_candidate["source_refs"][0]["source_type"], "trip_candidate")
        self.assertEqual(selected_candidate["source_refs"][0]["authority"], "reviewed_source")
        self.assertEqual(selected_candidate["source_refs"][0]["source_id"], candidate["id"])
        self.assertTrue(
            set(candidate["evidence_refs"]).issubset(
                set(selected_candidate["source_refs"][0]["evidence_refs"])
            )
        )
        self.assertTrue(selected_candidate["confirmed_by_user"])
        self.assertIn(
            "schema_validated",
            selected_candidate["validation_codes"],
        )
        self.assertTrue(any(field["status"] == "shadowed" and field["value"].get("city") == "北京" for field in envelope["fields"]))
        self.assertTrue(any(conflict["reason_code"] == "higher_priority_source_selected" for conflict in envelope["conflicts"]))
        self.assertEqual(envelope["planner_ready_intent"]["city"], "上海")
        self.assertEqual(envelope["planner_ready_intent"]["trip_days"], 2)
        self.assertIn(candidate["id"], envelope["planner_ready_intent"]["must_place_candidate_ids"])
        self.assertEqual(envelope["planner_ready_intent"]["pace"], "relaxed")
        self.assertEqual(envelope["typed_intent"]["destinations"][0]["value"]["city"], "上海")
        self.assertEqual(envelope["typed_intent"]["date_policy"]["trip_days"]["value"]["days"], 2)
        self.assertEqual(envelope["typed_intent"]["poi_preferences"]["must_candidates"][0]["value"]["candidate_id"], candidate["id"])
        self.assertTrue(
            any(
                item["field_path"] == "trip.city"
                and "direct_user_language" in item["source_types"]
                and "llm_proposal" in item["source_types"]
                for item in envelope["provenance_summary"]
            )
        )
        self.assertTrue(envelope["validation_report"]["llm_proposal_validated"])
        self.assertEqual(envelope["parser_result"]["status"], "validated")
        self.assertTrue(envelope["semantic_digest"])
        self.assertTrue(envelope["lineage_digest"])
        self.assertNotEqual(envelope["semantic_digest"], envelope["lineage_digest"])
        self.assertGreater(envelope["validation_report"]["provenance_graph_node_count"], 0)
        node_types = {node["node_type"] for node in envelope["provenance_graph"]["nodes"]}
        self.assertIn("trip_candidate", node_types)
        self.assertIn("source_artifact", node_types)
        self.assertIn("extracted_mention", node_types)
        self.assertTrue(
            any(
                edge["relation"] == "supports"
                for edge in envelope["provenance_graph"]["edges"]
            )
        )
        self.assertIn("destinations", envelope["validation_report"]["typed_intent_sections"])
        self.assertIn("poi_preferences", envelope["validation_report"]["typed_intent_sections"])
        self.assertFalse(envelope["validation_report"]["manual_override_priority_enforced"])

    def test_structured_override_wins_over_llm_proposal_and_records_priority(self) -> None:
        client, trip_id, base_revision_id = create_saved_trip()

        response = client.post(
            f"/trips/{trip_id}/intent-envelope/compile",
            json={
                "base_revision_id": base_revision_id,
                "structured_overrides": {"city": "杭州", "trip_days": 2},
                "llm_proposal": {
                    "city": "上海",
                    "trip_days": 4,
                    "explanation": "The older LLM explanation should not override manual state.",
                },
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "manual-wins"},
        )

        self.assertEqual(response.status_code, 201, response.text)
        envelope = response.json()["envelope"]
        city = selected_field(envelope, "trip.city")
        self.assertEqual(city["value"], {"type": "destination_city", "city": "杭州"})
        self.assertEqual(city["source_refs"][0]["source_type"], "structured_user_override")
        self.assertTrue(city["confirmed_by_user"])
        self.assertEqual(envelope["planner_ready_intent"]["city"], "杭州")
        self.assertTrue(envelope["validation_report"]["manual_override_priority_enforced"])
        self.assertTrue(
            any(
                conflict["field_path"] == "trip.city"
                and conflict["reason_code"] == "higher_priority_source_selected"
                for conflict in envelope["conflicts"]
            )
        )

    def test_missing_destination_creates_blocking_clarification_queue(self) -> None:
        client, trip_id, base_revision_id = create_saved_trip()

        response = client.post(
            f"/trips/{trip_id}/intent-envelope/compile",
            json={
                "base_revision_id": base_revision_id,
                "direct_user_text": "偏好：不要太赶",
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "clarify-city"},
        )

        self.assertEqual(response.status_code, 201, response.text)
        envelope = response.json()["envelope"]
        self.assertEqual(envelope["planner_ready_status"], "needs_clarification")
        self.assertEqual(envelope["planner_ready_intent"]["city"], None)
        self.assertEqual(envelope["clarification_queue"][0]["question_id"], "clarify_trip_city")
        self.assertTrue(envelope["clarification_queue"][0]["blocking"])
        self.assertEqual(envelope["clarification_queue"][0]["answer_field_path"], "trip.city")
        self.assertFalse(envelope["validation_report"]["planner_ready"])

    def test_missing_trip_days_blocks_planner_ready_with_unvalued_typed_assumption(self) -> None:
        client, trip_id, base_revision_id = create_saved_trip()

        response = client.post(
            f"/trips/{trip_id}/intent-envelope/compile",
            json={
                "base_revision_id": base_revision_id,
                "structured_overrides": {"city": "上海"},
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "nonblocking-days"},
        )

        self.assertEqual(response.status_code, 201, response.text)
        envelope = response.json()["envelope"]
        self.assertEqual(envelope["planner_ready_status"], "needs_clarification")
        question = next(item for item in envelope["clarification_queue"] if item["question_id"] == "clarify_trip_days")
        self.assertTrue(question["blocking"])
        self.assertEqual(question["impact"], "planner_blocking")
        self.assertEqual(question["answer_field_path"], "trip.trip_days")
        self.assertEqual(question["answer_value_type"], "integer")
        assumption = next(item for item in envelope["typed_assumptions"] if item["field_path"] == "trip.trip_days")
        self.assertFalse(assumption["has_assumed_value"])
        self.assertTrue(assumption["blocks_planner_ready"])
        self.assertIn("missing_trip_length", envelope["readiness_policy"]["blocking_reason_codes"])
        self.assertFalse(envelope["validation_report"]["planner_ready"])

    def test_intent_revision_is_idempotent_and_does_not_mutate_trip_revision(self) -> None:
        client, trip_id, base_revision_id = create_saved_trip()
        payload = {
            "base_revision_id": base_revision_id,
            "structured_overrides": {"city": "上海", "trip_days": 2},
        }

        first = client.post(
            f"/trips/{trip_id}/intent-envelope/compile",
            json=payload,
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "same-intent"},
        )
        replay = client.post(
            f"/trips/{trip_id}/intent-envelope/compile",
            json=payload,
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "same-intent"},
        )
        revisions = client.get(f"/trips/{trip_id}/intent-envelope")
        trip_revisions = client.get(f"/trips/{trip_id}/revisions")

        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(replay.status_code, 201, replay.text)
        self.assertEqual(first.json()["revision"]["id"], replay.json()["revision"]["id"])
        self.assertTrue(replay.json()["idempotent_replay"])
        self.assertEqual(len(revisions.json()["revisions"]), 1)
        self.assertEqual(len(trip_revisions.json()["revisions"]), 1)

    def test_semantic_digest_is_stable_across_equivalent_revisions(self) -> None:
        client, trip_id, base_revision_id = create_saved_trip()
        payload = {
            "base_revision_id": base_revision_id,
            "structured_overrides": {
                "city": "上海",
                "trip_days": 2,
                "pace": "relaxed",
                "transport_preferences": ["地铁", "步行"],
            },
        }

        first = client.post(
            f"/trips/{trip_id}/intent-envelope/compile",
            json=payload,
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "semantic-one"},
        )
        second = client.post(
            f"/trips/{trip_id}/intent-envelope/compile",
            json=payload,
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "semantic-two"},
        )

        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertNotEqual(first.json()["revision"]["id"], second.json()["revision"]["id"])
        self.assertEqual(second.json()["revision"]["parent_intent_revision_id"], first.json()["revision"]["id"])
        self.assertEqual(first.json()["envelope"]["semantic_digest"], second.json()["envelope"]["semantic_digest"])
        self.assertNotEqual(first.json()["envelope"]["lineage_digest"], second.json()["envelope"]["lineage_digest"])
        self.assertNotEqual(first.json()["envelope"]["content_digest"], second.json()["envelope"]["content_digest"])

    def test_stale_base_revision_is_rejected_before_intent_revision_is_created(self) -> None:
        client, trip_id, base_revision_id = create_saved_trip()

        response = client.post(
            f"/trips/{trip_id}/intent-envelope/compile",
            json={
                "base_revision_id": f"{base_revision_id}-old",
                "structured_overrides": {"city": "上海"},
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "stale-intent"},
        )
        revisions = client.get(f"/trips/{trip_id}/intent-envelope")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "stale_base_revision")
        self.assertEqual(revisions.json()["revisions"], [])

    def test_compile_rejects_stale_base_intent_revision_id(self) -> None:
        client, trip_id, base_revision_id = create_saved_trip()
        initial = client.post(
            f"/trips/{trip_id}/intent-envelope/compile",
            json={"base_revision_id": base_revision_id, "structured_overrides": {"city": "上海", "trip_days": 2}},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "base-intent-initial"},
        )
        self.assertEqual(initial.status_code, 201, initial.text)

        stale = client.post(
            f"/trips/{trip_id}/intent-envelope/compile",
            json={
                "base_revision_id": base_revision_id,
                "base_intent_revision_id": "intent_old",
                "structured_overrides": {"city": "杭州", "trip_days": 2},
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "base-intent-stale"},
        )

        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.json()["error"]["code"], "stale_intent_revision")

    def test_detail_edit_and_clarification_create_intent_revision_lineage(self) -> None:
        client, trip_id, base_revision_id = create_saved_trip()
        initial = client.post(
            f"/trips/{trip_id}/intent-envelope/compile",
            json={"base_revision_id": base_revision_id, "direct_user_text": "偏好：不要太赶"},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "lineage-initial"},
        )
        initial_revision_id = initial.json()["revision"]["id"]

        clarified = client.post(
            f"/trips/{trip_id}/intent-envelope/{initial_revision_id}/clarifications/clarify_trip_city/answer",
            json={"base_revision_id": base_revision_id, "answer": "上海"},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "lineage-city-answer"},
        )
        edited = client.post(
            f"/trips/{trip_id}/intent-envelope/{clarified.json()['revision']['id']}/edit",
            json={"base_revision_id": base_revision_id, "field_updates": {"trip_days": 3}},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "lineage-days-edit"},
        )
        detail = client.get(f"/trips/{trip_id}/intent-envelope/{edited.json()['revision']['id']}")
        history = client.get(f"/trips/{trip_id}/intent-envelope")

        self.assertEqual(clarified.status_code, 201, clarified.text)
        self.assertEqual(edited.status_code, 201, edited.text)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(clarified.json()["revision"]["parent_intent_revision_id"], initial_revision_id)
        self.assertEqual(edited.json()["revision"]["parent_intent_revision_id"], clarified.json()["revision"]["id"])
        self.assertEqual(selected_field(edited.json()["envelope"], "trip.city")["value"]["city"], "上海")
        self.assertEqual(selected_field(edited.json()["envelope"], "trip.trip_days")["value"]["days"], 3)
        self.assertEqual([item["revision_number"] for item in history.json()["revisions"]], [3, 2, 1])

    def test_restore_intent_revision_appends_new_revision_without_trip_revision_mutation(self) -> None:
        client, trip_id, base_revision_id = create_saved_trip()
        initial = client.post(
            f"/trips/{trip_id}/intent-envelope/compile",
            json={"base_revision_id": base_revision_id, "structured_overrides": {"city": "上海", "trip_days": 2}},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "restore-initial"},
        )
        edited = client.post(
            f"/trips/{trip_id}/intent-envelope/{initial.json()['revision']['id']}/edit",
            json={"base_revision_id": base_revision_id, "field_updates": {"city": "杭州", "trip_days": 3}},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "restore-edit"},
        )

        restored = client.post(
            f"/trips/{trip_id}/intent-envelope/{initial.json()['revision']['id']}/restore",
            json={"base_revision_id": base_revision_id},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "restore-old"},
        )
        history = client.get(f"/trips/{trip_id}/intent-envelope")
        trip_revisions = client.get(f"/trips/{trip_id}/revisions")

        self.assertEqual(edited.status_code, 201, edited.text)
        self.assertEqual(restored.status_code, 201, restored.text)
        self.assertEqual(restored.json()["revision"]["parent_intent_revision_id"], edited.json()["revision"]["id"])
        self.assertEqual(selected_field(restored.json()["envelope"], "trip.city")["value"]["city"], "上海")
        self.assertEqual(restored.json()["envelope"]["validation_report"]["restored_from_intent_revision_id"], initial.json()["revision"]["id"])
        self.assertEqual([item["revision_number"] for item in history.json()["revisions"]], [3, 2, 1])
        self.assertEqual(len(trip_revisions.json()["revisions"]), 1)

    def test_generic_clarification_answer_resolves_trip_days(self) -> None:
        client, trip_id, base_revision_id = create_saved_trip()
        initial = client.post(
            f"/trips/{trip_id}/intent-envelope/compile",
            json={"base_revision_id": base_revision_id, "structured_overrides": {"city": "上海"}},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "generic-days-initial"},
        )

        answered = client.post(
            f"/trips/{trip_id}/intent-envelope/{initial.json()['revision']['id']}/clarifications/clarify_trip_days/answer",
            json={"base_revision_id": base_revision_id, "answer": 4},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "generic-days-answer"},
        )

        self.assertEqual(answered.status_code, 201, answered.text)
        envelope = answered.json()["envelope"]
        self.assertEqual(selected_field(envelope, "trip.trip_days")["value"]["days"], 4)
        self.assertEqual(envelope["typed_intent"]["date_policy"]["trip_days"]["value"]["days"], 4)
        self.assertEqual(envelope["revision_number"], 2)
        self.assertEqual(envelope["parent_intent_revision_id"], initial.json()["revision"]["id"])

    def test_stale_intent_edit_is_rejected_but_idempotent_retry_replays(self) -> None:
        client, trip_id, base_revision_id = create_saved_trip()
        initial = client.post(
            f"/trips/{trip_id}/intent-envelope/compile",
            json={"base_revision_id": base_revision_id, "structured_overrides": {"city": "上海"}},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "stale-intent-initial"},
        )
        initial_revision_id = initial.json()["revision"]["id"]
        edit_payload = {"base_revision_id": base_revision_id, "field_updates": {"trip_days": 2}}
        first_edit = client.post(
            f"/trips/{trip_id}/intent-envelope/{initial_revision_id}/edit",
            json=edit_payload,
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "stale-intent-edit"},
        )
        replay = client.post(
            f"/trips/{trip_id}/intent-envelope/{initial_revision_id}/edit",
            json=edit_payload,
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "stale-intent-edit"},
        )
        stale_edit = client.post(
            f"/trips/{trip_id}/intent-envelope/{initial_revision_id}/edit",
            json={"base_revision_id": base_revision_id, "field_updates": {"pace": "relaxed"}},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "stale-intent-edit-new"},
        )

        self.assertEqual(first_edit.status_code, 201, first_edit.text)
        self.assertEqual(replay.status_code, 201, replay.text)
        self.assertTrue(replay.json()["idempotent_replay"])
        self.assertEqual(first_edit.json()["revision"]["id"], replay.json()["revision"]["id"])
        self.assertEqual(stale_edit.status_code, 409)
        self.assertEqual(stale_edit.json()["error"]["code"], "stale_intent_revision")

    def test_concurrent_intent_edits_cannot_create_sibling_revisions(self) -> None:
        client, trip_id, base_revision_id = create_saved_trip()
        initial = client.post(
            f"/trips/{trip_id}/intent-envelope/compile",
            json={"base_revision_id": base_revision_id, "structured_overrides": {"city": "上海", "trip_days": 2}},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "concurrent-initial"},
        )
        self.assertEqual(initial.status_code, 201, initial.text)
        parent_id = initial.json()["revision"]["id"]

        def edit_city(city: tuple[str, str]) -> tuple[int, dict]:
            city_name, key_suffix = city
            response = client.post(
                f"/trips/{trip_id}/intent-envelope/{parent_id}/edit",
                json={"base_revision_id": base_revision_id, "field_updates": {"city": city_name, "trip_days": 2}},
                headers={"Origin": "http://testserver", "X-Idempotency-Key": f"concurrent-edit-{key_suffix}"},
            )
            return response.status_code, response.json()

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(edit_city, [("杭州", "hz"), ("苏州", "sz")]))

        status_codes = sorted(status for status, _body in results)
        history = client.get(f"/trips/{trip_id}/intent-envelope")
        self.assertEqual(status_codes, [201, 409])
        self.assertEqual([item["revision_number"] for item in history.json()["revisions"]], [2, 1])

    def test_repository_compare_and_append_rejects_stale_parent_inside_transaction(self) -> None:
        client, trip_id, base_revision_id = create_saved_trip()
        initial = client.post(
            f"/trips/{trip_id}/intent-envelope/compile",
            json={"base_revision_id": base_revision_id, "structured_overrides": {"city": "上海", "trip_days": 2}},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "atomic-initial"},
        )
        edited = client.post(
            f"/trips/{trip_id}/intent-envelope/{initial.json()['revision']['id']}/edit",
            json={"base_revision_id": base_revision_id, "field_updates": {"city": "杭州", "trip_days": 2}},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "atomic-edit"},
        )
        repository = get_trip_repository()
        stale_envelope = dict(initial.json()["envelope"])
        stale_envelope["id"] = "intent_stale_direct_insert"
        stale_envelope["revision_number"] = 2
        stale_envelope["parent_intent_revision_id"] = initial.json()["revision"]["id"]
        stale_record = TripIntentRevisionRecord(
            id=stale_envelope["id"],
            trip_id=trip_id,
            revision_number=2,
            parent_intent_revision_id=initial.json()["revision"]["id"],
            base_trip_revision_id=base_revision_id,
            envelope_schema_version=stale_envelope["schema_version"],
            envelope=stale_envelope,
            content_digest=stale_envelope["content_digest"],
            compiler_version=stale_envelope["compiler_version"],
            source_digest=stale_envelope["source_digest"],
            validation_report=stale_envelope["validation_report"],
            created_at=stale_envelope["created_at"],
        )

        self.assertEqual(edited.status_code, 201, edited.text)
        with self.assertRaises(StaleIntentRevisionError):
            repository.create_intent_revision(
                revision=stale_record,
                request_digest="atomic-stale-request",
                idempotency_key_hash="atomic-stale-key",
                expected_parent_intent_revision_id=initial.json()["revision"]["id"],
                require_latest_parent=True,
            )

    def test_fixed_event_outside_trip_days_blocks_planner_ready(self) -> None:
        client, trip_id, base_revision_id = create_saved_trip()

        response = client.post(
            f"/trips/{trip_id}/intent-envelope/compile",
            json={
                "base_revision_id": base_revision_id,
                "structured_overrides": {
                    "city": "上海",
                    "trip_days": 1,
                    "fixed_events": [
                        {
                            "name": "第二天博物馆预约",
                            "fixed_day": 2,
                            "fixed_time_start": "14:00",
                            "fixed_time_end": "15:00",
                        }
                    ],
                },
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "fixed-outside"},
        )

        self.assertEqual(response.status_code, 201, response.text)
        envelope = response.json()["envelope"]
        self.assertEqual(envelope["planner_ready_status"], "blocked")
        self.assertTrue(
            any(
                conflict["reason_code"] == "fixed_event_outside_trip_dates"
                and conflict["severity"] == "blocking"
                for conflict in envelope["conflicts"]
            )
        )
        self.assertFalse(envelope["validation_report"]["planner_ready"])

    def test_llm_adapter_proposal_is_untrusted_and_loses_to_manual_override(self) -> None:
        client, trip_id, base_revision_id = create_saved_trip()
        with patch(
            "app.trips.intent_llm_adapter.parse_trip_text_with_llm",
            return_value=ParsedTripIntentResponse(city="北京", trip_days=5),
        ):
            response = client.post(
                f"/trips/{trip_id}/intent-envelope/compile",
                json={
                    "base_revision_id": base_revision_id,
                    "direct_user_text": "城市：上海\n天数：2",
                    "structured_overrides": {"city": "上海"},
                    "use_llm_proposal_adapter": True,
                },
                headers={"Origin": "http://testserver", "X-Idempotency-Key": "llm-adapter"},
            )

        self.assertEqual(response.status_code, 201, response.text)
        envelope = response.json()["envelope"]
        self.assertTrue(envelope["validation_report"]["llm_proposal_validated"])
        self.assertEqual(selected_field(envelope, "trip.city")["value"]["city"], "上海")
        self.assertTrue(
            any(field["status"] == "shadowed" and field["source_refs"][0]["source_type"] == "llm_proposal" for field in envelope["fields"])
        )

    def test_llm_adapter_timeout_is_recorded_without_trusting_parser_output(self) -> None:
        client, trip_id, base_revision_id = create_saved_trip()
        with patch(
            "app.trips.service.build_untrusted_llm_intent_proposal",
            side_effect=TimeoutError(),
        ):
            response = client.post(
                f"/trips/{trip_id}/intent-envelope/compile",
                json={
                    "base_revision_id": base_revision_id,
                    "direct_user_text": "城市：上海\n天数：2",
                    "use_llm_proposal_adapter": True,
                },
                headers={"Origin": "http://testserver", "X-Idempotency-Key": "llm-adapter-timeout"},
            )

        self.assertEqual(response.status_code, 201, response.text)
        envelope = response.json()["envelope"]
        self.assertEqual(envelope["parser_result"]["status"], "timeout")
        self.assertIn("llm_adapter_timeout", envelope["parser_result"]["warnings"])
        self.assertFalse(envelope["validation_report"]["llm_proposal_validated"])

    def test_sqlite_intent_revisions_are_immutable(self) -> None:
        client, trip_id, base_revision_id = create_saved_trip()
        created = client.post(
            f"/trips/{trip_id}/intent-envelope/compile",
            json={
                "base_revision_id": base_revision_id,
                "structured_overrides": {"city": "上海", "trip_days": 2},
            },
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "immutable-intent"},
        )
        revision_id = created.json()["revision"]["id"]

        connection = sqlite3.connect(str(self.store_path), isolation_level=None)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE trip_intent_revisions SET compiler_version = ? WHERE id = ?",
                    ("mutated", revision_id),
                )
        finally:
            connection.close()


def create_saved_trip() -> tuple[TestClient, str, str]:
    client = TestClient(app)
    with patch("app.trips.service.build_itinerary_response", return_value=simple_itinerary()):
        response = client.post(
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
    assert response.status_code == 201, response.text
    body = response.json()
    return client, body["trip"]["id"], body["current_revision"]["id"]


def create_reviewed_candidate(client: TestClient, trip_id: str, text: str) -> dict:
    imported = client.post(
        f"/trips/{trip_id}/imports/text",
        json={"text": text, "original_label": "intent contract source"},
        headers={"Origin": "http://testserver", "X-Idempotency-Key": "intent-import"},
    )
    assert imported.status_code == 201, imported.text
    body = imported.json()
    review_version = body["job"]["review_version"]
    for index, mention in enumerate([item for item in body["mentions"] if item["entity_type"] == "place"]):
        decision = client.post(
            f"/trips/{trip_id}/imports/{body['job']['id']}/mentions/{mention['id']}/decisions",
            json={
                "base_review_version": review_version,
                "action": "confirm",
                "selected_resolution_candidate_id": mention["selected_resolution_candidate_id"],
            },
            headers={
                "Origin": "http://testserver",
                "X-Idempotency-Key": f"confirm-intent-{index}-{mention['id']}",
            },
        )
        assert decision.status_code == 200, decision.text
        review_version = decision.json()["job"]["review_version"]
    committed = client.post(
        f"/trips/{trip_id}/imports/{body['job']['id']}/commit",
        json={"base_review_version": review_version},
        headers={"Origin": "http://testserver", "X-Idempotency-Key": f"commit-{body['job']['id']}"},
    )
    assert committed.status_code == 200, committed.text
    candidates = client.get(f"/trips/{trip_id}/candidates").json()["candidates"]
    assert candidates, "Expected reviewed import to create at least one TripCandidate"
    return candidates[0]


def selected_field(envelope: dict, field_path: str) -> dict:
    for field in envelope["fields"]:
        if field["field_path"] == field_path and field["status"] == "selected":
            return field
    raise AssertionError(f"No selected field for {field_path}")

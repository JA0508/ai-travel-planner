from __future__ import annotations

import tempfile
import unittest
import json
from contextlib import redirect_stdout
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from pathlib import Path
from sqlite3 import connect
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.plan_candidate_store import reset_plan_candidate_store_for_tests
from app.services.planning_run_dependencies import get_planning_run_repository
from app.services.trip_compiler import compile_travel_intent
from app.trips.access import generate_capability, hash_capability, hash_idempotency_key
from app.trips.dependencies import get_trip_repository, reset_trip_repository_cache_for_tests
from app.services.constraint_planning import canonical_digest, generate_candidates, intent_digest
from app.services.planning_run_replay import replay_planning_run
from app.tools.verify_planning_run import main as verify_planning_run_main


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

    def revision_count(self) -> int:
        get_trip_repository()
        with connect(self.database_path) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM trip_revisions").fetchone()[0])

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

    def test_same_idempotency_key_cannot_select_a_different_candidate(self) -> None:
        generated = self.candidates().json()
        self.assertGreaterEqual(len(generated["candidates"]), 2)
        first, second = generated["candidates"][:2]
        headers = {"Origin": "http://testserver", "X-Idempotency-Key": "selection-payload-boundary"}
        selected = self.client.post(
            f"/trip-compiler/planning-runs/{generated['planning_run_id']}/candidates/{first['id']}/select",
            json={"candidate_hash": first["candidate_hash"], "intent_digest": generated["intent_digest"]}, headers=headers,
        )
        self.assertEqual(selected.status_code, 201, selected.text)
        mismatch = self.client.post(
            f"/trip-compiler/planning-runs/{generated['planning_run_id']}/candidates/{second['id']}/select",
            json={"candidate_hash": second["candidate_hash"], "intent_digest": generated["intent_digest"]}, headers=headers,
        )
        self.assertEqual(mismatch.status_code, 409, mismatch.text)
        self.assertEqual(mismatch.json()["error"]["code"], "idempotency_payload_mismatch")
        self.assertEqual(self.trip_count(), 1)
        self.assertEqual(self.revision_count(), 1)

    def test_response_loss_retry_reissues_trip_cookie_without_creating_another_revision(self) -> None:
        generated = self.candidates().json()
        candidate = generated["candidates"][0]
        planning_capability = self.client.cookies.get("planning_run_capability")
        headers = {"Origin": "http://testserver", "X-Idempotency-Key": "response-loss-recovery"}
        original = self.client.post(
            f"/trip-compiler/planning-runs/{generated['planning_run_id']}/candidates/{candidate['id']}/select",
            json={"candidate_hash": candidate["candidate_hash"], "intent_digest": generated["intent_digest"]},
            headers=headers,
        )
        self.assertEqual(original.status_code, 201, original.text)
        trip_id = original.json()["trip"]["id"]
        # Model a response that committed but never reached the browser: retain
        # only the independent Planning Run cookie for a new client.
        recovered_client = TestClient(app)
        recovered_client.cookies.set("planning_run_capability", str(planning_capability))
        recovered = recovered_client.post(
            f"/trip-compiler/planning-runs/{generated['planning_run_id']}/candidates/{candidate['id']}/select",
            json={"candidate_hash": candidate["candidate_hash"], "intent_digest": generated["intent_digest"]},
            headers=headers,
        )
        self.assertEqual(recovered.status_code, 201, recovered.text)
        self.assertTrue(recovered.json()["persistence"]["idempotent_replay"])
        self.assertEqual(recovered.json()["trip"]["id"], trip_id)
        self.assertEqual(recovered.json()["current_revision"]["revision_number"], 1)
        self.assertIn("trip_capability_", recovered.headers["set-cookie"])
        self.assertEqual(recovered_client.get(f"/trips/{trip_id}").status_code, 200)
        self.assertEqual(self.trip_count(), 1)
        self.assertEqual(self.revision_count(), 1)

    def test_transaction_failure_points_roll_back_trip_and_keep_run_retryable(self) -> None:
        generated = self.candidates().json()
        candidate = generated["candidates"][0]
        run_capability = self.client.cookies.get("planning_run_capability")
        self.assertIsNotNone(run_capability)
        request_digest = canonical_digest({"candidate_id": candidate["id"], "candidate_hash": candidate["candidate_hash"], "intent_digest": generated["intent_digest"]})

        for failure_point in (
            "after_selection_reserved",
            "after_trip_inserted",
            "after_revision_inserted",
            "before_planning_run_selected",
        ):
            with self.subTest(failure_point=failure_point):
                def fail_at(point: str) -> None:
                    if point == failure_point:
                        raise RuntimeError(f"injected {failure_point}")

                with self.assertRaisesRegex(RuntimeError, "injected"):
                    get_planning_run_repository().select_candidate_atomically(
                        trip_repository=get_trip_repository(),
                        run_id=generated["planning_run_id"],
                        candidate_id=candidate["id"],
                        candidate_hash=candidate["candidate_hash"],
                        intent_digest=generated["intent_digest"],
                        planning_capability_hash=hash_capability(str(run_capability)),
                        trip_capability_hash=hash_capability(generate_capability()),
                        idempotency_key_hash=hash_idempotency_key(f"injected-{failure_point}"),
                        request_digest=request_digest,
                        failure_hook=fail_at,
                    )
                self.assertEqual(self.trip_count(), 0)
                self.assertEqual(self.revision_count(), 0)
                restored = self.client.get(f"/trip-compiler/planning-runs/{generated['planning_run_id']}")
                self.assertEqual(restored.status_code, 200, restored.text)
                self.assertEqual(restored.json()["status"], "generated")

    def test_initial_revision_records_candidate_lineage_metadata(self) -> None:
        generated = self.candidates().json()
        candidate = generated["candidates"][0]
        selected = self.client.post(
            f"/trip-compiler/planning-runs/{generated['planning_run_id']}/candidates/{candidate['id']}/select",
            json={"candidate_hash": candidate["candidate_hash"], "intent_digest": generated["intent_digest"]},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "lineage-metadata"},
        )
        self.assertEqual(selected.status_code, 201, selected.text)
        with connect(self.database_path) as connection:
            row = connection.execute("SELECT operation_metadata_json FROM revision_operations WHERE trip_id = ?", (selected.json()["trip"]["id"],)).fetchone()
        metadata = json.loads(row[0])
        self.assertEqual(metadata["root_planning_run_id"], generated["planning_run_id"])
        self.assertEqual(metadata["selected_candidate_id"], candidate["id"])
        self.assertEqual(metadata["selected_candidate_hash"], candidate["candidate_hash"])
        self.assertIn("constraint_graph_digest", metadata)
        self.assertIn("poi_snapshot_digest", metadata)
        self.assertIn("route_snapshot_digest", metadata)
        self.assertEqual(metadata["planner_policy_version"], "trip-compiler-candidates-v1")
        self.assertEqual(metadata["source"], "candidate_selection")

    def test_controlled_edit_preserves_root_planning_run_lineage(self) -> None:
        generated = self.candidates().json()
        candidate = generated["candidates"][0]
        selected = self.client.post(
            f"/trip-compiler/planning-runs/{generated['planning_run_id']}/candidates/{candidate['id']}/select",
            json={"candidate_hash": candidate["candidate_hash"], "intent_digest": generated["intent_digest"]},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "lineage-repair-selection"},
        )
        self.assertEqual(selected.status_code, 201, selected.text)
        selected_body = selected.json()
        base_revision_id = selected_body["current_revision"]["id"]
        first_item = next(
            item
            for day in selected_body["itinerary"]["days"]
            for block in day["blocks"]
            for item in block["items"]
        )
        preview = self.client.post(
            f"/trips/{selected_body['trip']['id']}/mutations/preview",
            json={
                "base_revision_id": base_revision_id,
                "mutation_kind": "route_edit",
                "commands": [{"type": "remove_stop", "stop_id": first_item["stable_id"]}],
            },
            headers={"Origin": "http://testserver"},
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        proposal = preview.json()["proposal"]
        applied = self.client.post(
            f"/trips/{selected_body['trip']['id']}/mutation-proposals/{proposal['id']}/apply",
            json={"base_revision_id": base_revision_id, "proposal_digest": proposal["proposal_digest"]},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "lineage-repair-apply"},
        )
        self.assertEqual(applied.status_code, 200, applied.text)
        revision = applied.json()["current_revision"]
        self.assertEqual(revision["revision_number"], 2)
        self.assertEqual(revision["planner_run_id"], generated["planning_run_id"])
        with connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT operation_metadata_json FROM revision_operations WHERE revision_id = ?",
                (revision["id"],),
            ).fetchone()
        self.assertEqual(json.loads(row[0])["root_planning_run_id"], generated["planning_run_id"])

    def test_concurrent_different_candidates_create_one_trip_and_one_revision(self) -> None:
        generated = self.candidates().json()
        first, second = generated["candidates"][:2]
        planning_cookie = self.client.cookies.get("planning_run_capability")

        def select(candidate: dict, key: str) -> tuple[int, dict]:
            with TestClient(app) as client:
                response = client.post(
                    f"/trip-compiler/planning-runs/{generated['planning_run_id']}/candidates/{candidate['id']}/select",
                    json={"candidate_hash": candidate["candidate_hash"], "intent_digest": generated["intent_digest"]},
                    headers={"Origin": "http://testserver", "X-Idempotency-Key": key, "Cookie": f"planning_run_capability={planning_cookie}"},
                )
                return response.status_code, response.json()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda input: select(*input), [(first, "parallel-a"), (second, "parallel-b")]))
        self.assertEqual(sorted(status for status, _ in results), [201, 409])
        self.assertEqual(self.trip_count(), 1)
        self.assertEqual(self.revision_count(), 1)

    def test_concurrent_same_candidate_same_key_replays_one_trip(self) -> None:
        generated = self.candidates().json()
        candidate = generated["candidates"][0]
        planning_cookie = self.client.cookies.get("planning_run_capability")

        def select() -> tuple[int, dict]:
            with TestClient(app) as client:
                response = client.post(
                    f"/trip-compiler/planning-runs/{generated['planning_run_id']}/candidates/{candidate['id']}/select",
                    json={"candidate_hash": candidate["candidate_hash"], "intent_digest": generated["intent_digest"]},
                    headers={"Origin": "http://testserver", "X-Idempotency-Key": "parallel-same", "Cookie": f"planning_run_capability={planning_cookie}"},
                )
                return response.status_code, response.json()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: select(), range(2)))
        self.assertEqual([status for status, _ in results].count(201), 2)
        self.assertEqual(len({body["trip"]["id"] for _, body in results}), 1)
        self.assertEqual(self.trip_count(), 1)
        self.assertEqual(self.revision_count(), 1)

    def test_concurrent_same_candidate_different_keys_creates_one_trip(self) -> None:
        generated = self.candidates().json()
        candidate = generated["candidates"][0]
        planning_cookie = self.client.cookies.get("planning_run_capability")

        def select(key: str) -> int:
            with TestClient(app) as client:
                return client.post(
                    f"/trip-compiler/planning-runs/{generated['planning_run_id']}/candidates/{candidate['id']}/select",
                    json={"candidate_hash": candidate["candidate_hash"], "intent_digest": generated["intent_digest"]},
                    headers={"Origin": "http://testserver", "X-Idempotency-Key": key, "Cookie": f"planning_run_capability={planning_cookie}"},
                ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(select, ["parallel-key-a", "parallel-key-b"]))
        self.assertEqual(sorted(statuses), [201, 409])
        self.assertEqual(self.trip_count(), 1)
        self.assertEqual(self.revision_count(), 1)

    def test_frozen_decision_record_verification_checks_manifest_without_creating_trip(self) -> None:
        generated = self.candidates().json()
        before_trips, before_revisions = self.trip_count(), self.revision_count()
        result = replay_planning_run(get_planning_run_repository(), generated["planning_run_id"])
        self.assertEqual(result.status, "verified")
        self.assertEqual(result.expected_candidate_set_hash, result.actual_candidate_set_hash)
        self.assertEqual(self.trip_count(), before_trips)
        self.assertEqual(self.revision_count(), before_revisions)
        with connect(self.database_path) as connection:
            manifest = connection.execute("SELECT snapshot_manifest_json FROM planning_runs WHERE id = ?", (generated["planning_run_id"],)).fetchone()[0]
        self.assertIn("poi_snapshot_digest", manifest)
        self.assertIn("route_snapshot_digest", manifest)

    def test_frozen_decision_record_verification_reports_tampered_candidate_without_overwriting_it(self) -> None:
        generated = self.candidates().json()
        candidate_id = generated["candidates"][0]["id"]
        with connect(self.database_path) as connection:
            connection.execute("DROP TRIGGER planning_run_candidates_immutable")
            connection.execute(
                "UPDATE planning_run_candidates SET metrics_json = ? WHERE planning_run_id = ? AND candidate_id = ?",
                ('{"fixed_coverage":999}', generated["planning_run_id"], candidate_id),
            )
            connection.commit()
        result = replay_planning_run(get_planning_run_repository(), generated["planning_run_id"])
        self.assertEqual(result.status, "mismatch")
        self.assertTrue(any(item.kind == "candidate_metrics" and item.candidate_id == candidate_id for item in result.differences))
        with connect(self.database_path) as connection:
            stored = connection.execute("SELECT metrics_json FROM planning_run_candidates WHERE planning_run_id = ? AND candidate_id = ?", (generated["planning_run_id"], candidate_id)).fetchone()[0]
        self.assertEqual(stored, '{"fixed_coverage":999}')

    def test_frozen_decision_record_verification_rejects_unsupported_policy_without_writes(self) -> None:
        generated = self.candidates().json()
        with connect(self.database_path) as connection:
            connection.execute("DROP TRIGGER planning_runs_immutable_snapshot")
            connection.execute("UPDATE planning_runs SET planner_policy_version = 'retired-policy' WHERE id = ?", (generated["planning_run_id"],))
            connection.commit()
        result = replay_planning_run(get_planning_run_repository(), generated["planning_run_id"])
        self.assertEqual(result.status, "unsupported_policy_version")
        self.assertEqual(self.trip_count(), 0)

    def test_frozen_decision_record_cli_reports_verified_snapshot_without_exposing_capability(self) -> None:
        generated = self.candidates().json()
        output = StringIO()
        with redirect_stdout(output):
            exit_code = verify_planning_run_main([generated["planning_run_id"]])
        self.assertEqual(exit_code, 0)
        rendered = output.getvalue()
        self.assertIn("Result: VERIFIED", rendered)
        self.assertNotIn(str(self.client.cookies.get("planning_run_capability")), rendered)

    def test_source_fragment_display_order_does_not_change_intent_or_candidate_hashes(self) -> None:
        intent = compile_travel_intent(HANGZHOU).intent
        reordered = intent.model_copy(update={"source_fragments": list(reversed(intent.source_fragments))})
        self.assertEqual(intent_digest(intent), intent_digest(reordered))
        _, first_cores, first_candidates, _ = generate_candidates(intent)
        _, second_cores, second_candidates, _ = generate_candidates(reordered)
        self.assertFalse(first_cores)
        self.assertFalse(second_cores)
        self.assertEqual(
            [(candidate.id, candidate.candidate_hash) for candidate in first_candidates],
            [(candidate.id, candidate.candidate_hash) for candidate in second_candidates],
        )


if __name__ == "__main__":
    unittest.main()

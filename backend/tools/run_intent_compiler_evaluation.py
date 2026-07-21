from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.imports.dependencies import reset_import_dependencies_for_tests
from app.main import app
from app.trips.dependencies import reset_trip_repository_cache_for_tests
from tests.test_trip_persistence_api import simple_itinerary


@dataclass(frozen=True, slots=True)
class IntentCompilerFixture:
    name: str
    payload: dict
    expected_status: str
    expected_conflict: str | None = None
    expected_clarification: str | None = None
    expected_typed_section: str | None = None
    expected_provenance_field: str | None = None
    expected_semantic_type: str | None = None
    expected_blocking_reason: str | None = None
    expected_graph_node_type: str | None = None
    expected_domain_value_type: str | None = None


MIN_FIXTURE_COUNT = 15


FIXTURES = [
    IntentCompilerFixture(
        name="direct_user_text_ready",
        payload={"direct_user_text": "城市：上海\n天数：2\n偏好：不要太赶"},
        expected_status="ready",
        expected_typed_section="destinations",
        expected_provenance_field="trip.city",
        expected_domain_value_type="destination_city",
    ),
    IntentCompilerFixture(
        name="manual_override_beats_llm",
        payload={
            "structured_overrides": {"city": "杭州", "trip_days": 2},
            "llm_proposal": {"city": "上海", "trip_days": 4},
        },
        expected_status="ready",
        expected_conflict="higher_priority_source_selected",
        expected_typed_section="date_policy",
        expected_domain_value_type="destination_city",
    ),
    IntentCompilerFixture(
        name="missing_destination_clarification",
        payload={"direct_user_text": "偏好：不要太赶"},
        expected_status="needs_clarification",
        expected_clarification="clarify_trip_city",
    ),
    IntentCompilerFixture(
        name="missing_trip_days_requires_clarification",
        payload={"structured_overrides": {"city": "上海"}},
        expected_status="needs_clarification",
        expected_clarification="clarify_trip_days",
        expected_typed_section="unresolved_questions",
        expected_blocking_reason="missing_trip_length",
    ),
    IntentCompilerFixture(
        name="fixed_event_outside_trip_dates",
        payload={
            "structured_overrides": {
                "city": "上海",
                "trip_days": 1,
                "fixed_events": [{"name": "第二天预约", "fixed_day": 2}],
            }
        },
        expected_status="blocked",
        expected_conflict="fixed_event_outside_trip_dates",
        expected_typed_section="fixed_events",
        expected_domain_value_type="fixed_event",
    ),
    IntentCompilerFixture(
        name="llm_proposal_only_is_assumption_weighted",
        payload={"llm_proposal": {"city": "上海", "trip_days": 2}},
        expected_status="ready",
        expected_typed_section="destinations",
        expected_semantic_type="destination_city",
        expected_domain_value_type="destination_city",
    ),
    IntentCompilerFixture(
        name="transport_preference_is_typed_soft_field",
        payload={"structured_overrides": {"city": "上海", "trip_days": 2, "transport_preferences": ["地铁", "步行"]}},
        expected_status="ready",
        expected_typed_section="transport_preferences",
        expected_provenance_field="preferences.transport",
        expected_semantic_type="transport_preference",
        expected_domain_value_type="transport_preference",
    ),
    IntentCompilerFixture(
        name="manual_pace_is_semantic_soft_field",
        payload={"structured_overrides": {"city": "上海", "trip_days": 2, "pace": "balanced"}},
        expected_status="ready",
        expected_typed_section="pace",
        expected_semantic_type="pace",
        expected_domain_value_type="pace",
    ),
    IntentCompilerFixture(
        name="reviewed_candidate_absence_is_allowed_typed_assumption",
        payload={"structured_overrides": {"city": "上海", "trip_days": 2}},
        expected_status="ready",
        expected_blocking_reason=None,
    ),
    IntentCompilerFixture(
        name="direct_user_text_parser_result_is_recorded",
        payload={"direct_user_text": "城市：杭州\n天数：3\n偏好：轻松"},
        expected_status="ready",
        expected_typed_section="destinations",
        expected_provenance_field="trip.city",
        expected_semantic_type="destination_city",
        expected_domain_value_type="destination_city",
    ),
    IntentCompilerFixture(
        name="manual_budget_is_domain_native_soft_value",
        payload={"structured_overrides": {"city": "上海", "trip_days": 2, "budget": {"budget_level": "medium", "currency": "CNY"}}},
        expected_status="ready",
        expected_typed_section="budget",
        expected_semantic_type="budget",
        expected_domain_value_type="budget",
    ),
    IntentCompilerFixture(
        name="traveler_need_is_typed_hard_value",
        payload={"structured_overrides": {"city": "上海", "trip_days": 2, "traveler_needs": ["轮椅可达"]}},
        expected_status="ready",
        expected_typed_section="travelers",
        expected_semantic_type="traveler_need",
        expected_domain_value_type="traveler_need",
    ),
    IntentCompilerFixture(
        name="llm_parser_error_status_is_explicit",
        payload={
            "direct_user_text": "城市：上海\n天数：2",
            "use_llm_proposal_adapter": True,
            "parser_error_status": "timeout",
            "parser_error_code": "llm_adapter_timeout",
        },
        expected_status="ready",
        expected_provenance_field="trip.city",
        expected_domain_value_type="destination_city",
    ),
    IntentCompilerFixture(
        name="fixed_event_same_day_is_planner_ready",
        payload={
            "structured_overrides": {
                "city": "上海",
                "trip_days": 2,
                "fixed_events": [{"name": "博物馆预约", "fixed_day": 2, "fixed_time_start": "14:00"}],
            }
        },
        expected_status="ready",
        expected_typed_section="fixed_events",
        expected_semantic_type="fixed_event",
        expected_domain_value_type="fixed_event",
    ),
    IntentCompilerFixture(
        name="manual_transport_deduplicates_into_single_domain_values",
        payload={"structured_overrides": {"city": "上海", "trip_days": 2, "transport_preferences": ["地铁", "地铁", "步行"]}},
        expected_status="ready",
        expected_typed_section="transport_preferences",
        expected_semantic_type="transport_preference",
        expected_domain_value_type="transport_preference",
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    results = run_evaluation()
    if len(results) < MIN_FIXTURE_COUNT:
        results.append(
            {
                "name": "fixture_count_gate",
                "passed": False,
                "status": "blocked",
                "error": f"Intent evaluation requires at least {MIN_FIXTURE_COUNT} fixtures.",
            }
        )
    failed = [result for result in results if not result["passed"]]
    if args.json:
        print(json.dumps({"total": len(results), "failed": len(failed), "results": results}, ensure_ascii=False, indent=2))
    else:
        for result in results:
            marker = "PASS" if result["passed"] else "FAIL"
            print(f"{marker} {result['name']} status={result.get('status')} conflicts={result.get('conflicts')}")
        print(f"Intent compiler evaluation: {len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


def run_evaluation() -> list[dict]:
    results: list[dict] = []
    with tempfile.TemporaryDirectory() as temp_dir:
        env = patch.dict(
            "os.environ",
            {
                "TRIP_STORE_MODE": "sqlite",
                "TRIP_STORE_PATH": str(Path(temp_dir) / "intent-eval.sqlite3"),
                "TRIP_ALLOWED_ORIGINS": "http://testserver",
                "CORS_ALLOW_ORIGINS": "http://testserver",
                "IMPORT_ARTIFACT_STORE_MODE": "memory",
            },
        )
        env.start()
        try:
            reset_trip_repository_cache_for_tests()
            reset_import_dependencies_for_tests()
            client = TestClient(app)
            for index, fixture in enumerate(FIXTURES):
                trip_id, base_revision_id = create_trip(client)
                payload = {"base_revision_id": base_revision_id, **fixture.payload}
                response = client.post(
                    f"/trips/{trip_id}/intent-envelope/compile",
                    json=payload,
                    headers={"Origin": "http://testserver", "X-Idempotency-Key": f"intent-eval-{index}"},
                )
                passed, detail = evaluate_response(fixture, response)
                results.append({"name": fixture.name, "passed": passed, **detail})
        finally:
            reset_trip_repository_cache_for_tests()
            reset_import_dependencies_for_tests()
            env.stop()
    return results


def create_trip(client: TestClient) -> tuple[str, str]:
    with patch("app.trips.service.build_itinerary_response", return_value=simple_itinerary()):
        response = client.post(
            "/trips/plan",
            json={"itinerary_request": {"city": "上海", "trip_days": 1, "scenic_spots": [], "restaurants": []}},
        )
    response.raise_for_status()
    body = response.json()
    return body["trip"]["id"], body["current_revision"]["id"]


def evaluate_response(fixture: IntentCompilerFixture, response) -> tuple[bool, dict]:
    if response.status_code != 201:
        return False, {"status_code": response.status_code, "error": response.text}
    envelope = response.json()["envelope"]
    conflicts = [conflict["reason_code"] for conflict in envelope["conflicts"]]
    clarifications = [item["question_id"] for item in envelope["clarification_queue"]]
    passed = envelope["planner_ready_status"] == fixture.expected_status
    if fixture.expected_conflict:
        passed = passed and fixture.expected_conflict in conflicts
    if fixture.expected_clarification:
        passed = passed and fixture.expected_clarification in clarifications
    typed_sections = envelope["validation_report"].get("typed_intent_sections", [])
    provenance_fields = [item["field_path"] for item in envelope.get("provenance_summary", [])]
    semantic_types = [field["semantic_type"] for field in envelope["fields"]]
    domain_value_types = [field["value"].get("type") for field in envelope["fields"] if isinstance(field.get("value"), dict)]
    graph_node_types = [node["node_type"] for node in envelope.get("provenance_graph", {}).get("nodes", [])]
    blocking_reasons = envelope.get("readiness_policy", {}).get("blocking_reason_codes", [])
    if fixture.expected_typed_section:
        passed = passed and fixture.expected_typed_section in typed_sections
    if fixture.expected_provenance_field:
        passed = passed and fixture.expected_provenance_field in provenance_fields
    if fixture.expected_semantic_type:
        passed = passed and fixture.expected_semantic_type in semantic_types
    if fixture.expected_domain_value_type:
        passed = passed and fixture.expected_domain_value_type in domain_value_types
    if fixture.expected_graph_node_type:
        passed = passed and fixture.expected_graph_node_type in graph_node_types
    if fixture.expected_blocking_reason:
        passed = passed and fixture.expected_blocking_reason in blocking_reasons
    passed = passed and bool(envelope.get("semantic_digest"))
    passed = passed and bool(envelope.get("lineage_digest"))
    passed = passed and envelope.get("semantic_digest") != envelope.get("lineage_digest")
    passed = passed and envelope["validation_report"].get("provenance_graph_node_count", 0) > 0
    passed = passed and "typed_assumptions" in envelope
    passed = passed and "parser_result" in envelope
    return passed, {
        "status": envelope["planner_ready_status"],
        "conflicts": conflicts,
        "clarifications": clarifications,
        "typed_sections": typed_sections,
        "provenance_fields": provenance_fields,
        "semantic_types": semantic_types,
        "domain_value_types": domain_value_types,
        "graph_node_types": graph_node_types,
        "blocking_reasons": blocking_reasons,
        "semantic_digest": envelope.get("semantic_digest"),
        "provenance_graph_node_count": envelope["validation_report"].get("provenance_graph_node_count", 0),
        "field_count": len(envelope["fields"]),
    }


if __name__ == "__main__":
    raise SystemExit(main())

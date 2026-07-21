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


FIXTURES = [
    IntentCompilerFixture(
        name="direct_user_text_ready",
        payload={"direct_user_text": "城市：上海\n天数：2\n偏好：不要太赶"},
        expected_status="ready",
    ),
    IntentCompilerFixture(
        name="manual_override_beats_llm",
        payload={
            "structured_overrides": {"city": "杭州", "trip_days": 2},
            "llm_proposal": {"city": "上海", "trip_days": 4},
        },
        expected_status="ready",
        expected_conflict="higher_priority_source_selected",
    ),
    IntentCompilerFixture(
        name="missing_destination_clarification",
        payload={"direct_user_text": "偏好：不要太赶"},
        expected_status="needs_clarification",
        expected_clarification="clarify_trip_city",
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
    ),
    IntentCompilerFixture(
        name="llm_proposal_only_is_assumption_weighted",
        payload={"llm_proposal": {"city": "上海", "trip_days": 2}},
        expected_status="ready",
    ),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    results = run_evaluation()
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
    return passed, {
        "status": envelope["planner_ready_status"],
        "conflicts": conflicts,
        "clarifications": clarifications,
        "field_count": len(envelope["fields"]),
    }


if __name__ == "__main__":
    raise SystemExit(main())

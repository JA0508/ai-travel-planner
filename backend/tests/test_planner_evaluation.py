from __future__ import annotations

import copy
import json
import unittest

from app.evaluation.fixture_loader import load_cases
from app.evaluation.runner import (
    execute_case,
    handoff_review_gate_errors,
    run_case,
    run_handoff_review_evaluation,
    run_planner_evaluation,
)


class PlannerEvaluationTests(unittest.TestCase):
    def test_handoff_review_fixture_corpus_gates_lifecycle_boundaries(self) -> None:
        report = run_handoff_review_evaluation()

        self.assertEqual(report.fixture_count, 6)
        self.assertEqual(report.strict_fixture_count, 5)
        self.assertEqual(report.drift_fixture_count, 1)
        self.assertEqual(report.failed_count, 0)
        self.assertEqual(
            {result.status for result in report.results},
            {"apply_ready", "blocked", "stale", "unstable", "applied"},
        )
        self.assertTrue(all(result.deterministic_match for result in report.results))
        self.assertEqual(handoff_review_gate_errors(report), [])

    def test_handoff_review_gate_rejects_missing_boundary_coverage(self) -> None:
        report = run_handoff_review_evaluation()
        incomplete = report.model_copy(
            update={
                "results": report.results[:1],
                "strict_fixture_count": 1,
                "drift_fixture_count": 0,
            }
        )

        errors = handoff_review_gate_errors(incomplete)

        self.assertIn("requires_at_least_5_strict_fixtures", errors)
        self.assertIn("requires_at_least_1_drift_fixture", errors)
        self.assertIn("missing_handoff_statuses:applied,blocked,stale,unstable", errors)

    def test_evaluation_corpus_replays_deterministically(self) -> None:
        report = run_planner_evaluation()

        self.assertEqual(report.fixture_count, 10)
        self.assertEqual(report.failed_count, 0)
        self.assertEqual(report.deterministic_mismatch_count, 0)

    def test_trace_privacy_scan_excludes_fixture_secrets(self) -> None:
        case = load_cases()[0]
        executed = execute_case(case)
        trace_json = json.dumps(executed["trace"].model_dump(mode="json"), ensure_ascii=False)

        self.assertNotIn("OPENAI_API_KEY", trace_json)
        self.assertNotIn("AMAP_API_KEY", trace_json)
        self.assertNotIn("Authorization", trace_json)
        self.assertNotIn("confirmation_code", trace_json)
        self.assertNotIn("fixture-secret" + "@example.com", trace_json)

    def test_intentionally_broken_fixture_fails_invariants(self) -> None:
        case = copy.deepcopy(load_cases()[0])
        case["id"] = "broken_duplicate_place"
        duplicate = copy.deepcopy(case["request"]["scenic_spots"][0])
        case["request"]["scenic_spots"].append(duplicate)

        result = run_case(case)

        self.assertEqual(result.status, "fail")
        failed_codes = {
            invariant.code
            for invariant in result.invariant_results
            if invariant.status == "fail"
        }
        self.assertIn("NO_DUPLICATE_SCHEDULED_PLACE", failed_codes)


if __name__ == "__main__":
    unittest.main()

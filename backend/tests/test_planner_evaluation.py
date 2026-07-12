from __future__ import annotations

import copy
import json
import unittest

from app.evaluation.fixture_loader import load_cases
from app.evaluation.runner import execute_case, run_case, run_planner_evaluation


class PlannerEvaluationTests(unittest.TestCase):
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

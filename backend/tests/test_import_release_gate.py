from __future__ import annotations

import unittest

from tools import run_import_evaluation


class ImportReleaseGateTests(unittest.TestCase):
    def test_release_gate_covers_each_form_and_required_degradation(self) -> None:
        cases = {case.name: case for case in run_import_evaluation.RELEASE_GATE_CASES}

        self.assertEqual(
            {case.form for case in cases.values()},
            {"text", "url", "image", "pdf"},
        )
        self.assertEqual(cases["text_review_commit"].stage, "review_commit")
        self.assertEqual(cases["url_private_destination_rejected"].expected_reason_code, "import_url_destination_blocked")
        self.assertEqual(cases["image_ocr_unavailable"].expected_reason_code, "import_document_ocr_unavailable")
        self.assertEqual(cases["pdf_partial_page_retry"].expected_document_status, "partial")
        self.assertIn("STALE_REVIEW_REJECTED", cases["text_stale_review_rejected"].required_invariants)
        self.assertIn("IMPORT_COMMIT_IDEMPOTENT", cases["image_review_commit"].required_invariants)

    def test_release_gate_failure_identifies_form_stage_and_stable_reason_code(self) -> None:
        gate = run_import_evaluation.evaluate_release_gate(
            [{"fixture": "commit_confirmed_only", "passed_invariants": [], "failed_invariants": []}]
        )

        failed = next(result for result in gate if result["case"] == "text_review_commit")
        self.assertFalse(failed["passed"])
        self.assertEqual(failed["form"], "text")
        self.assertEqual(failed["stage"], "review_commit")
        self.assertEqual(failed["reason_code"], "release_gate_invariant_failed")
        self.assertIn("IMPORT_COMMIT_IDEMPOTENT", failed["missing_invariants"])

    def test_release_gate_rejects_unexpected_reason_code(self) -> None:
        gate = run_import_evaluation.evaluate_release_gate(
            [{
                "fixture": "url_loopback_ipv4",
                "passed_invariants": ["PRIVATE_DESTINATION_BLOCKED"],
                "failed_invariants": [],
                "error_code": "import_url_host_invalid",
            }]
        )

        failed = next(result for result in gate if result["case"] == "url_private_destination_rejected")
        self.assertFalse(failed["passed"])
        self.assertEqual(failed["form"], "url")
        self.assertEqual(failed["stage"], "url_policy")
        self.assertEqual(failed["reason_code"], "release_gate_reason_code_mismatch")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import argparse
import json
import sys

from app.evaluation.runner import (
    handoff_review_gate_errors,
    run_handoff_review_evaluation,
    run_planner_evaluation,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ci", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_planner_evaluation()
    handoff_report = run_handoff_review_evaluation()
    handoff_gate_errors = handoff_review_gate_errors(handoff_report) if args.ci else []
    report_json = {
        **report.model_dump(mode="json"),
        "handoff_review": handoff_report.model_dump(mode="json"),
        "handoff_gate_errors": handoff_gate_errors,
    }
    if args.json:
        print(json.dumps(report_json, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "Planner evaluation: "
            f"{report.passed_count}/{report.fixture_count} fixtures passed; "
            f"{report.deterministic_mismatch_count} deterministic mismatches."
        )
        for result in report.results:
            failed = [
                invariant.code
                for invariant in result.invariant_results
                if invariant.status == "fail"
            ]
            suffix = f" failed={','.join(failed)}" if failed else ""
            print(f"- {result.case_id}: {result.status}{suffix}")
        print(
            "Frozen handoff review evaluation: "
            f"{handoff_report.passed_count}/{handoff_report.fixture_count} fixtures passed; "
            f"{handoff_report.strict_fixture_count} strict, {handoff_report.drift_fixture_count} drift."
        )
        for result in handoff_report.results:
            marker = "PASS" if result.passed else "FAIL"
            print(f"- {marker} {result.case_id}: {result.status} coverage={result.coverage}")
        for error in handoff_gate_errors:
            print(f"- FAIL handoff CI gate: {error}")
        print(json.dumps(report_json, ensure_ascii=False, sort_keys=True))

    return 1 if report.failed_count or handoff_report.failed_count or handoff_gate_errors else 0


if __name__ == "__main__":
    sys.exit(main())

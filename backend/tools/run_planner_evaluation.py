from __future__ import annotations

import argparse
import json
import sys

from app.evaluation.runner import run_planner_evaluation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ci", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_planner_evaluation()
    report_json = report.model_dump(mode="json")
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
        print(json.dumps(report_json, ensure_ascii=False, sort_keys=True))

    return 1 if report.failed_count else 0


if __name__ == "__main__":
    sys.exit(main())

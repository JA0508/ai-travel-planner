from __future__ import annotations

import argparse

from app.services.planning_run_dependencies import get_planning_run_repository
from app.services.planning_run_replay import replay_planning_run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a persisted Planning Run without provider calls.")
    parser.add_argument("planning_run_id")
    args = parser.parse_args(argv)
    result = replay_planning_run(get_planning_run_repository(), args.planning_run_id)
    print(f"Planning Run: {result.planning_run_id}")
    print(f"Policy Version: {result.planner_policy_version or 'unavailable'}")
    print(f"Expected Candidate Set Hash: {result.expected_candidate_set_hash or 'unavailable'}")
    print(f"Actual Candidate Set Hash: {result.actual_candidate_set_hash or 'unavailable'}")
    if result.status == "verified":
        print("Result: VERIFIED")
        return 0
    if result.status == "mismatch":
        print("Result: MISMATCH")
        print("Differences:")
        for difference in result.differences:
            print(f"- {difference.kind}: {difference.candidate_id or 'planning_run'}")
        return 1
    print("Result: VERSION UNAVAILABLE" if result.status == "unsupported_policy_version" else "Result: INVALID")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

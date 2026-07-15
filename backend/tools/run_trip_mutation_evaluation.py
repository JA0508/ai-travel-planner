from __future__ import annotations

import argparse
import json
import sys
import unittest


TARGET_TESTS = [
    "tests.test_trip_persistence_api.TripPersistenceApiTests."
    "test_persisted_replan_creates_revision_with_idempotent_retry",
    "tests.test_trip_persistence_api.TripPersistenceApiTests."
    "test_replan_preview_is_non_persistent_and_apply_rejects_mismatched_proposal",
    "tests.test_trip_persistence_api.TripPersistenceApiTests."
    "test_replan_apply_rejects_expired_proposal_without_new_revision",
    "tests.test_trip_persistence_api.TripPersistenceApiTests."
    "test_persisted_replan_rejects_stale_base_and_undo_compensates",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ci", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    suite = unittest.defaultTestLoader.loadTestsFromNames(TARGET_TESTS)
    result = unittest.TextTestRunner(verbosity=2 if not args.ci else 1).run(suite)
    report = {
        "suite": "trip_mutation_evaluation",
        "test_count": result.testsRun,
        "failure_count": len(result.failures),
        "error_count": len(result.errors),
        "passed": result.wasSuccessful(),
        "covered_contracts": [
            "persisted_replan_preview_creates_immutable_proposal",
            "persisted_replan_apply_uses_stored_proposal_without_planner_reexecution",
            "proposal_digest_mismatch_is_rejected",
            "expired_proposal_is_rejected_without_revision",
            "current_only_replan_undo_creates_compensating_revision",
        ],
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())

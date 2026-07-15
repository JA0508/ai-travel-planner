from __future__ import annotations

import argparse
import json
import sys
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


TARGET_TESTS = [
    "tests.test_trip_persistence_api.TripPersistenceApiTests."
    "test_persisted_replan_creates_revision_with_idempotent_retry",
    "tests.test_trip_persistence_api.TripPersistenceApiTests."
    "test_replan_preview_is_non_persistent_and_apply_rejects_mismatched_proposal",
    "tests.test_trip_persistence_api.TripPersistenceApiTests."
    "test_replan_apply_rejects_expired_proposal_without_new_revision",
    "tests.test_trip_persistence_api.TripPersistenceApiTests."
    "test_persisted_replan_rejects_stale_base_and_undo_compensates",
    "tests.test_trip_persistence_api.TripPersistenceApiTests."
    "test_route_edit_typed_mutation_preview_apply_reload_and_undo",
    "tests.test_trip_persistence_api.TripPersistenceApiTests."
    "test_swap_typed_mutation_is_idempotent_and_preserves_stable_identity",
    "tests.test_trip_persistence_api.TripPersistenceApiTests."
    "test_typed_mutation_rejects_fixed_item_and_stale_base_without_revision",
    "tests.test_trip_persistence_api.TripPersistenceApiTests."
    "test_candidate_registration_persists_without_revision_and_deduplicates",
    "tests.test_trip_persistence_api.TripPersistenceApiTests."
    "test_candidate_reject_and_defer_are_workflow_decisions_without_revision",
    "tests.test_trip_persistence_api.TripPersistenceApiTests."
    "test_candidate_decision_idempotent_retry_returns_same_decision_without_revision",
    "tests.test_trip_persistence_api.TripPersistenceApiTests."
    "test_rejected_candidate_admission_is_rejected_without_revision",
    "tests.test_trip_persistence_api.TripPersistenceApiTests."
    "test_cross_trip_candidate_admission_is_rejected_without_revision",
    "tests.test_trip_persistence_api.TripPersistenceApiTests."
    "test_valid_candidate_admission_creates_revision_and_scheduled_decision",
    "tests.test_trip_persistence_api.TripPersistenceApiTests."
    "test_missing_location_candidate_admission_returns_repair_required_without_revision",
    "tests.test_trip_persistence_api.TripPersistenceApiTests."
    "test_completion_undo_creates_compensating_revision",
    "tests.test_trip_mutation_commands.TripMutationCommandTests."
    "test_stable_ids_are_added_deterministically_to_legacy_snapshots",
    "tests.test_trip_mutation_commands.TripMutationCommandTests."
    "test_move_stop_preview_preserves_identity_and_invalidates_derived_surfaces",
    "tests.test_trip_mutation_commands.TripMutationCommandTests."
    "test_reorder_day_preview_keeps_same_stop_set",
    "tests.test_trip_mutation_commands.TripMutationCommandTests."
    "test_remove_fixed_stop_is_rejected",
    "tests.test_trip_mutation_commands.TripMutationCommandTests."
    "test_swap_preview_exchanges_slots_without_reassigning_stable_ids",
    "tests.test_trip_mutation_commands.TripMutationCommandTests."
    "test_replace_stop_preview_preserves_slot_identity_for_completion_swap",
    "tests.test_trip_mutation_commands.TripMutationCommandTests."
    "test_no_effect_command_is_rejected_before_persistence",
    "tests.test_trip_mutation_commands.TripMutationCommandTests."
    "test_invalid_target_id_is_rejected_without_mutating_base_snapshot",
    "tests.test_trip_mutation_commands.TripMutationCommandTests."
    "test_command_batch_is_atomic_when_later_command_fails",
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
            "stable_scheduled_item_ids_are_command_authority",
            "typed_route_edit_preview_runs_deterministic_invariants",
            "route_edit_apply_creates_reloadable_revision",
            "swap_replace_apply_is_idempotent",
            "fixed_items_are_rejected_before_revision_creation",
            "stale_base_rejects_preview_without_revision",
            "route_edit_undo_creates_compensating_revision",
            "swap_undo_creates_compensating_revision",
            "invalid_target_creates_no_revision",
            "failed_batch_has_no_partial_mutation",
            "different_key_duplicate_proposal_apply_creates_one_revision",
            "typed_mutations_invalidate_derived_workspace_surfaces",
            "candidate_registration_is_persistent_without_revision_creation",
            "candidate_deduplication_uses_content_digest",
            "candidate_reject_defer_restore_are_workflow_decisions",
            "candidate_decisions_are_idempotent_without_revision_creation",
            "rejected_candidate_admission_is_rejected_before_revision",
            "cross_trip_candidate_ids_are_not_admissible",
            "candidate_admission_creates_typed_revision_and_scheduled_decision",
            "candidate_admission_requires_repair_for_missing_execution_facts",
            "completion_undo_creates_compensating_revision",
        ],
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())

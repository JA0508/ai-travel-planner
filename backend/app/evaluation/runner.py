from __future__ import annotations

import time
from contextlib import ExitStack
from unittest.mock import patch

from app.api.routes import itinerary as itinerary_route
from app.evaluation.fixture_loader import load_cases, load_handoff_review_cases
from app.evaluation.fixture_provider import FixtureProviderSnapshot
from app.evaluation.invariants import evaluate_invariants
from app.evaluation.models import (
    EvaluationCaseResult,
    EvaluationInvariantResult,
    EvaluationReport,
    HandoffEvaluationCaseResult,
    HandoffEvaluationReport,
)
from app.planner.trace import PlannerTraceCollector, planner_trace_digest, stable_subject_id
from app.schemas import ItineraryRequest
from app.trips.planner_handoff import build_handoff_review_summary


HANDOFF_REQUIRED_STATUSES = {"apply_ready", "blocked", "stale", "unstable", "applied"}
HANDOFF_MIN_STRICT_FIXTURES = 5
HANDOFF_MIN_DRIFT_FIXTURES = 1


def run_planner_evaluation() -> EvaluationReport:
    results = [run_case(case) for case in load_cases()]
    failed_results = [
        result
        for result in results
        if result.status == "fail"
        or any(invariant.status == "fail" for invariant in result.invariant_results)
    ]
    return EvaluationReport(
        fixture_count=len(results),
        passed_count=len(results) - len(failed_results),
        failed_count=len(failed_results),
        deterministic_mismatch_count=sum(
            1 for result in results if not result.deterministic_match
        ),
        results=results,
    )


def run_handoff_review_evaluation() -> HandoffEvaluationReport:
    """Replay frozen-handoff review fixtures without invoking the planner."""

    results = [run_handoff_review_case(case) for case in load_handoff_review_cases()]
    failed_results = [result for result in results if not result.passed]
    return HandoffEvaluationReport(
        fixture_count=len(results),
        strict_fixture_count=sum(result.coverage == "strict" for result in results),
        drift_fixture_count=sum(result.coverage == "drift" for result in results),
        passed_count=len(results) - len(failed_results),
        failed_count=len(failed_results),
        results=results,
    )


def run_handoff_review_case(case: dict) -> HandoffEvaluationCaseResult:
    review_input = case["review_input"]
    expected = case["expected"]
    summary = build_handoff_review_summary(**review_input)
    repeated = build_handoff_review_summary(**review_input)
    invariants = [
        _handoff_invariant("expected_status", summary.status == expected["status"]),
        _handoff_invariant("expected_can_apply", summary.can_apply == expected["can_apply"]),
        _handoff_invariant(
            "deterministic_summary",
            summary.model_dump(mode="json") == repeated.model_dump(mode="json"),
        ),
    ]
    if case["coverage"] == "strict":
        invariants.extend(
            [
                _handoff_invariant(
                    "expected_blocking_reasons",
                    summary.blocking_reason_codes == expected["blocking_reason_codes"],
                ),
                _handoff_invariant(
                    "expected_warning_codes",
                    summary.warning_codes == expected["warning_codes"],
                ),
                _handoff_invariant(
                    "expected_trace_summary",
                    summary.trace.model_dump(mode="json", exclude={"reason_codes"}) == expected["trace"],
                ),
            ]
        )
    else:
        invariants.append(
            _handoff_invariant(
                "required_warning_codes",
                set(expected.get("required_warning_codes", [])).issubset(summary.warning_codes),
            )
        )
    return HandoffEvaluationCaseResult(
        case_id=case["id"],
        coverage=case["coverage"],
        status=summary.status,
        can_apply=summary.can_apply,
        passed=all(invariant.status == "pass" for invariant in invariants),
        deterministic_match=invariants[2].status == "pass",
        invariant_results=invariants,
    )


def _handoff_invariant(code: str, passed: bool) -> EvaluationInvariantResult:
    return EvaluationInvariantResult(code=code, status="pass" if passed else "fail")


def handoff_review_gate_errors(report: HandoffEvaluationReport) -> list[str]:
    errors: list[str] = []
    observed_statuses = {result.status for result in report.results}
    if report.strict_fixture_count < HANDOFF_MIN_STRICT_FIXTURES:
        errors.append(f"requires_at_least_{HANDOFF_MIN_STRICT_FIXTURES}_strict_fixtures")
    if report.drift_fixture_count < HANDOFF_MIN_DRIFT_FIXTURES:
        errors.append(f"requires_at_least_{HANDOFF_MIN_DRIFT_FIXTURES}_drift_fixture")
    missing_statuses = HANDOFF_REQUIRED_STATUSES - observed_statuses
    if missing_statuses:
        errors.append(f"missing_handoff_statuses:{','.join(sorted(missing_statuses))}")
    return errors


def run_case(case: dict) -> EvaluationCaseResult:
    first = execute_case(case)
    second = execute_case(case)
    deterministic_match = first["trace"].trace_digest == second["trace"].trace_digest
    invariant_results = evaluate_invariants(
        case=case,
        itinerary=first["itinerary"],
        trace=first["trace"],
        deterministic_match=deterministic_match,
    )
    metrics = build_metrics(first["trace"])
    status = "pass" if deterministic_match and all(
        invariant.status != "fail" for invariant in invariant_results
    ) else "fail"
    return EvaluationCaseResult(
        case_id=case["id"],
        status=status,
        trace_digest=first["trace"].trace_digest,
        repeat_trace_digest=second["trace"].trace_digest,
        deterministic_match=deterministic_match,
        invariant_results=invariant_results,
        metrics=metrics,
    )


def execute_case(case: dict) -> dict:
    provider = FixtureProviderSnapshot(case)
    payload = ItineraryRequest.model_validate(case["request"])
    collector = PlannerTraceCollector(
        planner_run_id=stable_subject_id("planner_run", case["id"]),
        input_summary=itinerary_route.build_planner_input_snapshot(
            payload,
            raw_text_ref=case["id"],
        ),
        strict=True,
        volatile_metadata={
            "fixture_id": case["id"],
            "started_at_epoch_ms": int(time.time() * 1000),
        },
    )
    with ExitStack() as stack:
        stack.enter_context(patch("app.api.routes.itinerary.normalize_poi", provider.normalize_poi))
        stack.enter_context(patch("app.api.routes.itinerary.normalize_hotel", provider.normalize_hotel))
        stack.enter_context(patch("app.api.routes.itinerary.normalize_anchor", provider.normalize_anchor))
        stack.enter_context(patch("app.core.scheduler.get_route", provider.get_route))
        itinerary = itinerary_route.build_itinerary_response(
            payload,
            trace_collector=collector,
        )
    trace = collector.build_trace(
        itinerary_route.build_planner_result_summary(itinerary)
    )
    trace.trace_digest = planner_trace_digest(trace)
    return {"itinerary": itinerary, "trace": trace}


def build_metrics(trace) -> dict:
    rejection_count_by_reason: dict[str, int] = {}
    for event in trace.decisions:
        if event.decision.value != "rejected":
            continue
        for reason in event.reason_codes:
            rejection_count_by_reason[reason.value] = rejection_count_by_reason.get(reason.value, 0) + 1
    return {
        "candidate_count": sum(
            1 for event in trace.decisions if event.subject_type.value == "candidate"
        ),
        "accepted_candidate_count": sum(
            1 for event in trace.decisions if event.decision.value == "accepted"
        ),
        "rejected_candidate_count": sum(
            1 for event in trace.decisions if event.decision.value == "rejected"
        ),
        "rejection_count_by_reason": rejection_count_by_reason,
        "scheduled_item_count": trace.result_summary.scheduled_item_count,
        "route_known_count": trace.provider_summary.route_known_count,
        "route_missing_count": trace.provider_summary.route_missing_count,
        "fixed_event_count": trace.result_summary.fixed_event_count,
        "fallback_usage_count": sum(
            1 for event in trace.decisions if event.decision.value == "fallback_used"
        ),
        "warning_count": len(trace.warnings),
    }

from __future__ import annotations

import time
from contextlib import ExitStack
from unittest.mock import patch

from app.api.routes import itinerary as itinerary_route
from app.evaluation.fixture_loader import load_cases
from app.evaluation.fixture_provider import FixtureProviderSnapshot
from app.evaluation.invariants import evaluate_invariants
from app.evaluation.models import EvaluationCaseResult, EvaluationReport
from app.planner.trace import PlannerTraceCollector, planner_trace_digest, stable_subject_id
from app.schemas import ItineraryRequest


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

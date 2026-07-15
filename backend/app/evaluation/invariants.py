from __future__ import annotations

import json
import re

from app.evaluation.models import EvaluationInvariantResult
from app.planner.trace import PlannerDecision, PlannerDecisionStage, PlannerTrace
from app.schemas import ItineraryResponse, ScheduledPOI


CRITICAL_INVARIANTS = [
    "FIXED_EVENTS_PRESERVED",
    "NO_SCHEDULE_OVERLAP",
    "WITHIN_DAY_AVAILABILITY",
    "WITHIN_ARRIVAL_DEPARTURE_BOUNDARIES",
    "NO_DUPLICATE_SCHEDULED_PLACE",
    "MISSING_ROUTE_NOT_ZERO",
    "ALL_SCHEDULED_ITEMS_TRACEABLE",
    "REJECTED_CANDIDATES_HAVE_REASON",
    "NO_SECRET_OR_PII_IN_TRACE",
]


def evaluate_invariants(
    *,
    case: dict,
    itinerary: ItineraryResponse,
    trace: PlannerTrace,
    deterministic_match: bool,
) -> list[EvaluationInvariantResult]:
    return [
        fixed_events_preserved(case, itinerary),
        no_schedule_overlap(itinerary),
        within_day_availability(itinerary),
        within_arrival_departure_boundaries(itinerary),
        no_duplicate_scheduled_place(itinerary),
        missing_route_not_zero(trace),
        all_scheduled_items_traceable(itinerary, trace),
        rejected_candidates_have_reason(trace),
        deterministic_replay(deterministic_match),
        no_secret_or_pii_in_trace(trace),
    ]


def all_items(itinerary: ItineraryResponse) -> list[ScheduledPOI]:
    return [
        item
        for day in itinerary.days
        for block in day.blocks
        for item in block.items
    ]


def fixed_events_preserved(case: dict, itinerary: ItineraryResponse) -> EvaluationInvariantResult:
    expected = [
        poi
        for bucket in ("scenic_spots", "restaurants")
        for poi in case["request"].get(bucket, [])
        if poi.get("fixed_day") is not None or poi.get("fixed_time_start") is not None
    ]
    scheduled = {item.name: item for item in all_items(itinerary)}
    failures = []
    for fixed in expected:
        item = scheduled.get(fixed["name"])
        if item is None or not item.is_fixed:
            failures.append(fixed["name"])
            continue
        if fixed.get("fixed_day") is not None and item.day != fixed["fixed_day"]:
            failures.append(fixed["name"])
        if fixed.get("fixed_time_start") and item.start_time.strftime("%H:%M") != fixed["fixed_time_start"]:
            failures.append(fixed["name"])
    return result("FIXED_EVENTS_PRESERVED", not failures, {"failed": failures})


def no_schedule_overlap(itinerary: ItineraryResponse) -> EvaluationInvariantResult:
    failures = []
    for day in itinerary.days:
        items = sorted(all_items_for_day(itinerary, day.day), key=lambda item: item.start_time)
        for left, right in zip(items, items[1:]):
            if left.end_time > right.start_time:
                failures.append({"day": day.day, "left": left.name, "right": right.name})
    return result("NO_SCHEDULE_OVERLAP", not failures, {"failed": failures})


def within_day_availability(itinerary: ItineraryResponse) -> EvaluationInvariantResult:
    failures = []
    for day in itinerary.days:
        for block in day.blocks:
            for item in block.items:
                if item.start_time < block.start_time or item.end_time > block.end_time:
                    failures.append({"day": day.day, "item": item.name})
    return result("WITHIN_DAY_AVAILABILITY", not failures, {"failed": failures})


def within_arrival_departure_boundaries(itinerary: ItineraryResponse) -> EvaluationInvariantResult:
    # Boundary availability is already materialized into day block windows.
    boundary = within_day_availability(itinerary)
    return EvaluationInvariantResult(
        code="WITHIN_ARRIVAL_DEPARTURE_BOUNDARIES",
        status=boundary.status,
        evidence=boundary.evidence,
    )


def no_duplicate_scheduled_place(itinerary: ItineraryResponse) -> EvaluationInvariantResult:
    seen: set[str] = set()
    duplicates: list[str] = []
    for item in all_items(itinerary):
        key = item.name.strip().casefold()
        if key in seen:
            duplicates.append(item.name)
        seen.add(key)
    return result("NO_DUPLICATE_SCHEDULED_PLACE", not duplicates, {"duplicates": duplicates})


def missing_route_not_zero(trace: PlannerTrace) -> EvaluationInvariantResult:
    bad = [
        route.model_dump(mode="json")
        for route in trace.provider_summary.routes
        if route.availability in {"missing", "failed"} and route.duration_seconds == 0
    ]
    return result("MISSING_ROUTE_NOT_ZERO", not bad, {"bad_routes": bad})


def all_scheduled_items_traceable(
    itinerary: ItineraryResponse,
    trace: PlannerTrace,
) -> EvaluationInvariantResult:
    accepted_names = {
        str(event.metrics.get("name"))
        for event in trace.decisions
        if event.stage == PlannerDecisionStage.SCHEDULE_COMMIT
        and event.decision == PlannerDecision.ACCEPTED
    }
    missing = [item.name for item in all_items(itinerary) if item.name not in accepted_names]
    return result("ALL_SCHEDULED_ITEMS_TRACEABLE", not missing, {"missing": missing})


def rejected_candidates_have_reason(trace: PlannerTrace) -> EvaluationInvariantResult:
    missing = [
        event.subject_id
        for event in trace.decisions
        if event.decision == PlannerDecision.REJECTED and not event.reason_codes
    ]
    return result("REJECTED_CANDIDATES_HAVE_REASON", not missing, {"missing": missing})


def deterministic_replay(deterministic_match: bool) -> EvaluationInvariantResult:
    return result("DETERMINISTIC_REPLAY", deterministic_match, {})


def no_secret_or_pii_in_trace(trace: PlannerTrace) -> EvaluationInvariantResult:
    trace_json = json.dumps(trace.model_dump(mode="json"), ensure_ascii=False)
    patterns = {
        "OPENAI_API_KEY": r"OPENAI_API_KEY",
        "AMAP_API_KEY": r"AMAP_API_KEY",
        "AUTHORIZATION": r"Authorization",
        "CONFIRMATION_CODE": r"confirmation_code",
        "EMAIL": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
        "PHONE": r"\b1[3-9]\d{9}\b",
        "API_KEY_VALUE": r"sk-[A-Za-z0-9_-]{20,}",
    }
    found = [
        label
        for label, pattern in patterns.items()
        if re.search(pattern, trace_json, flags=re.IGNORECASE)
    ]
    return result("NO_SECRET_OR_PII_IN_TRACE", not found, {"found": found})


def all_items_for_day(itinerary: ItineraryResponse, day_number: int) -> list[ScheduledPOI]:
    return [
        item
        for day in itinerary.days
        if day.day == day_number
        for block in day.blocks
        for item in block.items
    ]


def result(code: str, passed: bool, evidence: dict) -> EvaluationInvariantResult:
    return EvaluationInvariantResult(
        code=code,
        status="pass" if passed else "fail",
        evidence=evidence,
    )

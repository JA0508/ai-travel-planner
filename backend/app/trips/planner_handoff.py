from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.planner.trace import (
    PlannerDecision,
    PlannerDecisionStage,
    PlannerReasonCode,
    PlannerSubjectType,
    PlannerTraceCollector,
)
from app.schemas import AvailabilityWindow, ItineraryRequest, RestaurantInput, ScenicSpotInput, TravelMode, TripDaysInputSource

from .candidates import CandidateType, TripCandidateRecord
from .digests import sha256_digest
from .errors import PlannerHandoffBlockedError
from .intent_contracts import SourceLinkedTripIntentEnvelope


PLANNER_HANDOFF_INPUT_SCHEMA_VERSION = "planner-handoff-input-v1"
PLANNER_HANDOFF_POLICY_VERSION = "planner-handoff-policy-v1"


class PlannerHandoffTraceSummary(BaseModel):
    """A compact, read-only view of the trace stored with a frozen handoff."""

    model_config = ConfigDict(extra="forbid")

    decision_count: int
    accepted_decision_count: int
    rejected_decision_count: int
    warning_count: int
    reason_codes: list[str] = Field(default_factory=list)


class PlannerHandoffReviewSummary(BaseModel):
    """Current applicability of a frozen handoff without rerunning the planner."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["apply_ready", "blocked", "stale", "unstable", "applied"]
    can_apply: bool
    intent_revision_id: str
    current_intent_revision_id: str
    base_trip_revision_id: str | None = None
    current_trip_revision_id: str | None = None
    readiness_status: str
    blocking_reason_codes: list[str] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)
    trace: PlannerHandoffTraceSummary


def build_handoff_review_summary(
    *,
    bound_intent_revision_id: str,
    current_intent_revision_id: str,
    base_trip_revision_id: str | None,
    current_trip_revision_id: str | None,
    run_status: str,
    applied_revision_id: str | None,
    trace_snapshot: dict[str, Any],
    result_snapshot: dict[str, Any],
    readiness_status: str,
    readiness_blocking_reason_codes: list[str],
    readiness_warning_codes: list[str],
) -> PlannerHandoffReviewSummary:
    """Summarize a stored handoff using only frozen data and current boundaries."""

    trace = _handoff_trace_summary(trace_snapshot)
    blocking_reason_codes = list(readiness_blocking_reason_codes)
    warning_codes = list(readiness_warning_codes)

    if applied_revision_id is not None or run_status == "applied":
        status: Literal["apply_ready", "blocked", "stale", "unstable", "applied"] = "applied"
        can_apply = False
    elif bound_intent_revision_id != current_intent_revision_id:
        status = "stale"
        can_apply = False
        blocking_reason_codes.append("intent_revision_advanced")
    elif base_trip_revision_id != current_trip_revision_id:
        status = "stale"
        can_apply = False
        blocking_reason_codes.append("base_revision_advanced")
    else:
        realism = result_snapshot.get("planner_realism") or {}
        realism_issues = realism.get("issues") or []
        if realism.get("status") == "unstable":
            status = "unstable"
            can_apply = False
            blocking_reason_codes.extend(
                issue["code"]
                for issue in realism_issues
                if isinstance(issue, dict) and isinstance(issue.get("code"), str)
            )
            if not realism_issues:
                blocking_reason_codes.append("planner_realism_unstable")
        elif readiness_status not in {"ready_for_planning", "ready_with_assumptions"}:
            status = "blocked"
            can_apply = False
            blocking_reason_codes.append("intent_not_planner_ready")
        elif run_status != "pending":
            status = "blocked"
            can_apply = False
            blocking_reason_codes.append(f"handoff_run_{run_status}")
        else:
            status = "apply_ready"
            can_apply = True

    return PlannerHandoffReviewSummary(
        status=status,
        can_apply=can_apply,
        intent_revision_id=bound_intent_revision_id,
        current_intent_revision_id=current_intent_revision_id,
        base_trip_revision_id=base_trip_revision_id,
        current_trip_revision_id=current_trip_revision_id,
        readiness_status=readiness_status,
        blocking_reason_codes=_unique_codes(blocking_reason_codes),
        warning_codes=_unique_codes(warning_codes),
        trace=trace,
    )


def _handoff_trace_summary(trace_snapshot: dict[str, Any]) -> PlannerHandoffTraceSummary:
    decisions = [item for item in trace_snapshot.get("decisions", []) if isinstance(item, dict)]
    warnings = [item for item in trace_snapshot.get("warnings", []) if isinstance(item, dict)]
    reason_codes = [
        code
        for item in decisions
        for code in item.get("reason_codes", [])
        if isinstance(code, str)
    ]
    return PlannerHandoffTraceSummary(
        decision_count=len(decisions),
        accepted_decision_count=sum(item.get("decision") == "accepted" for item in decisions),
        rejected_decision_count=sum(item.get("decision") == "rejected" for item in decisions),
        warning_count=len(warnings),
        reason_codes=_unique_codes(reason_codes),
    )


def _unique_codes(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


class PlannerHandoffSourceLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_id: str
    field_id: str
    field_path: str
    provenance_node_ids: list[str] = Field(default_factory=list)
    authority: str
    confirmed: bool


class PlannerHandoffInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = PLANNER_HANDOFF_INPUT_SCHEMA_VERSION
    policy_version: str = PLANNER_HANDOFF_POLICY_VERSION
    trip_id: str
    # A Draft Trip is deliberately not attached to an itinerary revision yet.
    base_trip_revision_id: str | None = None
    intent_revision_id: str
    intent_semantic_digest: str
    intent_lineage_digest: str
    itinerary_request: ItineraryRequest
    source_links: list[PlannerHandoffSourceLink] = Field(default_factory=list)
    rejected_candidate_ids: list[str] = Field(default_factory=list)

    @property
    def digest(self) -> str:
        return sha256_digest(self.model_dump(mode="json"))


@dataclass(frozen=True, slots=True)
class PlannerHandoffBuildResult:
    handoff: PlannerHandoffInput
    field_links_by_candidate_id: dict[str, PlannerHandoffSourceLink]


def build_planner_handoff_input(
    *,
    envelope: SourceLinkedTripIntentEnvelope,
    candidates: list[TripCandidateRecord],
) -> PlannerHandoffBuildResult:
    formal = envelope.formal_contract
    readiness = formal.readiness
    if not formal.formal_contract_verified:
        raise PlannerHandoffBlockedError("formal_contract_not_verified")
    if readiness.status not in {"ready_for_planning", "ready_with_assumptions"}:
        raise PlannerHandoffBlockedError("intent_not_planner_ready")
    if readiness.unresolved_required_field_paths:
        raise PlannerHandoffBlockedError("intent_has_unresolved_required_fields")
    if not formal.destinations:
        raise PlannerHandoffBlockedError("destination_missing")
    if len(formal.destinations) != 1:
        raise PlannerHandoffBlockedError("multi_destination_handoff_not_supported")
    if formal.date_policy is None or formal.date_policy.trip_days is None:
        raise PlannerHandoffBlockedError("trip_days_missing")

    candidate_by_id = {candidate.id: candidate for candidate in candidates}
    source_links = _source_links(envelope)
    source_link_by_field_id = {link.field_id: link for link in source_links}
    candidate_links: dict[str, PlannerHandoffSourceLink] = {}
    scenic: list[ScenicSpotInput] = []
    restaurants: list[RestaurantInput] = []
    fixed_candidate_ids = {
        event.place_candidate_id
        for event in formal.fixed_events
        if event.place_candidate_id is not None
    }

    for preference in [*formal.must_visit_places, *formal.optional_places]:
        candidate = candidate_by_id.get(preference.trip_candidate_id)
        if candidate is None:
            raise PlannerHandoffBlockedError("intent_candidate_missing", candidate_id=preference.trip_candidate_id)
        raw = _candidate_to_raw(candidate, fixed_day=None, fixed_time_start=None, fixed_time_end=None)
        candidate_links[candidate.id] = source_link_by_field_id.get(
            preference.metadata.field_id,
            PlannerHandoffSourceLink(
                subject_id=candidate.id,
                field_id=preference.metadata.field_id,
                field_path=preference.metadata.field_path,
                provenance_node_ids=[],
                authority=preference.metadata.authority,
                confirmed=preference.metadata.confirmation_state in {"user_confirmed", "review_confirmed"},
            ),
        )
        # A fixed event is the same candidate with a stronger execution
        # constraint. It is added below only once, as the fixed item.
        if candidate.id in fixed_candidate_ids:
            continue
        if candidate.candidate_type == CandidateType.MEAL.value:
            restaurants.append(RestaurantInput.model_validate(raw))
        else:
            scenic.append(ScenicSpotInput.model_validate(raw))

    for fixed_event in formal.fixed_events:
        raw = _fixed_event_to_raw(
            fixed_event=fixed_event,
            candidate_by_id=candidate_by_id,
            start_date=formal.date_policy.start_date,
            trip_days=formal.date_policy.trip_days,
        )
        if fixed_event.place_candidate_id:
            candidate_links[fixed_event.place_candidate_id] = source_link_by_field_id.get(
                fixed_event.metadata.field_id,
                PlannerHandoffSourceLink(
                    subject_id=fixed_event.place_candidate_id,
                    field_id=fixed_event.metadata.field_id,
                    field_path=fixed_event.metadata.field_path,
                    provenance_node_ids=[],
                    authority=fixed_event.metadata.authority,
                    confirmed=fixed_event.metadata.confirmation_state in {"user_confirmed", "review_confirmed"},
                ),
            )
        if raw["candidate_id"] and candidate_by_id[raw["candidate_id"]].candidate_type == CandidateType.MEAL.value:
            restaurants.append(RestaurantInput.model_validate(raw))
        else:
            scenic.append(ScenicSpotInput.model_validate(raw))

    availability_windows = _availability_windows(formal, trip_days=formal.date_policy.trip_days)
    preferences = _planner_preferences(formal)
    city = formal.destinations[0].city_name
    itinerary_request = ItineraryRequest(
        city=city,
        scenic_spots=scenic,
        restaurants=restaurants,
        arrival_anchor=formal.arrival_boundary.location_text if formal.arrival_boundary else None,
        departure_anchor=formal.departure_boundary.location_text if formal.departure_boundary else None,
        availability_windows=availability_windows,
        preferences=preferences,
        auto_fill_sparse_days=False,
        trip_days=formal.date_policy.trip_days,
        trip_days_source=TripDaysInputSource.EXPLICIT,
        travel_mode=_travel_mode(formal),
    )
    handoff = PlannerHandoffInput(
        trip_id=envelope.trip_id,
        base_trip_revision_id=envelope.base_trip_revision_id,
        intent_revision_id=envelope.id,
        intent_semantic_digest=envelope.semantic_digest or envelope.content_digest,
        intent_lineage_digest=envelope.lineage_digest or envelope.content_digest,
        itinerary_request=itinerary_request,
        source_links=source_links,
        rejected_candidate_ids=[item.trip_candidate_id for item in formal.avoid_places],
    )
    return PlannerHandoffBuildResult(handoff=handoff, field_links_by_candidate_id=candidate_links)


def record_handoff_trace_context(
    collector: PlannerTraceCollector,
    *,
    handoff: PlannerHandoffInput,
    candidate_links: dict[str, PlannerHandoffSourceLink],
) -> None:
    for link in handoff.source_links:
        collector.record_decision(
            stage=PlannerDecisionStage.INTENT_NORMALIZATION,
            subject_type=PlannerSubjectType.INTENT,
            subject_id=link.subject_id,
            decision=PlannerDecision.ACCEPTED,
            reason_codes=[PlannerReasonCode.ACCEPTED_INPUT_CANDIDATE],
            metrics={"field_path": link.field_path, "authority": link.authority, "confirmed": link.confirmed},
            evidence_refs=[f"intent_field:{link.field_id}", *[f"provenance:{node_id}" for node_id in link.provenance_node_ids]],
        )
    for candidate_id in handoff.rejected_candidate_ids:
        collector.record_decision(
            stage=PlannerDecisionStage.CANDIDATE_VALIDATION,
            subject_type=PlannerSubjectType.CANDIDATE,
            subject_id=candidate_id,
            decision=PlannerDecision.REJECTED,
            reason_codes=[PlannerReasonCode.REJECTED_USER_EXCLUSION],
            evidence_refs=[f"trip_candidate:{candidate_id}"],
        )


def attach_handoff_source_links(
    itinerary,
    *,
    candidate_links: dict[str, PlannerHandoffSourceLink],
    collector: PlannerTraceCollector,
):
    """Attach formal-contract provenance to the frozen scheduled-item snapshot."""
    updated_days = []
    for day in itinerary.days:
        updated_blocks = []
        for block in day.blocks:
            updated_items = []
            for item in block.items:
                link = candidate_links.get(item.candidate_id or "")
                if link is None:
                    updated_items.append(item)
                    continue
                updated_item = item.model_copy(
                    update={
                        "source_label": "Confirmed intent candidate",
                        "source_reason": f"Confirmed intent field {link.field_path} was accepted by the deterministic planner.",
                        "candidate_provenance": {
                            "intent_field_id": link.field_id,
                            "intent_field_path": link.field_path,
                            "provenance_node_ids": link.provenance_node_ids,
                            "authority": link.authority,
                            "confirmed": link.confirmed,
                        },
                    }
                )
                collector.record_decision(
                    stage=PlannerDecisionStage.SCHEDULE_COMMIT,
                    subject_type=PlannerSubjectType.SCHEDULED_ITEM,
                    subject_id=updated_item.stable_id or updated_item.candidate_id or updated_item.name,
                    decision=PlannerDecision.ACCEPTED,
                    reason_codes=[PlannerReasonCode.ACCEPTED_RANKED_CANDIDATE],
                    metrics={
                        "candidate_id": updated_item.candidate_id,
                        "intent_field_id": link.field_id,
                        "day": updated_item.day,
                    },
                    evidence_refs=[
                        f"intent_field:{link.field_id}",
                        *[f"provenance:{node_id}" for node_id in link.provenance_node_ids],
                    ],
                )
                updated_items.append(updated_item)
            updated_blocks.append(block.model_copy(update={"items": updated_items}))
        updated_days.append(day.model_copy(update={"blocks": updated_blocks}))
    return itinerary.model_copy(update={"days": updated_days})


def _candidate_to_raw(
    candidate: TripCandidateRecord,
    *,
    fixed_day: int | None,
    fixed_time_start: time | None,
    fixed_time_end: time | None,
) -> dict[str, Any]:
    if not candidate.canonical_place_id or candidate.coordinates is None:
        raise PlannerHandoffBlockedError("intent_candidate_identity_not_verified", candidate_id=candidate.id)
    return {
        "name": candidate.display_name,
        "candidate_id": candidate.id,
        "canonical_place_id": candidate.canonical_place_id,
        "resolved_latitude": candidate.coordinates["latitude"],
        "resolved_longitude": candidate.coordinates["longitude"],
        "resolved_duration_minutes": candidate.estimated_duration_minutes,
        "fixed_day": fixed_day,
        "fixed_time_start": fixed_time_start,
        "fixed_time_end": fixed_time_end,
    }


def _fixed_event_to_raw(*, fixed_event, candidate_by_id: dict[str, TripCandidateRecord], start_date: date | None, trip_days: int) -> dict[str, Any]:
    fixed_day = fixed_event.fixed_day
    if fixed_event.start_at is not None:
        if start_date is None:
            raise PlannerHandoffBlockedError("fixed_event_requires_date_policy", field_id=fixed_event.metadata.field_id)
        fixed_day = (fixed_event.start_at.date() - start_date).days + 1
    if fixed_day is None or fixed_day < 1 or fixed_day > trip_days:
        raise PlannerHandoffBlockedError("fixed_event_outside_trip", field_id=fixed_event.metadata.field_id)
    start = fixed_event.start_at.time() if fixed_event.start_at else None
    end = fixed_event.end_at.time() if fixed_event.end_at else None
    if (start is None) != (end is None):
        raise PlannerHandoffBlockedError("fixed_event_time_range_incomplete", field_id=fixed_event.metadata.field_id)
    if fixed_event.place_candidate_id:
        candidate = candidate_by_id.get(fixed_event.place_candidate_id)
        if candidate is None:
            raise PlannerHandoffBlockedError("fixed_event_candidate_missing", candidate_id=fixed_event.place_candidate_id)
        return _candidate_to_raw(candidate, fixed_day=fixed_day, fixed_time_start=start, fixed_time_end=end)
    raise PlannerHandoffBlockedError(
        "fixed_event_identity_not_verified",
        field_id=fixed_event.metadata.field_id,
    )


def _availability_windows(formal, *, trip_days: int) -> list[AvailabilityWindow]:
    windows: list[AvailabilityWindow] = []
    start_date = formal.date_policy.start_date if formal.date_policy else None
    for window in formal.availability_windows:
        if start_date is None:
            raise PlannerHandoffBlockedError("availability_window_requires_date_policy", field_id=window.metadata.field_id)
        day = (window.date - start_date).days + 1
        if day < 1 or day > trip_days or window.crosses_midnight:
            raise PlannerHandoffBlockedError("availability_window_outside_supported_range", field_id=window.metadata.field_id)
        windows.append(AvailabilityWindow(day=day, available_start=window.start_time.strftime("%H:%M"), available_end=window.end_time.strftime("%H:%M")))
    for boundary, is_arrival in ((formal.arrival_boundary, True), (formal.departure_boundary, False)):
        if boundary is None:
            continue
        if start_date is not None:
            day = (boundary.local_datetime.date() - start_date).days + 1
        else:
            day = 1 if is_arrival else trip_days
        if day < 1 or day > trip_days:
            raise PlannerHandoffBlockedError("travel_boundary_outside_trip", field_id=boundary.metadata.field_id)
        value = boundary.local_datetime.strftime("%H:%M")
        windows.append(AvailabilityWindow(day=day, available_start=value if is_arrival else None, available_end=None if is_arrival else value))
    return windows


def _planner_preferences(formal) -> list[str]:
    values: list[str] = []
    if formal.pace:
        values.append({"relaxed": "不要太赶", "balanced": "节奏均衡", "intensive": "行程紧凑"}[formal.pace.value])
    values.extend(item.preference_text for item in formal.meal_preferences if item.preference != "avoid")
    values.extend(item.description for item in formal.traveler_needs)
    values.extend(item.exclusion_text for item in formal.exclusions)
    return values


def _travel_mode(formal) -> TravelMode | None:
    modes = {item.mode for item in formal.transport_preferences if item.preference in {"prefer", "require"}}
    if "drive" in modes or "taxi" in modes or "ride_hailing" in modes:
        return TravelMode.CAR
    if "rail" in modes:
        return TravelMode.RAIL
    if "flight" in modes:
        return TravelMode.AIRPLANE
    return None


def _source_links(envelope: SourceLinkedTripIntentEnvelope) -> list[PlannerHandoffSourceLink]:
    links: list[PlannerHandoffSourceLink] = []
    node_ids_by_field: dict[str, list[str]] = {}
    for node in envelope.provenance_graph.nodes:
        if node.field_path:
            node_ids_by_field.setdefault(node.field_path, []).append(node.node_id)
    for field in envelope.fields:
        if field.status.value != "selected":
            continue
        links.append(
            PlannerHandoffSourceLink(
                subject_id=field.field_id,
                field_id=field.field_id,
                field_path=field.field_path,
                provenance_node_ids=sorted(node_ids_by_field.get(field.field_path, [])),
                authority=max((ref.authority.value for ref in field.source_refs), default="legacy_unknown"),
                confirmed=field.confirmed_by_user,
            )
        )
    return links

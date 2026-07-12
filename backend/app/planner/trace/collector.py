from __future__ import annotations

from pydantic import ValidationError

from .identity import stable_subject_id
from .models import (
    JsonValue,
    PlannerDecision,
    PlannerDecisionEvent,
    PlannerDecisionStage,
    PlannerInputSnapshot,
    PlannerResultSummary,
    PlannerSubjectType,
    PlannerTrace,
    PlannerTraceWarning,
    ProviderRouteSnapshot,
    ProviderSnapshotSummary,
)
from .reason_codes import PlannerReasonCode
from .versions import PLANNER_TRACE_SCHEMA_VERSION, PLANNER_VERSION


class PlannerTraceCollector:
    def __init__(
        self,
        *,
        planner_run_id: str,
        input_summary: PlannerInputSnapshot,
        strict: bool = False,
        volatile_metadata: dict[str, JsonValue] | None = None,
    ) -> None:
        self.planner_run_id = planner_run_id
        self.input_summary = input_summary
        self.strict = strict
        self.volatile_metadata = volatile_metadata or {}
        self.decisions: list[PlannerDecisionEvent] = []
        self.warnings: list[PlannerTraceWarning] = []
        self.provider_summary = ProviderSnapshotSummary()
        self._sequence = 0

    def record_decision(
        self,
        *,
        stage: PlannerDecisionStage,
        subject_type: PlannerSubjectType,
        subject_id: str,
        decision: PlannerDecision,
        reason_codes: list[PlannerReasonCode],
        metrics: dict[str, JsonValue] | None = None,
        evidence_refs: list[str] | None = None,
    ) -> None:
        self._sequence += 1
        try:
            self.decisions.append(
                PlannerDecisionEvent(
                    sequence=self._sequence,
                    stage=stage,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    decision=decision,
                    reason_codes=reason_codes,
                    metrics=metrics or {},
                    evidence_refs=evidence_refs or [],
                )
            )
        except ValidationError as exc:
            if self.strict:
                raise
            self.record_warning(
                code="TRACE_EVENT_SCHEMA_INVALID",
                stage=stage,
                subject_id=subject_id,
                detail=str(exc),
            )

    def record_warning(
        self,
        *,
        code: str,
        stage: PlannerDecisionStage | None = None,
        subject_id: str | None = None,
        recoverable: bool = True,
        detail: str | None = None,
    ) -> None:
        warning = PlannerTraceWarning(
            code=code,
            stage=stage,
            subject_id=subject_id,
            recoverable=recoverable,
            detail=detail,
        )
        self.warnings.append(warning)
        if self.strict and not recoverable:
            raise RuntimeError(code)

    def record_route_snapshot(
        self,
        *,
        origin_id: str,
        destination_id: str,
        travel_mode: str,
        availability: str,
        duration_seconds: int | None = None,
        distance_meters: int | None = None,
    ) -> None:
        route = ProviderRouteSnapshot(
            origin_id=origin_id,
            destination_id=destination_id,
            travel_mode=travel_mode,
            duration_seconds=duration_seconds,
            distance_meters=distance_meters,
            availability=availability,
        )
        self.provider_summary.routes.append(route)
        if availability == "known":
            self.provider_summary.route_known_count += 1
        elif availability == "missing":
            self.provider_summary.route_missing_count += 1
        elif availability == "failed":
            self.provider_summary.route_failed_count += 1
        elif availability == "not_requested":
            self.provider_summary.route_not_requested_count += 1

    def mark_place_known(self) -> None:
        self.provider_summary.place_known_count += 1

    def mark_place_missing(self) -> None:
        self.provider_summary.place_missing_count += 1

    def mark_place_failed(self) -> None:
        self.provider_summary.place_failed_count += 1

    def build_trace(self, result_summary: PlannerResultSummary) -> PlannerTrace:
        return PlannerTrace(
            schema_version=PLANNER_TRACE_SCHEMA_VERSION,
            planner_version=PLANNER_VERSION,
            planner_run_id=self.planner_run_id,
            volatile_metadata=self.volatile_metadata,
            input_summary=self.input_summary,
            provider_summary=self.provider_summary,
            decisions=[event.model_copy(deep=True) for event in self.decisions],
            result_summary=result_summary,
            warnings=[warning.model_copy(deep=True) for warning in self.warnings],
        )


def subject_id_for_name(subject_type: PlannerSubjectType, name: str, *parts: object) -> str:
    return stable_subject_id(subject_type.value, name.strip().casefold(), *parts)

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.nl_parser import parse_trip_text_fallback
from app.trips.access import generate_intent_revision_id
from app.trips.candidates import TripCandidateRecord
from app.trips.digests import sha256_digest


TRIP_INTENT_ENVELOPE_SCHEMA_VERSION = "1.2"
TRIP_INTENT_COMPILER_VERSION = "intent-compiler-v3"


class IntentSourceType(str, Enum):
    DIRECT_USER_LANGUAGE = "direct_user_language"
    STRUCTURED_USER_OVERRIDE = "structured_user_override"
    LLM_PROPOSAL = "llm_proposal"
    TRIP_CANDIDATE = "trip_candidate"
    EXISTING_TRIP_STATE = "existing_trip_state"
    EXISTING_INTENT_REVISION = "existing_intent_revision"


class IntentFieldKind(str, Enum):
    HARD = "hard"
    SOFT = "soft"
    ASSUMPTION = "assumption"


class IntentFieldStatus(str, Enum):
    SELECTED = "selected"
    SHADOWED = "shadowed"
    NEEDS_CLARIFICATION = "needs_clarification"


class IntentPlannerReadyStatus(str, Enum):
    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"
    BLOCKED = "blocked"


class IntentAuthority(str, Enum):
    USER_CONFIRMED = "user_confirmed"
    REVIEWED_SOURCE = "reviewed_source"
    SAVED_STATE = "saved_state"
    LLM_UNTRUSTED = "llm_untrusted"
    DETERMINISTIC_CONTEXT = "deterministic_context"
    LEGACY_UNKNOWN = "legacy_unknown"


class IntentValueType(str, Enum):
    UNKNOWN = "unknown"
    DESTINATION_CITY = "destination_city"
    TRIP_DAYS = "trip_days"
    PACE = "pace"
    TRANSPORT_PREFERENCE = "transport_preference"
    MUST_CANDIDATE = "must_candidate"
    FIXED_EVENT = "fixed_event"
    GENERAL_PREFERENCE = "general_preference"


class ProvenanceNodeType(str, Enum):
    ENVELOPE_REVISION = "envelope_revision"
    PARSER_RESULT = "parser_result"
    SOURCE = "source"
    FIELD = "field"
    ASSUMPTION = "assumption"


class ProvenanceEdgeType(str, Enum):
    PRODUCED = "produced"
    SUPPORTS = "supports"
    SELECTED_IN = "selected_in"
    SHADOWED_IN = "shadowed_in"
    CREATED_ASSUMPTION = "created_assumption"


class IntentSourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref_id: str
    source_type: IntentSourceType
    source_id: str | None = None
    field_path: str
    label: str
    priority: int = Field(..., ge=0, le=100)
    confirmed: bool = False
    authority: IntentAuthority = IntentAuthority.LEGACY_UNKNOWN
    evidence_digest: str
    evidence_refs: list[str] = Field(default_factory=list)


class IntentField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_id: str
    field_path: str
    value: Any
    semantic_type: IntentValueType = IntentValueType.UNKNOWN
    semantic_value: dict[str, Any] = Field(default_factory=dict)
    kind: IntentFieldKind
    confidence: float = Field(..., ge=0, le=1)
    source_refs: list[IntentSourceRef] = Field(default_factory=list)
    confirmed_by_user: bool = False
    priority: int = Field(..., ge=0, le=100)
    status: IntentFieldStatus = IntentFieldStatus.SELECTED
    validation_codes: list[str] = Field(default_factory=list)
    explanation: str


class IntentConflict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conflict_id: str
    field_path: str
    severity: Literal["blocking", "non_blocking"]
    winner_field_id: str | None = None
    losing_field_ids: list[str] = Field(default_factory=list)
    reason_code: str
    explanation: str
    requires_clarification: bool
    source_refs: list[IntentSourceRef] = Field(default_factory=list)


class ClarificationQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    field_paths: list[str]
    answer_field_path: str | None = None
    answer_value_type: Literal["string", "integer", "pace", "string_list"] = "string"
    question: str
    priority: int = Field(..., ge=0, le=100)
    blocking: bool
    impact: Literal["planner_blocking", "planner_quality", "evidence_quality"] = "planner_blocking"
    reason_code: str
    options: list[Any] = Field(default_factory=list)


class TypedIntentValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_path: str
    field_id: str | None = None
    value: Any
    semantic_type: IntentValueType = IntentValueType.UNKNOWN
    semantic_value: dict[str, Any] = Field(default_factory=dict)
    kind: IntentFieldKind
    confidence: float = Field(..., ge=0, le=1)
    confirmed_by_user: bool
    source_refs: list[IntentSourceRef] = Field(default_factory=list)
    validation_codes: list[str] = Field(default_factory=list)


class TypedDatePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trip_days: TypedIntentValue | None = None
    availability_windows: list[TypedIntentValue] = Field(default_factory=list)


class TypedPoiPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    must_candidates: list[TypedIntentValue] = Field(default_factory=list)
    optional_candidates: list[TypedIntentValue] = Field(default_factory=list)
    exclusions: list[TypedIntentValue] = Field(default_factory=list)


class TypedTripIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    destinations: list[TypedIntentValue] = Field(default_factory=list)
    date_policy: TypedDatePolicy = Field(default_factory=TypedDatePolicy)
    fixed_events: list[TypedIntentValue] = Field(default_factory=list)
    poi_preferences: TypedPoiPreferences = Field(default_factory=TypedPoiPreferences)
    pace: TypedIntentValue | None = None
    transport_preferences: list[TypedIntentValue] = Field(default_factory=list)
    budget: TypedIntentValue | None = None
    travelers: list[TypedIntentValue] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    typed_assumptions: list["IntentAssumption"] = Field(default_factory=list)
    unresolved_questions: list[ClarificationQuestion] = Field(default_factory=list)


class IntentAssumption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assumption_id: str
    field_path: str
    assumption_type: Literal["missing_value", "empty_reviewed_candidate_set", "carried_forward_assumption"]
    value: Any = None
    has_assumed_value: bool
    blocks_planner_ready: bool
    reason_code: str
    explanation: str
    source_refs: list[IntentSourceRef] = Field(default_factory=list)


class IntentProvenanceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_path: str
    selected_field_ids: list[str] = Field(default_factory=list)
    shadowed_field_ids: list[str] = Field(default_factory=list)
    source_types: list[IntentSourceType] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    confirmed: bool
    max_confidence: float = Field(..., ge=0, le=1)


class IntentParserResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parser_name: str
    parser_version: str
    status: Literal["not_run", "parsed", "validated"]
    input_digests: list[str] = Field(default_factory=list)
    extracted_field_paths: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class IntentProvenanceNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    node_type: ProvenanceNodeType
    label: str
    field_path: str | None = None
    source_type: IntentSourceType | None = None
    source_id: str | None = None
    authority: IntentAuthority = IntentAuthority.LEGACY_UNKNOWN
    confirmed: bool = False
    digest: str | None = None


class IntentProvenanceEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_node_id: str
    to_node_id: str
    relation: ProvenanceEdgeType


class IntentProvenanceGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[IntentProvenanceNode] = Field(default_factory=list)
    edges: list[IntentProvenanceEdge] = Field(default_factory=list)


class IntentReadinessPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version: str = "intent-readiness-v2"
    status: IntentPlannerReadyStatus
    blocking_reason_codes: list[str] = Field(default_factory=list)
    allowed_assumption_ids: list[str] = Field(default_factory=list)
    requires_user_confirmation: bool = False


class PlannerReadyIntentPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city: str | None = None
    trip_days: int | None = Field(default=None, ge=1)
    must_place_candidate_ids: list[str] = Field(default_factory=list)
    must_place_names: list[str] = Field(default_factory=list)
    pace: str | None = None
    transport_preferences: list[str] = Field(default_factory=list)
    fixed_events: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class SourceLinkedTripIntentEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    schema_version: str = TRIP_INTENT_ENVELOPE_SCHEMA_VERSION
    revision_number: int
    trip_id: str
    base_trip_revision_id: str
    parent_intent_revision_id: str | None = None
    compiler_version: str = TRIP_INTENT_COMPILER_VERSION
    fields: list[IntentField] = Field(default_factory=list)
    conflicts: list[IntentConflict] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    typed_assumptions: list[IntentAssumption] = Field(default_factory=list)
    clarification_queue: list[ClarificationQuestion] = Field(default_factory=list)
    parser_result: IntentParserResult = Field(default_factory=lambda: IntentParserResult(
        parser_name="intent_contract_compiler",
        parser_version=TRIP_INTENT_COMPILER_VERSION,
        status="not_run",
    ))
    typed_intent: TypedTripIntent = Field(default_factory=TypedTripIntent)
    provenance_summary: list[IntentProvenanceSummary] = Field(default_factory=list)
    provenance_graph: IntentProvenanceGraph = Field(default_factory=IntentProvenanceGraph)
    planner_ready_intent: PlannerReadyIntentPreview
    planner_ready_status: IntentPlannerReadyStatus
    readiness_policy: IntentReadinessPolicy | None = None
    validation_report: dict[str, Any]
    source_digest: str
    semantic_digest: str | None = None
    content_digest: str
    created_at: str


class IntentStructuredOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city: str | None = Field(default=None, max_length=120)
    trip_days: int | None = Field(default=None, ge=1, le=60)
    must_candidate_ids: list[str] = Field(default_factory=list, max_length=40)
    pace: Literal["relaxed", "balanced", "intensive"] | None = None
    transport_preferences: list[str] = Field(default_factory=list, max_length=20)
    fixed_events: list[dict[str, Any]] = Field(default_factory=list, max_length=40)

    @field_validator("city")
    @classmethod
    def strip_city(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

    @field_validator("transport_preferences")
    @classmethod
    def strip_transport(cls, value: list[str]) -> list[str]:
        return unique_texts(value)


class UntrustedIntentProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city: str | None = Field(default=None, max_length=120)
    trip_days: int | None = Field(default=None, ge=1, le=60)
    must_candidate_ids: list[str] = Field(default_factory=list, max_length=40)
    pace: Literal["relaxed", "balanced", "intensive"] | None = None
    transport_preferences: list[str] = Field(default_factory=list, max_length=20)
    fixed_events: list[dict[str, Any]] = Field(default_factory=list, max_length=40)
    explanation: str | None = Field(default=None, max_length=1000)


class CompileTripIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_revision_id: str = Field(..., min_length=1)
    direct_user_text: str | None = Field(default=None, max_length=10000)
    candidate_ids: list[str] = Field(default_factory=list, max_length=80)
    structured_overrides: IntentStructuredOverrides | None = None
    llm_proposal: UntrustedIntentProposal | None = None
    use_llm_proposal_adapter: bool = False


class EditTripIntentEnvelopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_revision_id: str = Field(..., min_length=1)
    field_updates: IntentStructuredOverrides


class AnswerIntentClarificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_revision_id: str = Field(..., min_length=1)
    answer: Any


class RestoreTripIntentEnvelopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_revision_id: str = Field(..., min_length=1)


class TripIntentRevisionMetadata(BaseModel):
    id: str
    trip_id: str
    revision_number: int
    base_trip_revision_id: str
    parent_intent_revision_id: str | None = None
    envelope_schema_version: str
    compiler_version: str
    source_digest: str
    content_digest: str
    created_at: str


class CompileTripIntentResponse(BaseModel):
    envelope: SourceLinkedTripIntentEnvelope
    revision: TripIntentRevisionMetadata
    idempotent_replay: bool = False


class TripIntentRevisionDetailResponse(BaseModel):
    envelope: SourceLinkedTripIntentEnvelope
    revision: TripIntentRevisionMetadata


class TripIntentRevisionListResponse(BaseModel):
    revisions: list[TripIntentRevisionMetadata]


@dataclass(slots=True)
class TripIntentRevisionRecord:
    id: str
    trip_id: str
    revision_number: int
    parent_intent_revision_id: str | None
    base_trip_revision_id: str
    envelope_schema_version: str
    envelope: dict[str, Any]
    content_digest: str
    compiler_version: str
    source_digest: str
    validation_report: dict[str, Any]
    created_at: str


@dataclass(slots=True)
class CreateIntentRevisionResult:
    revision: TripIntentRevisionRecord
    idempotent_replay: bool = False


@dataclass(slots=True)
class _CandidateField:
    field_path: str
    value: Any
    semantic_type: IntentValueType
    semantic_value: dict[str, Any]
    kind: IntentFieldKind
    confidence: float
    source_ref: IntentSourceRef
    explanation: str


def compile_source_linked_intent(
    *,
    trip_id: str,
    base_revision_id: str,
    parent_intent_revision_id: str | None,
    next_revision_number: int,
    created_at: str,
    request: CompileTripIntentRequest,
    existing_trip_snapshot: dict[str, Any],
    parent_intent_snapshot: dict[str, Any] | None = None,
    candidates: list[TripCandidateRecord],
    candidate_workflow_states: dict[str, str],
) -> SourceLinkedTripIntentEnvelope:
    field_candidates: list[_CandidateField] = []
    if parent_intent_snapshot is not None:
        field_candidates.extend(_fields_from_existing_intent_revision(parent_intent_snapshot))
    field_candidates.extend(_fields_from_existing_trip(existing_trip_snapshot))
    if request.direct_user_text and request.direct_user_text.strip():
        field_candidates.extend(_fields_from_user_text(request.direct_user_text.strip()))
    field_candidates.extend(_fields_from_candidates(candidates, candidate_workflow_states))
    if request.llm_proposal is not None:
        field_candidates.extend(_fields_from_payload(request.llm_proposal.model_dump(mode="json"), IntentSourceType.LLM_PROPOSAL))
    if request.structured_overrides is not None:
        field_candidates.extend(_fields_from_payload(request.structured_overrides.model_dump(mode="json"), IntentSourceType.STRUCTURED_USER_OVERRIDE))

    selected, shadowed, conflicts, clarifications = _select_fields(field_candidates)
    fields = [*selected, *shadowed]
    planner_ready = _build_planner_ready(selected)
    validation_conflicts = _validate_selected_fields(selected, planner_ready)
    conflicts.extend(validation_conflicts)
    typed_assumptions = _build_typed_assumptions(selected, planner_ready)
    assumptions = [assumption.explanation for assumption in typed_assumptions]
    for assumption in assumptions:
        if assumption not in planner_ready.assumptions:
            planner_ready.assumptions.append(assumption)
    typed_intent = _build_typed_intent(selected, clarifications, assumptions, typed_assumptions)
    provenance_summary = _build_provenance_summary(selected, shadowed)
    parser_result = _build_parser_result(request, fields)
    provenance_graph = _build_provenance_graph(
        envelope_id=f"intent_revision:{trip_id}:{next_revision_number}",
        parser_result=parser_result,
        fields=fields,
        assumptions=typed_assumptions,
    )
    blocking_conflicts = [item for item in conflicts if item.severity == "blocking"]
    blocking_clarifications = [item for item in clarifications if item.blocking]
    blocking_assumptions = [
        assumption
        for assumption in typed_assumptions
        if assumption.blocks_planner_ready and not assumption.has_assumed_value
    ]
    status = (
        IntentPlannerReadyStatus.BLOCKED
        if blocking_conflicts
        else IntentPlannerReadyStatus.NEEDS_CLARIFICATION
        if blocking_clarifications or blocking_assumptions
        else IntentPlannerReadyStatus.READY
    )
    readiness_policy = IntentReadinessPolicy(
        status=status,
        blocking_reason_codes=unique_texts(
            [
                *[conflict.reason_code for conflict in blocking_conflicts],
                *[item.reason_code for item in blocking_clarifications],
                *[item.reason_code for item in blocking_assumptions],
            ]
        ),
        allowed_assumption_ids=[
            assumption.assumption_id
            for assumption in typed_assumptions
            if not assumption.blocks_planner_ready or assumption.has_assumed_value
        ],
        requires_user_confirmation=bool(blocking_clarifications or blocking_assumptions),
    )
    validation_report = {
        "schema_version": "1.2",
        "compiler_version": TRIP_INTENT_COMPILER_VERSION,
        "llm_proposal_validated": request.llm_proposal is not None,
        "parser_status": parser_result.status,
        "manual_override_priority_enforced": any(
            conflict.reason_code == "higher_priority_source_selected"
            and any(ref.source_type == IntentSourceType.STRUCTURED_USER_OVERRIDE for ref in conflict.source_refs)
            for conflict in conflicts
        ),
        "blocking_conflict_count": sum(1 for conflict in conflicts if conflict.severity == "blocking"),
        "clarification_count": len(clarifications),
        "blocking_clarification_count": len(blocking_clarifications),
        "blocking_unvalued_assumption_count": len(blocking_assumptions),
        "typed_intent_sections": _typed_section_names(typed_intent),
        "provenance_summary_count": len(provenance_summary),
        "provenance_graph_node_count": len(provenance_graph.nodes),
        "planner_ready": status == IntentPlannerReadyStatus.READY,
        "excluded_candidate_ids": [
            candidate.id
            for candidate in candidates
            if candidate_workflow_states.get(candidate.id) in {"rejected", "deferred"}
        ],
    }
    source_digest = sha256_digest(
        {
            "request": request.model_dump(mode="json"),
            "candidate_ids": [candidate.id for candidate in candidates],
            "base_revision_id": base_revision_id,
        }
    )
    semantic_digest = _build_semantic_digest(
        selected=selected,
        conflicts=conflicts,
        assumptions=typed_assumptions,
        planner_ready_status=status,
    )
    envelope_without_digest = {
        "trip_id": trip_id,
        "base_trip_revision_id": base_revision_id,
        "parent_intent_revision_id": parent_intent_revision_id,
        "revision_number": next_revision_number,
        "fields": [field.model_dump(mode="json") for field in fields],
        "conflicts": [conflict.model_dump(mode="json") for conflict in conflicts],
        "assumptions": assumptions,
        "typed_assumptions": [assumption.model_dump(mode="json") for assumption in typed_assumptions],
        "clarification_queue": [item.model_dump(mode="json") for item in clarifications],
        "parser_result": parser_result.model_dump(mode="json"),
        "typed_intent": typed_intent.model_dump(mode="json"),
        "provenance_summary": [item.model_dump(mode="json") for item in provenance_summary],
        "provenance_graph": provenance_graph.model_dump(mode="json"),
        "planner_ready_intent": planner_ready.model_dump(mode="json"),
        "planner_ready_status": status.value,
        "readiness_policy": readiness_policy.model_dump(mode="json"),
        "validation_report": validation_report,
        "source_digest": source_digest,
        "semantic_digest": semantic_digest,
    }
    content_digest = sha256_digest(envelope_without_digest)
    return SourceLinkedTripIntentEnvelope(
        id=generate_intent_revision_id(),
        revision_number=next_revision_number,
        trip_id=trip_id,
        base_trip_revision_id=base_revision_id,
        parent_intent_revision_id=parent_intent_revision_id,
        fields=fields,
        conflicts=conflicts,
        assumptions=assumptions,
        typed_assumptions=typed_assumptions,
        clarification_queue=clarifications,
        parser_result=parser_result,
        typed_intent=typed_intent,
        provenance_summary=provenance_summary,
        provenance_graph=provenance_graph,
        planner_ready_intent=planner_ready,
        planner_ready_status=status,
        readiness_policy=readiness_policy,
        validation_report=validation_report,
        source_digest=source_digest,
        semantic_digest=semantic_digest,
        content_digest=content_digest,
        created_at=created_at,
    )


def intent_revision_metadata(record: TripIntentRevisionRecord) -> TripIntentRevisionMetadata:
    return TripIntentRevisionMetadata(
        id=record.id,
        trip_id=record.trip_id,
        revision_number=record.revision_number,
        parent_intent_revision_id=record.parent_intent_revision_id,
        base_trip_revision_id=record.base_trip_revision_id,
        envelope_schema_version=record.envelope_schema_version,
        compiler_version=record.compiler_version,
        source_digest=record.source_digest,
        content_digest=record.content_digest,
        created_at=record.created_at,
    )


def _source_ref(
    source_type: IntentSourceType,
    *,
    field_path: str,
    label: str,
    source_id: str | None,
    priority: int,
    confirmed: bool,
    value: Any,
    evidence_refs: list[str] | None = None,
) -> IntentSourceRef:
    refs = unique_texts(evidence_refs or [])
    return IntentSourceRef(
        ref_id=f"src_{sha256_digest({'source_type': source_type.value, 'field_path': field_path, 'source_id': source_id, 'value': value})[:16]}",
        source_type=source_type,
        source_id=source_id,
        field_path=field_path,
        label=label,
        priority=priority,
        confirmed=confirmed,
        authority=_authority_for_source(source_type, confirmed),
        evidence_digest=sha256_digest(
            {
                "field_path": field_path,
                "value": value,
                "source_id": source_id,
                "evidence_refs": refs,
            }
        ),
        evidence_refs=refs,
    )


def _authority_for_source(source_type: IntentSourceType, confirmed: bool) -> IntentAuthority:
    if source_type == IntentSourceType.STRUCTURED_USER_OVERRIDE or (
        source_type == IntentSourceType.DIRECT_USER_LANGUAGE and confirmed
    ):
        return IntentAuthority.USER_CONFIRMED
    if source_type == IntentSourceType.TRIP_CANDIDATE:
        return IntentAuthority.REVIEWED_SOURCE
    if source_type in {IntentSourceType.EXISTING_TRIP_STATE, IntentSourceType.EXISTING_INTENT_REVISION}:
        return IntentAuthority.SAVED_STATE
    if source_type == IntentSourceType.LLM_PROPOSAL:
        return IntentAuthority.LLM_UNTRUSTED
    return IntentAuthority.LEGACY_UNKNOWN


def _candidate(
    field_path: str,
    value: Any,
    *,
    kind: IntentFieldKind,
    confidence: float,
    source_ref: IntentSourceRef,
    explanation: str,
) -> _CandidateField:
    return _CandidateField(
        field_path=field_path,
        value=value,
        semantic_type=_semantic_type_for_field(field_path),
        semantic_value=_semantic_value_for_field(field_path, value),
        kind=kind,
        confidence=confidence,
        source_ref=source_ref,
        explanation=explanation,
    )


def _semantic_type_for_field(field_path: str) -> IntentValueType:
    return {
        "trip.city": IntentValueType.DESTINATION_CITY,
        "trip.trip_days": IntentValueType.TRIP_DAYS,
        "trip.pace": IntentValueType.PACE,
        "preferences.transport": IntentValueType.TRANSPORT_PREFERENCE,
        "poi.must_candidates": IntentValueType.MUST_CANDIDATE,
        "time.fixed_events": IntentValueType.FIXED_EVENT,
        "preferences.general": IntentValueType.GENERAL_PREFERENCE,
    }.get(field_path, IntentValueType.UNKNOWN)


def _semantic_value_for_field(field_path: str, value: Any) -> dict[str, Any]:
    if field_path == "trip.city":
        return {"city": str(value).strip()}
    if field_path == "trip.trip_days":
        return {"days": int(value)}
    if field_path == "trip.pace":
        return {"pace": str(value).strip()}
    if field_path == "preferences.transport":
        return {"mode": str(value).strip()}
    if field_path == "poi.must_candidates":
        return {"candidate_id": str(value).strip()}
    if field_path == "time.fixed_events":
        return {"event": value if isinstance(value, dict) else {"value": value}}
    if field_path == "preferences.general":
        return {"preference": str(value).strip()}
    return {"value": value}


def _fields_from_payload(payload: dict[str, Any], source_type: IntentSourceType) -> list[_CandidateField]:
    priority = 100 if source_type == IntentSourceType.STRUCTURED_USER_OVERRIDE else 30
    confirmed = source_type == IntentSourceType.STRUCTURED_USER_OVERRIDE
    label = "User override" if confirmed else "LLM proposal"
    fields: list[_CandidateField] = []
    for key in ("city", "trip_days", "pace"):
        value = payload.get(key)
        if value in (None, "", []):
            continue
        field_path = f"trip.{key}"
        fields.append(
            _candidate(
                field_path,
                value,
                kind=IntentFieldKind.HARD if key in {"city", "trip_days"} else IntentFieldKind.SOFT,
                confidence=1.0 if confirmed else 0.55,
                source_ref=_source_ref(
                    source_type,
                    field_path=field_path,
                    label=label,
                    source_id=source_type.value,
                    priority=priority,
                    confirmed=confirmed,
                    value=value,
                ),
                explanation=f"{label} supplied {field_path}.",
            )
        )
    for value in unique_texts(payload.get("transport_preferences") or []):
        field_path = "preferences.transport"
        fields.append(
            _candidate(
                field_path,
                value,
                kind=IntentFieldKind.SOFT,
                confidence=1.0 if confirmed else 0.5,
                source_ref=_source_ref(
                    source_type,
                    field_path=field_path,
                    label=label,
                    source_id=source_type.value,
                    priority=priority,
                    confirmed=confirmed,
                    value=value,
                ),
                explanation=f"{label} supplied a transport preference.",
            )
        )
    for candidate_id in payload.get("must_candidate_ids") or []:
        field_path = "poi.must_candidates"
        fields.append(
            _candidate(
                field_path,
                candidate_id,
                kind=IntentFieldKind.HARD if confirmed else IntentFieldKind.ASSUMPTION,
                confidence=1.0 if confirmed else 0.45,
                source_ref=_source_ref(
                    source_type,
                    field_path=field_path,
                    label=label,
                    source_id=str(candidate_id),
                    priority=priority,
                    confirmed=confirmed,
                    value=candidate_id,
                ),
                explanation=f"{label} referenced a must-visit candidate.",
            )
        )
    for index, event in enumerate(payload.get("fixed_events") or []):
        field_path = "time.fixed_events"
        fields.append(
            _candidate(
                field_path,
                event,
                kind=IntentFieldKind.HARD,
                confidence=1.0 if confirmed else 0.5,
                source_ref=_source_ref(
                    source_type,
                    field_path=field_path,
                    label=label,
                    source_id=f"{source_type.value}:fixed_event_{index}",
                    priority=priority,
                    confirmed=confirmed,
                    value=event,
                ),
                explanation=f"{label} supplied a fixed event.",
            )
        )
    return fields


def _fields_from_user_text(text: str) -> list[_CandidateField]:
    parsed = parse_trip_text_fallback(text)
    fields: list[_CandidateField] = []
    if parsed.city:
        fields.append(_text_field("trip.city", parsed.city, IntentFieldKind.HARD, text))
    if parsed.trip_days:
        fields.append(_text_field("trip.trip_days", parsed.trip_days, IntentFieldKind.HARD, text))
    if "不要太赶" in text or "不太赶" in text or "轻松" in text:
        fields.append(_text_field("trip.pace", "relaxed", IntentFieldKind.SOFT, text))
    for preference in unique_texts(parsed.preferences + parsed.style_preferences):
        fields.append(_text_field("preferences.general", preference, IntentFieldKind.SOFT, text))
    for event in parsed.fixed_events:
        fields.append(_text_field("time.fixed_events", event.model_dump(mode="json"), IntentFieldKind.HARD, text))
    return fields


def _text_field(field_path: str, value: Any, kind: IntentFieldKind, text: str) -> _CandidateField:
    return _candidate(
        field_path,
        value,
        kind=kind,
        confidence=0.8,
        source_ref=_source_ref(
            IntentSourceType.DIRECT_USER_LANGUAGE,
            field_path=field_path,
            label="Direct user language",
            source_id=f"direct_user_text:{sha256_digest(text)[:16]}",
            priority=80,
            confirmed=True,
            value=value,
            evidence_refs=[f"direct_user_text:{sha256_digest(text)[:16]}"],
        ),
        explanation="Compiled from direct user language after deterministic parsing.",
    )


def _fields_from_candidates(candidates: list[TripCandidateRecord], states: dict[str, str]) -> list[_CandidateField]:
    fields: list[_CandidateField] = []
    for candidate in candidates:
        state = states.get(candidate.id, "pending")
        if state in {"rejected", "deferred"}:
            continue
        ref = _source_ref(
            IntentSourceType.TRIP_CANDIDATE,
            field_path="poi.must_candidates",
            label=candidate.display_name,
            source_id=candidate.id,
            priority=70,
            confirmed=True,
            value=candidate.id,
            evidence_refs=[candidate.source_ref or "", *candidate.evidence_refs],
        )
        fields.append(
            _candidate(
                "poi.must_candidates",
                candidate.id,
                kind=IntentFieldKind.HARD,
                confidence=0.9 if candidate.confidence in {"high", "medium"} else 0.7,
                source_ref=ref,
                explanation="Included from reviewed TripCandidate evidence.",
            )
        )
    return fields


def _fields_from_existing_trip(snapshot: dict[str, Any]) -> list[_CandidateField]:
    current = (((snapshot.get("trip_intent") or {}).get("current_intent")) or {})
    fields: list[_CandidateField] = []
    if current.get("city"):
        fields.append(_existing_field("trip.city", current["city"], IntentFieldKind.HARD))
    if current.get("trip_days"):
        fields.append(_existing_field("trip.trip_days", current["trip_days"], IntentFieldKind.HARD))
    for preference in unique_texts(current.get("preferences") or []):
        fields.append(_existing_field("preferences.general", preference, IntentFieldKind.SOFT))
    return fields


def _fields_from_existing_intent_revision(snapshot: dict[str, Any]) -> list[_CandidateField]:
    fields: list[_CandidateField] = []
    revision_id = str(snapshot.get("id") or "unknown_intent_revision")
    for field in snapshot.get("fields") or []:
        if not isinstance(field, dict) or field.get("status") != IntentFieldStatus.SELECTED.value:
            continue
        field_path = str(field.get("field_path") or "")
        if not field_path:
            continue
        fields.append(
            _candidate(
                field_path,
                field.get("value"),
                kind=IntentFieldKind(field.get("kind") or IntentFieldKind.ASSUMPTION.value),
                confidence=min(float(field.get("confidence") or 0.6), 0.75),
                source_ref=_source_ref(
                    IntentSourceType.EXISTING_INTENT_REVISION,
                    field_path=field_path,
                    label=f"Intent revision {snapshot.get('revision_number', '?')}",
                    source_id=revision_id,
                    priority=60,
                    confirmed=bool(field.get("confirmed_by_user")),
                    value=field.get("value"),
                    evidence_refs=[f"intent_revision:{revision_id}"],
                ),
                explanation="Carried from the parent TripIntentEnvelope revision.",
            )
        )
    return fields


def _existing_field(field_path: str, value: Any, kind: IntentFieldKind) -> _CandidateField:
    return _candidate(
        field_path,
        value,
        kind=kind,
        confidence=0.65,
        source_ref=_source_ref(
            IntentSourceType.EXISTING_TRIP_STATE,
            field_path=field_path,
            label="Existing trip state",
            source_id="current_trip_revision",
            priority=50,
            confirmed=False,
            value=value,
            evidence_refs=["current_trip_revision"],
        ),
        explanation="Carried from existing saved trip state as lower-priority context.",
    )


def _select_fields(candidates: list[_CandidateField]) -> tuple[list[IntentField], list[IntentField], list[IntentConflict], list[ClarificationQuestion]]:
    selected: list[IntentField] = []
    shadowed: list[IntentField] = []
    conflicts: list[IntentConflict] = []
    clarifications: list[ClarificationQuestion] = []
    singletons = {"trip.city", "trip.trip_days", "trip.pace"}
    by_path: dict[str, list[_CandidateField]] = {}
    for item in candidates:
        by_path.setdefault(item.field_path, []).append(item)
    for field_path, items in by_path.items():
        if field_path in singletons:
            selected_item, shadowed_items, conflict = _select_singleton(field_path, items)
            selected.append(_to_field(selected_item, IntentFieldStatus.SELECTED))
            for item in shadowed_items:
                shadowed.append(_to_field(item, IntentFieldStatus.SHADOWED))
            if conflict is not None:
                conflicts.append(conflict)
        else:
            seen: set[str] = set()
            for item in sorted(items, key=lambda value: (-value.source_ref.priority, value.source_ref.ref_id)):
                key = _value_key(item.value)
                if key in seen:
                    shadowed.append(_to_field(item, IntentFieldStatus.SHADOWED))
                    continue
                seen.add(key)
                selected.append(_to_field(item, IntentFieldStatus.SELECTED))
    if not any(field.field_path == "trip.city" and field.status == IntentFieldStatus.SELECTED for field in selected):
        clarifications.append(
            ClarificationQuestion(
                question_id="clarify_trip_city",
                field_paths=["trip.city"],
                answer_field_path="trip.city",
                answer_value_type="string",
                question="Which destination city should this trip be compiled for?",
                priority=100,
                blocking=True,
                impact="planner_blocking",
                reason_code="missing_destination",
            )
        )
    if not any(field.field_path == "trip.trip_days" and field.status == IntentFieldStatus.SELECTED for field in selected):
        clarifications.append(
            ClarificationQuestion(
                question_id="clarify_trip_days",
                field_paths=["trip.trip_days"],
                answer_field_path="trip.trip_days",
                answer_value_type="integer",
                question="How many days should the trip cover?",
                priority=70,
                blocking=True,
                impact="planner_blocking",
                reason_code="missing_trip_length",
            )
        )
    return selected, shadowed, conflicts, clarifications


def _select_singleton(field_path: str, items: list[_CandidateField]) -> tuple[_CandidateField, list[_CandidateField], IntentConflict | None]:
    ordered = sorted(items, key=lambda value: (-value.source_ref.priority, value.source_ref.ref_id))
    winner = ordered[0]
    losers = [item for item in ordered[1:] if _value_key(item.value) != _value_key(winner.value)]
    conflict = None
    if losers:
        max_loser_priority = max(item.source_ref.priority for item in losers)
        requires_clarification = max_loser_priority == winner.source_ref.priority
        conflict = IntentConflict(
            conflict_id=f"conf_{sha256_digest({'field_path': field_path, 'winner': winner.value, 'losers': [item.value for item in losers]})[:16]}",
            field_path=field_path,
            severity="blocking" if requires_clarification else "non_blocking",
            winner_field_id=_field_id(winner),
            losing_field_ids=[_field_id(item) for item in losers],
            reason_code="same_priority_conflict" if requires_clarification else "higher_priority_source_selected",
            explanation=(
                "Sources with equal priority disagree; user clarification is required."
                if requires_clarification
                else "A higher-priority source overrides lower-priority intent proposals."
            ),
            requires_clarification=requires_clarification,
            source_refs=[winner.source_ref, *[item.source_ref for item in losers]],
        )
    return winner, ordered[1:], conflict


def _to_field(item: _CandidateField, status: IntentFieldStatus) -> IntentField:
    return IntentField(
        field_id=_field_id(item),
        field_path=item.field_path,
        value=item.value,
        semantic_type=item.semantic_type,
        semantic_value=item.semantic_value,
        kind=item.kind,
        confidence=item.confidence,
        source_refs=[item.source_ref],
        confirmed_by_user=item.source_ref.confirmed,
        priority=item.source_ref.priority,
        status=status,
        validation_codes=["schema_validated", "deterministically_compiled"],
        explanation=item.explanation,
    )


def _field_id(item: _CandidateField) -> str:
    return f"field_{sha256_digest({'field_path': item.field_path, 'value': item.value, 'source': item.source_ref.ref_id})[:16]}"


def _value_key(value: Any) -> str:
    return sha256_digest(value)


def _build_planner_ready(fields: list[IntentField]) -> PlannerReadyIntentPreview:
    preview = PlannerReadyIntentPreview()
    for field in fields:
        if field.status != IntentFieldStatus.SELECTED:
            continue
        if field.field_path == "trip.city":
            preview.city = str(field.value)
        elif field.field_path == "trip.trip_days":
            preview.trip_days = int(field.value)
        elif field.field_path == "trip.pace":
            preview.pace = str(field.value)
        elif field.field_path == "poi.must_candidates":
            value = str(field.value)
            if value not in preview.must_place_candidate_ids:
                preview.must_place_candidate_ids.append(value)
            label = field.source_refs[0].label
            if label not in preview.must_place_names:
                preview.must_place_names.append(label)
        elif field.field_path == "preferences.transport":
            value = str(field.value)
            if value not in preview.transport_preferences:
                preview.transport_preferences.append(value)
        elif field.field_path == "time.fixed_events":
            preview.fixed_events.append(field.value)
    return preview


def _build_typed_intent(
    fields: list[IntentField],
    clarifications: list[ClarificationQuestion],
    assumptions: list[str],
    typed_assumptions: list[IntentAssumption],
) -> TypedTripIntent:
    typed = TypedTripIntent(
        assumptions=assumptions,
        typed_assumptions=typed_assumptions,
        unresolved_questions=clarifications,
    )
    for field in fields:
        if field.status != IntentFieldStatus.SELECTED:
            continue
        value = _typed_value(field)
        if field.field_path == "trip.city":
            typed.destinations.append(value)
        elif field.field_path == "trip.trip_days":
            typed.date_policy.trip_days = value
        elif field.field_path == "time.fixed_events":
            typed.fixed_events.append(value)
        elif field.field_path == "poi.must_candidates":
            typed.poi_preferences.must_candidates.append(value)
        elif field.field_path == "trip.pace":
            typed.pace = value
        elif field.field_path == "preferences.transport":
            typed.transport_preferences.append(value)
    return typed


def _typed_value(field: IntentField) -> TypedIntentValue:
    return TypedIntentValue(
        field_path=field.field_path,
        field_id=field.field_id,
        value=field.value,
        semantic_type=field.semantic_type,
        semantic_value=field.semantic_value,
        kind=field.kind,
        confidence=field.confidence,
        confirmed_by_user=field.confirmed_by_user,
        source_refs=field.source_refs,
        validation_codes=field.validation_codes,
    )


def _build_provenance_summary(
    selected: list[IntentField],
    shadowed: list[IntentField],
) -> list[IntentProvenanceSummary]:
    fields = [*selected, *shadowed]
    paths = sorted({field.field_path for field in fields})
    summary: list[IntentProvenanceSummary] = []
    for field_path in paths:
        path_fields = [field for field in fields if field.field_path == field_path]
        refs = [ref for field in path_fields for ref in field.source_refs]
        selected_fields = [
            field.field_id
            for field in path_fields
            if field.status == IntentFieldStatus.SELECTED
        ]
        shadowed_fields = [
            field.field_id
            for field in path_fields
            if field.status == IntentFieldStatus.SHADOWED
        ]
        summary.append(
            IntentProvenanceSummary(
                field_path=field_path,
                selected_field_ids=selected_fields,
                shadowed_field_ids=shadowed_fields,
                source_types=list(dict.fromkeys(ref.source_type for ref in refs)),
                evidence_refs=unique_texts([evidence for ref in refs for evidence in ref.evidence_refs]),
                confirmed=any(field.confirmed_by_user for field in path_fields),
                max_confidence=max((field.confidence for field in path_fields), default=0),
            )
        )
    return summary


def _typed_section_names(typed: TypedTripIntent) -> list[str]:
    names: list[str] = []
    if typed.destinations:
        names.append("destinations")
    if typed.date_policy.trip_days or typed.date_policy.availability_windows:
        names.append("date_policy")
    if typed.fixed_events:
        names.append("fixed_events")
    if typed.poi_preferences.must_candidates or typed.poi_preferences.optional_candidates or typed.poi_preferences.exclusions:
        names.append("poi_preferences")
    if typed.pace:
        names.append("pace")
    if typed.transport_preferences:
        names.append("transport_preferences")
    if typed.assumptions:
        names.append("assumptions")
    if typed.unresolved_questions:
        names.append("unresolved_questions")
    return names


def _validate_selected_fields(
    fields: list[IntentField],
    preview: PlannerReadyIntentPreview,
) -> list[IntentConflict]:
    conflicts: list[IntentConflict] = []
    if preview.trip_days is None:
        return conflicts
    for field in fields:
        if field.field_path != "time.fixed_events" or field.status != IntentFieldStatus.SELECTED:
            continue
        event = field.value if isinstance(field.value, dict) else {}
        fixed_day = event.get("fixed_day")
        if fixed_day is None:
            continue
        try:
            day_number = int(fixed_day)
        except (TypeError, ValueError):
            continue
        if day_number < 1 or day_number > preview.trip_days:
            conflicts.append(
                IntentConflict(
                    conflict_id=f"conf_{sha256_digest({'field_path': field.field_path, 'field_id': field.field_id, 'fixed_day': fixed_day, 'trip_days': preview.trip_days})[:16]}",
                    field_path=field.field_path,
                    severity="blocking",
                    winner_field_id=None,
                    losing_field_ids=[field.field_id],
                    reason_code="fixed_event_outside_trip_dates",
                    explanation="A fixed event falls outside the compiled trip length and cannot enter planner safely.",
                    requires_clarification=True,
                    source_refs=field.source_refs,
                )
            )
    return conflicts


def _build_typed_assumptions(fields: list[IntentField], preview: PlannerReadyIntentPreview) -> list[IntentAssumption]:
    assumptions: list[IntentAssumption] = []
    if preview.trip_days is None:
        assumptions.append(
            IntentAssumption(
                assumption_id=f"asm_{sha256_digest({'field_path': 'trip.trip_days', 'reason': 'missing_trip_length'})[:16]}",
                field_path="trip.trip_days",
                assumption_type="missing_value",
                value=None,
                has_assumed_value=False,
                blocks_planner_ready=True,
                reason_code="missing_trip_length",
                explanation="Trip length is unresolved and must be clarified before deterministic planning.",
            )
        )
    if not preview.must_place_candidate_ids:
        assumptions.append(
            IntentAssumption(
                assumption_id=f"asm_{sha256_digest({'field_path': 'poi.must_candidates', 'reason': 'empty_reviewed_candidate_set'})[:16]}",
                field_path="poi.must_candidates",
                assumption_type="empty_reviewed_candidate_set",
                value=[],
                has_assumed_value=True,
                blocks_planner_ready=False,
                reason_code="no_reviewed_must_candidates",
                explanation="No reviewed must-visit TripCandidate has been selected yet.",
            )
        )
    for field in fields:
        if field.kind == IntentFieldKind.ASSUMPTION:
            assumptions.append(
                IntentAssumption(
                    assumption_id=f"asm_{sha256_digest({'field_id': field.field_id, 'reason': 'carried_forward_assumption'})[:16]}",
                    field_path=field.field_path,
                    assumption_type="carried_forward_assumption",
                    value=field.value,
                    has_assumed_value=True,
                    blocks_planner_ready=False,
                    reason_code="carried_forward_assumption",
                    explanation=f"{field.field_path} is carried as an assumption from {field.source_refs[0].label}.",
                    source_refs=field.source_refs,
                )
            )
    by_id: dict[str, IntentAssumption] = {}
    for assumption in assumptions:
        by_id.setdefault(assumption.assumption_id, assumption)
    return list(by_id.values())


def _build_parser_result(request: CompileTripIntentRequest, fields: list[IntentField]) -> IntentParserResult:
    input_digests: list[str] = []
    warnings: list[str] = []
    parser_name = "intent_contract_compiler"
    status: Literal["not_run", "parsed", "validated"] = "not_run"
    if request.direct_user_text and request.direct_user_text.strip():
        input_digests.append(f"direct_user_text:{sha256_digest(request.direct_user_text.strip())[:16]}")
        parser_name = "deterministic_text_fallback"
        status = "parsed"
    if request.llm_proposal is not None:
        input_digests.append(f"llm_proposal:{sha256_digest(request.llm_proposal.model_dump(mode='json'))[:16]}")
        status = "validated"
    if request.use_llm_proposal_adapter:
        warnings.append("LLM proposal adapter output was treated as untrusted input and deterministically recompiled.")
    return IntentParserResult(
        parser_name=parser_name,
        parser_version=TRIP_INTENT_COMPILER_VERSION,
        status=status,
        input_digests=input_digests,
        extracted_field_paths=sorted(
            {
                field.field_path
                for field in fields
                if any(
                    ref.source_type in {IntentSourceType.DIRECT_USER_LANGUAGE, IntentSourceType.LLM_PROPOSAL}
                    for ref in field.source_refs
                )
            }
        ),
        warnings=warnings,
    )


def _build_provenance_graph(
    *,
    envelope_id: str,
    parser_result: IntentParserResult,
    fields: list[IntentField],
    assumptions: list[IntentAssumption],
) -> IntentProvenanceGraph:
    nodes: dict[str, IntentProvenanceNode] = {
        envelope_id: IntentProvenanceNode(
            node_id=envelope_id,
            node_type=ProvenanceNodeType.ENVELOPE_REVISION,
            label="TripIntentEnvelope revision",
            authority=IntentAuthority.DETERMINISTIC_CONTEXT,
            confirmed=True,
        )
    }
    edges: list[IntentProvenanceEdge] = []
    parser_node_id = f"parser:{sha256_digest(parser_result.model_dump(mode='json'))[:16]}"
    nodes[parser_node_id] = IntentProvenanceNode(
        node_id=parser_node_id,
        node_type=ProvenanceNodeType.PARSER_RESULT,
        label=parser_result.parser_name,
        authority=IntentAuthority.DETERMINISTIC_CONTEXT,
        confirmed=parser_result.status in {"parsed", "validated"},
        digest=sha256_digest(parser_result.model_dump(mode="json")),
    )
    edges.append(
        IntentProvenanceEdge(
            from_node_id=parser_node_id,
            to_node_id=envelope_id,
            relation=ProvenanceEdgeType.PRODUCED,
        )
    )
    for field in fields:
        field_node_id = f"field:{field.field_id}"
        nodes[field_node_id] = IntentProvenanceNode(
            node_id=field_node_id,
            node_type=ProvenanceNodeType.FIELD,
            label=field.field_path,
            field_path=field.field_path,
            authority=_strongest_authority(field.source_refs),
            confirmed=field.confirmed_by_user,
            digest=sha256_digest(
                {
                    "field_path": field.field_path,
                    "semantic_type": field.semantic_type.value,
                    "semantic_value": field.semantic_value,
                    "kind": field.kind.value,
                }
            ),
        )
        edges.append(
            IntentProvenanceEdge(
                from_node_id=field_node_id,
                to_node_id=envelope_id,
                relation=ProvenanceEdgeType.SELECTED_IN
                if field.status == IntentFieldStatus.SELECTED
                else ProvenanceEdgeType.SHADOWED_IN,
            )
        )
        for ref in field.source_refs:
            source_node_id = f"source:{ref.ref_id}"
            nodes[source_node_id] = IntentProvenanceNode(
                node_id=source_node_id,
                node_type=ProvenanceNodeType.SOURCE,
                label=ref.label,
                field_path=ref.field_path,
                source_type=ref.source_type,
                source_id=ref.source_id,
                authority=ref.authority,
                confirmed=ref.confirmed,
                digest=ref.evidence_digest,
            )
            edges.append(
                IntentProvenanceEdge(
                    from_node_id=source_node_id,
                    to_node_id=field_node_id,
                    relation=ProvenanceEdgeType.SUPPORTS,
                )
            )
    for assumption in assumptions:
        assumption_node_id = f"assumption:{assumption.assumption_id}"
        nodes[assumption_node_id] = IntentProvenanceNode(
            node_id=assumption_node_id,
            node_type=ProvenanceNodeType.ASSUMPTION,
            label=assumption.reason_code,
            field_path=assumption.field_path,
            authority=IntentAuthority.DETERMINISTIC_CONTEXT,
            confirmed=False,
            digest=sha256_digest(assumption.model_dump(mode="json")),
        )
        edges.append(
            IntentProvenanceEdge(
                from_node_id=assumption_node_id,
                to_node_id=envelope_id,
                relation=ProvenanceEdgeType.CREATED_ASSUMPTION,
            )
        )
    return IntentProvenanceGraph(
        nodes=sorted(nodes.values(), key=lambda node: node.node_id),
        edges=sorted(edges, key=lambda edge: (edge.from_node_id, edge.to_node_id, edge.relation.value)),
    )


def _strongest_authority(refs: list[IntentSourceRef]) -> IntentAuthority:
    rank = {
        IntentAuthority.USER_CONFIRMED: 5,
        IntentAuthority.REVIEWED_SOURCE: 4,
        IntentAuthority.SAVED_STATE: 3,
        IntentAuthority.DETERMINISTIC_CONTEXT: 2,
        IntentAuthority.LLM_UNTRUSTED: 1,
        IntentAuthority.LEGACY_UNKNOWN: 0,
    }
    return max((ref.authority for ref in refs), key=lambda authority: rank[authority], default=IntentAuthority.LEGACY_UNKNOWN)


def _build_semantic_digest(
    *,
    selected: list[IntentField],
    conflicts: list[IntentConflict],
    assumptions: list[IntentAssumption],
    planner_ready_status: IntentPlannerReadyStatus,
) -> str:
    return sha256_digest(
        {
            "compiler_version": TRIP_INTENT_COMPILER_VERSION,
            "planner_ready_status": planner_ready_status.value,
            "selected_fields": sorted(
                [
                    {
                        "field_path": field.field_path,
                        "semantic_type": field.semantic_type.value,
                        "semantic_value": field.semantic_value,
                        "kind": field.kind.value,
                        "confirmed_by_user": field.confirmed_by_user,
                        "authority": _strongest_authority(field.source_refs).value,
                    }
                    for field in selected
                    if field.status == IntentFieldStatus.SELECTED
                ],
                key=lambda item: (
                    str(item["field_path"]),
                    str(item["semantic_type"]),
                    sha256_digest(item["semantic_value"]),
                    str(item["authority"]),
                ),
            ),
            "blocking_conflicts": sorted(
                [
                    {
                        "field_path": conflict.field_path,
                        "severity": conflict.severity,
                        "reason_code": conflict.reason_code,
                    }
                    for conflict in conflicts
                    if conflict.severity == "blocking"
                ],
                key=lambda item: (str(item["field_path"]), str(item["reason_code"])),
            ),
            "assumptions": sorted(
                [
                    {
                        "field_path": assumption.field_path,
                        "assumption_type": assumption.assumption_type,
                        "has_assumed_value": assumption.has_assumed_value,
                        "blocks_planner_ready": assumption.blocks_planner_ready,
                        "reason_code": assumption.reason_code,
                        "value": assumption.value,
                    }
                    for assumption in assumptions
                ],
                key=lambda item: (str(item["field_path"]), str(item["reason_code"])),
            ),
        }
    )


def unique_texts(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result

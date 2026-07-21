from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.nl_parser import parse_trip_text_fallback
from app.trips.access import generate_intent_revision_id
from app.trips.candidates import TripCandidateRecord
from app.trips.digests import sha256_digest


TRIP_INTENT_ENVELOPE_SCHEMA_VERSION = "1.4"
TRIP_INTENT_COMPILER_VERSION = "intent-compiler-v5"
INTENT_PRECEDENCE_VERSION = "intent-precedence-v3"
INTENT_READINESS_POLICY_VERSION = "intent-readiness-v3"
INTENT_DATE_POLICY_VERSION = "intent-date-policy-v1"


class IntentSourceType(str, Enum):
    DIRECT_USER_LANGUAGE = "direct_user_language"
    STRUCTURED_USER_OVERRIDE = "structured_user_override"
    LLM_PROPOSAL = "llm_proposal"
    TRIP_CANDIDATE = "trip_candidate"
    EXISTING_TRIP_STATE = "existing_trip_state"
    EXISTING_INTENT_REVISION = "existing_intent_revision"
    TRIP_FORM = "trip_form"
    SOURCE_ARTIFACT = "source_artifact"
    IMPORT_MENTION = "import_mention"
    IMPORT_REVIEW_DECISION = "import_review_decision"
    RESOLUTION_CANDIDATE = "resolution_candidate"
    SYSTEM_ASSUMPTION = "system_assumption"


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
    READY_WITH_ASSUMPTIONS = "ready_with_assumptions"
    READY_FOR_PLANNING = "ready_for_planning"


class IntentAuthority(str, Enum):
    USER_CONFIRMED = "user_confirmed"
    REVIEWED_SOURCE = "reviewed_source"
    REVIEW_CONFIRMED = "review_confirmed"
    SAVED_STATE = "saved_state"
    DIRECT_USER_PROPOSAL = "direct_user_proposal"
    LLM_UNTRUSTED = "llm_untrusted"
    DETERMINISTIC_CONTEXT = "deterministic_context"
    SYSTEM_ASSUMPTION = "system_assumption"
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
    BUDGET = "budget"
    TRAVELER_NEED = "traveler_need"


class ProvenanceNodeType(str, Enum):
    ENVELOPE_REVISION = "envelope_revision"
    PARSER_RESULT = "parser_result"
    SOURCE = "source"
    SOURCE_ARTIFACT = "source_artifact"
    EXTRACTED_MENTION = "extracted_mention"
    REVIEW_DECISION = "review_decision"
    TRIP_CANDIDATE = "trip_candidate"
    DOCUMENT_PAGE = "document_page"
    BOUNDING_BOX = "bounding_box"
    IMPORT_JOB = "import_job"
    RESOLUTION_CANDIDATE = "resolution_candidate"
    DIRECT_USER_SPAN = "direct_user_span"
    LLM_PROPOSAL = "llm_proposal"
    FIELD = "field"
    ASSUMPTION = "assumption"


class ProvenanceEdgeType(str, Enum):
    PRODUCED = "produced"
    SUPPORTS = "supports"
    DERIVED_FROM = "derived_from"
    MENTIONED_IN = "mentioned_in"
    REVIEWED_AS = "reviewed_as"
    RESOLVED_TO = "resolved_to"
    COMMITTED_AS = "committed_as"
    COMPILED_INTO = "compiled_into"
    ASSUMED_FROM = "assumed_from"
    RESTORED_FROM = "restored_from"
    SHADOWED_BY = "shadowed_by"
    EVIDENCES = "evidences"
    SELECTED_IN = "selected_in"
    SHADOWED_IN = "shadowed_in"
    CREATED_ASSUMPTION = "created_assumption"


class IntentDestinationValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["destination_city"] = "destination_city"
    city: str


class IntentTripDaysValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["trip_days"] = "trip_days"
    days: int = Field(..., ge=1, le=60)


class IntentPaceValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["pace"] = "pace"
    pace: Literal["relaxed", "balanced", "intensive"]


class IntentTransportPreferenceValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["transport_preference"] = "transport_preference"
    mode: str


class IntentMustCandidateValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["must_candidate"] = "must_candidate"
    candidate_id: str
    display_name: str | None = None


class IntentFixedEventValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["fixed_event"] = "fixed_event"
    name: str
    fixed_day: int | None = Field(default=None, ge=1, le=60)
    fixed_time_start: str | None = None
    fixed_time_end: str | None = None
    source_label: str | None = None


class IntentGeneralPreferenceValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["general_preference"] = "general_preference"
    preference: str


class IntentBudgetValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["budget"] = "budget"
    amount: float | None = Field(default=None, ge=0)
    currency: str | None = None
    budget_level: Literal["low", "medium", "high"] | None = None


class IntentTravelerNeedValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["traveler_need"] = "traveler_need"
    need: str
    traveler_group: str | None = None


class IntentUnknownValue(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["unknown"] = "unknown"
    raw: str | int | float | bool | dict[str, object] | list[object] | None = None


IntentFieldValue = (
    IntentDestinationValue
    | IntentTripDaysValue
    | IntentPaceValue
    | IntentTransportPreferenceValue
    | IntentMustCandidateValue
    | IntentFixedEventValue
    | IntentGeneralPreferenceValue
    | IntentBudgetValue
    | IntentTravelerNeedValue
    | IntentUnknownValue
)


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


JsonScalar = str | int | float | bool


class BoundingBox(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(..., ge=0)
    y: float = Field(..., ge=0)
    width: float = Field(..., gt=0)
    height: float = Field(..., gt=0)
    unit: Literal["normalized", "pixel"] = "normalized"


class IntentSourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_ref_id: str
    source_type: Literal[
        "direct_user_language",
        "structured_user_override",
        "trip_form",
        "source_artifact",
        "import_mention",
        "import_review_decision",
        "resolution_candidate",
        "trip_candidate",
        "existing_intent_revision",
        "llm_proposal",
        "system_assumption",
    ]
    source_id: str
    artifact_id: str | None = None
    import_job_id: str | None = None
    mention_id: str | None = None
    review_decision_id: str | None = None
    resolution_candidate_id: str | None = None
    trip_candidate_id: str | None = None
    intent_revision_id: str | None = None
    text_span_start: int | None = Field(default=None, ge=0)
    text_span_end: int | None = Field(default=None, ge=0)
    page_number: int | None = Field(default=None, ge=1)
    bounding_boxes: list[BoundingBox] = Field(default_factory=list)
    extraction_method: str | None = None
    geometry_source: str | None = None
    source_digest: str
    authority: Literal[
        "user_confirmed",
        "review_confirmed",
        "saved_state",
        "direct_user_proposal",
        "llm_untrusted",
        "system_assumption",
    ]
    confirmed: bool


class IntentFieldMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_id: str
    field_path: str
    kind: Literal["hard", "soft", "assumption"]
    confirmation_state: Literal[
        "user_confirmed",
        "review_confirmed",
        "proposed",
        "assumed",
        "conflicted",
        "superseded",
    ]
    authority: Literal[
        "user_confirmed",
        "review_confirmed",
        "saved_state",
        "direct_user_proposal",
        "llm_untrusted",
        "system_assumption",
    ]
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_refs: list[IntentSourceReference] = Field(default_factory=list)
    compiler_rule_code: str
    warning_codes: list[str] = Field(default_factory=list)


class DestinationIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: IntentFieldMetadata
    city_name: str = Field(..., min_length=1, max_length=120)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    timezone: str | None = Field(default=None, max_length=80)
    order: int = Field(..., ge=0)


class DatePolicyIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: IntentFieldMetadata
    start_date: date | None = None
    end_date: date | None = None
    trip_days: int | None = Field(default=None, ge=1, le=60)
    timezone: str = "unknown"
    original_expressions: list[str] = Field(default_factory=list)
    reference_date: date | None = None
    normalization_rule_codes: list[str] = Field(default_factory=list)


class TravelBoundaryIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: IntentFieldMetadata
    boundary_type: Literal["arrival", "departure"]
    local_datetime: datetime
    timezone: str
    flexibility_minutes: int = Field(default=0, ge=0, le=1440)
    location_candidate_id: str | None = None
    location_text: str | None = Field(default=None, max_length=240)


class AvailabilityWindowIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: IntentFieldMetadata
    date: date
    start_time: time
    end_time: time
    timezone: str
    crosses_midnight: bool = False


class FixedEventIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: IntentFieldMetadata
    event_id: str
    title: str = Field(..., min_length=1, max_length=240)
    start_at: datetime | None = None
    end_at: datetime | None = None
    timezone: str | None = None
    fixed_day: int | None = Field(default=None, ge=1, le=60)
    place_candidate_id: str | None = None
    location_text: str | None = Field(default=None, max_length=240)
    flexibility: Literal["fixed", "movable_with_confirmation"] = "fixed"


class PlacePreferenceIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: IntentFieldMetadata
    trip_candidate_id: str
    display_name: str | None = None
    preference: Literal["must", "optional", "avoid"]
    strength: int = Field(..., ge=1, le=100)


class TransportPreferenceIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: IntentFieldMetadata
    mode: Literal[
        "walk",
        "metro",
        "bus",
        "taxi",
        "ride_hailing",
        "drive",
        "bike",
        "rail",
        "flight",
        "other",
    ]
    preference: Literal["prefer", "avoid", "require"] = "prefer"
    custom_label: str | None = Field(default=None, max_length=80)


class MealPreferenceIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: IntentFieldMetadata
    preference_text: str = Field(..., min_length=1, max_length=240)
    preference: Literal["prefer", "avoid", "require"] = "prefer"


class BudgetIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: IntentFieldMetadata
    amount_minor: int | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    scope: Literal["total", "per_person", "per_day"] | None = None
    level: Literal["low", "medium", "high"] | None = None
    flexibility_percent: int = Field(default=0, ge=0, le=100)

    @model_validator(mode="after")
    def validate_budget(self) -> "BudgetIntent":
        if self.amount_minor is not None and (self.currency is None or self.scope is None):
            raise ValueError("numeric budget requires currency and scope.")
        return self


class TravelerNeedIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: IntentFieldMetadata
    need_type: Literal["mobility", "wheelchair", "child", "elderly", "dietary", "medical", "sensory", "other"]
    description: str = Field(..., min_length=1, max_length=240)
    severity: Literal["required", "preferred"] = "preferred"


class ExclusionIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: IntentFieldMetadata
    exclusion_text: str = Field(..., min_length=1, max_length=240)


class PlanningAssumption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assumption_id: str
    field_path: str
    assumed_value: JsonScalar
    value_type: Literal["integer", "string", "date", "datetime", "enum", "boolean"]
    reason_code: str
    impact: Literal["medium", "low"]
    source_refs: list[IntentSourceReference] = Field(default_factory=list)
    user_acknowledged: bool = False
    supersedes_clarification_id: str | None = None


class IntentReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["blocked", "needs_clarification", "ready_with_assumptions", "ready_for_planning"]
    planner_contract_complete: bool
    blocking_issue_codes: list[str] = Field(default_factory=list)
    unresolved_required_field_paths: list[str] = Field(default_factory=list)
    active_assumption_ids: list[str] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)


class FormalTripIntentContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "formal-trip-intent-v1"
    destinations: list[DestinationIntent] = Field(default_factory=list)
    date_policy: DatePolicyIntent | None = None
    arrival_boundary: TravelBoundaryIntent | None = None
    departure_boundary: TravelBoundaryIntent | None = None
    availability_windows: list[AvailabilityWindowIntent] = Field(default_factory=list)
    fixed_events: list[FixedEventIntent] = Field(default_factory=list)
    must_visit_places: list[PlacePreferenceIntent] = Field(default_factory=list)
    optional_places: list[PlacePreferenceIntent] = Field(default_factory=list)
    avoid_places: list[PlacePreferenceIntent] = Field(default_factory=list)
    pace: IntentFieldMetadata | None = None
    transport_preferences: list[TransportPreferenceIntent] = Field(default_factory=list)
    meal_preferences: list[MealPreferenceIntent] = Field(default_factory=list)
    budget: BudgetIntent | None = None
    traveler_needs: list[TravelerNeedIntent] = Field(default_factory=list)
    exclusions: list[ExclusionIntent] = Field(default_factory=list)
    assumptions: list[PlanningAssumption] = Field(default_factory=list)
    clarifications: list[ClarificationQuestion] = Field(default_factory=list)
    conflicts: list[IntentConflict] = Field(default_factory=list)
    readiness: IntentReadiness


class IntentField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_id: str
    field_path: str
    value: IntentFieldValue
    semantic_type: IntentValueType = IntentValueType.UNKNOWN
    semantic_value: IntentFieldValue
    kind: IntentFieldKind
    confidence: float = Field(..., ge=0, le=1)
    source_refs: list[IntentSourceRef] = Field(default_factory=list)
    confirmed_by_user: bool = False
    priority: int = Field(..., ge=0, le=100)
    status: IntentFieldStatus = IntentFieldStatus.SELECTED
    validation_codes: list[str] = Field(default_factory=list)
    explanation: str

    @model_validator(mode="before")
    @classmethod
    def coerce_domain_value(cls, data: Any) -> Any:
        if isinstance(data, dict):
            field_path = str(data.get("field_path") or "")
            data = dict(data)
            data["value"] = _domain_value_for_field(field_path, data.get("value"))
            data["semantic_value"] = _domain_value_for_field(
                field_path,
                data.get("semantic_value", data["value"]),
            )
        return data


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
    answer_value_type: Literal["string", "integer", "pace", "string_list", "fixed_event", "budget"] = "string"
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
    value: IntentFieldValue
    semantic_type: IntentValueType = IntentValueType.UNKNOWN
    semantic_value: IntentFieldValue
    kind: IntentFieldKind
    confidence: float = Field(..., ge=0, le=1)
    confirmed_by_user: bool
    source_refs: list[IntentSourceRef] = Field(default_factory=list)
    validation_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def coerce_domain_value(cls, data: Any) -> Any:
        if isinstance(data, dict):
            field_path = str(data.get("field_path") or "")
            data = dict(data)
            data["value"] = _domain_value_for_field(field_path, data.get("value"))
            data["semantic_value"] = _domain_value_for_field(
                field_path,
                data.get("semantic_value", data["value"]),
            )
        return data


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
    value: IntentFieldValue | list[IntentFieldValue] | None = None
    has_assumed_value: bool
    blocks_planner_ready: bool
    reason_code: str
    explanation: str
    source_refs: list[IntentSourceRef] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def coerce_assumption_value(cls, data: Any) -> Any:
        if isinstance(data, dict) and "value" in data:
            field_path = str(data.get("field_path") or "")
            data = dict(data)
            value = data.get("value")
            if isinstance(value, list):
                data["value"] = [_domain_value_for_field(field_path, item) for item in value]
            elif value is not None:
                data["value"] = _domain_value_for_field(field_path, value)
        return data


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
    status: Literal["success", "empty_input", "unavailable", "timeout", "invalid_output", "provider_error"]
    input_digests: list[str] = Field(default_factory=list)
    extracted_field_paths: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    model_name: str | None = None


class IntentProposalParseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "empty_input", "unavailable", "timeout", "invalid_output", "provider_error"]
    proposal: "UntrustedIntentProposal | None" = None
    parser_name: str
    parser_version: str
    model_name: str | None = None
    warning_codes: list[str] = Field(default_factory=list)


class IntentProvenanceNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    node_type: ProvenanceNodeType
    label: str
    field_path: str | None = None
    source_type: IntentSourceType | None = None
    source_id: str | None = None
    artifact_id: str | None = None
    mention_id: str | None = None
    review_decision_id: str | None = None
    candidate_id: str | None = None
    page_number: int | None = None
    bbox: dict[str, float | str] | None = None
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

    policy_version: str = INTENT_READINESS_POLICY_VERSION
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
    fixed_events: list[IntentFixedEventValue] = Field(default_factory=list)
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
        status="empty_input",
    ))
    formal_contract: FormalTripIntentContract
    typed_intent: TypedTripIntent = Field(default_factory=TypedTripIntent)
    provenance_summary: list[IntentProvenanceSummary] = Field(default_factory=list)
    provenance_graph: IntentProvenanceGraph = Field(default_factory=IntentProvenanceGraph)
    planner_ready_intent: PlannerReadyIntentPreview
    planner_ready_status: IntentPlannerReadyStatus
    readiness_policy: IntentReadinessPolicy | None = None
    validation_report: dict[str, Any]
    source_digest: str
    semantic_digest: str | None = None
    lineage_digest: str | None = None
    content_digest: str
    created_at: str

    @model_validator(mode="before")
    @classmethod
    def backfill_formal_contract(cls, data: Any) -> Any:
        if isinstance(data, dict) and "formal_contract" not in data:
            legacy = dict(data)
            fields = [IntentField.model_validate(item) for item in legacy.get("fields") or []]
            conflicts = [IntentConflict.model_validate(item) for item in legacy.get("conflicts") or []]
            clarifications = [
                ClarificationQuestion.model_validate(item)
                for item in legacy.get("clarification_queue") or []
            ]
            assumptions = [
                IntentAssumption.model_validate(item)
                for item in legacy.get("typed_assumptions") or []
            ]
            selected = [field for field in fields if field.status == IntentFieldStatus.SELECTED]
            planner_status = IntentPlannerReadyStatus(
                legacy.get("planner_ready_status") or IntentPlannerReadyStatus.NEEDS_CLARIFICATION.value
            )
            readiness = legacy.get("readiness_policy")
            readiness_policy = (
                IntentReadinessPolicy.model_validate(readiness)
                if isinstance(readiness, dict)
                else IntentReadinessPolicy(
                    status=planner_status,
                    blocking_reason_codes=[],
                    allowed_assumption_ids=[],
                )
            )
            legacy["formal_contract"] = _build_formal_contract(
                selected=selected,
                conflicts=conflicts,
                clarifications=clarifications,
                typed_assumptions=assumptions,
                planner_ready_status=planner_status,
                readiness_policy=readiness_policy,
                verified_candidate_source_refs={},
            ).model_dump(mode="json")
        return data


class IntentStructuredOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city: str | None = Field(default=None, max_length=120)
    trip_days: int | None = Field(default=None, ge=1, le=60)
    must_candidate_ids: list[str] = Field(default_factory=list, max_length=40)
    pace: Literal["relaxed", "balanced", "intensive"] | None = None
    transport_preferences: list[str] = Field(default_factory=list, max_length=20)
    fixed_events: list[IntentFixedEventValue] = Field(default_factory=list, max_length=40)
    budget: IntentBudgetValue | None = None
    traveler_needs: list[str] = Field(default_factory=list, max_length=20)

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
    fixed_events: list[IntentFixedEventValue] = Field(default_factory=list, max_length=40)
    budget: IntentBudgetValue | None = None
    traveler_needs: list[str] = Field(default_factory=list, max_length=20)
    explanation: str | None = Field(default=None, max_length=1000)


class CompileTripIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    base_trip_revision_id: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("base_trip_revision_id", "base_revision_id"),
    )
    base_intent_revision_id: str | None = Field(..., min_length=1)
    direct_user_text: str | None = Field(default=None, max_length=10000)
    candidate_ids: list[str] = Field(default_factory=list, max_length=80)
    structured_overrides: IntentStructuredOverrides | None = None
    llm_proposal: UntrustedIntentProposal | None = None
    use_llm_proposal_adapter: bool = False

    @property
    def base_revision_id(self) -> str:
        return self.base_trip_revision_id


class EditTripIntentEnvelopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    base_trip_revision_id: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("base_trip_revision_id", "base_revision_id"),
    )
    base_intent_revision_id: str = Field(..., min_length=1)
    field_updates: IntentStructuredOverrides

    @property
    def base_revision_id(self) -> str:
        return self.base_trip_revision_id


class AnswerIntentClarificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    base_trip_revision_id: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("base_trip_revision_id", "base_revision_id"),
    )
    base_intent_revision_id: str = Field(..., min_length=1)
    answer: str | int | bool | list[str] | IntentFixedEventValue | IntentBudgetValue

    @property
    def base_revision_id(self) -> str:
        return self.base_trip_revision_id


class RestoreTripIntentEnvelopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    base_trip_revision_id: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("base_trip_revision_id", "base_revision_id"),
    )
    base_intent_revision_id: str = Field(..., min_length=1)

    @property
    def base_revision_id(self) -> str:
        return self.base_trip_revision_id


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
class IntentCompileRunDraft:
    id: str
    trip_id: str
    operation: str
    base_trip_revision_id: str
    base_intent_revision_id: str | None
    parser_status: str
    parser_name: str
    parser_version: str
    model_name: str | None
    compiler_version: str
    precedence_version: str
    readiness_policy_version: str
    date_policy_version: str
    input_digest: str
    proposal_digest: str | None
    status: str
    warning_codes: list[str]
    error_code: str | None
    created_at: str


@dataclass(slots=True)
class IntentCompileRunRecord(IntentCompileRunDraft):
    result_intent_revision_id: str = ""
    semantic_digest: str = ""
    lineage_digest: str = ""


@dataclass(slots=True)
class _CandidateField:
    field_path: str
    value: IntentFieldValue
    semantic_type: IntentValueType
    semantic_value: IntentFieldValue
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
    parser_result: IntentProposalParseResult,
    existing_trip_snapshot: dict[str, Any],
    parent_intent_snapshot: dict[str, Any] | None = None,
    candidates: list[TripCandidateRecord],
    candidate_workflow_states: dict[str, str],
    verified_candidate_source_refs: dict[str, list[IntentSourceReference]] | None = None,
) -> SourceLinkedTripIntentEnvelope:
    field_candidates: list[_CandidateField] = []
    if parent_intent_snapshot is not None:
        field_candidates.extend(_fields_from_existing_intent_revision(parent_intent_snapshot))
    field_candidates.extend(_fields_from_existing_trip(existing_trip_snapshot))
    if request.direct_user_text and request.direct_user_text.strip():
        field_candidates.extend(_fields_from_user_text(request.direct_user_text.strip()))
    field_candidates.extend(_fields_from_candidates(candidates, candidate_workflow_states))
    proposal = parser_result.proposal or request.llm_proposal
    if proposal is not None:
        field_candidates.extend(_fields_from_payload(proposal.model_dump(mode="json"), IntentSourceType.LLM_PROPOSAL))
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
    envelope_parser_result = _build_parser_result(request, fields, parser_result)
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
    formal_contract = _build_formal_contract(
        selected=selected,
        conflicts=conflicts,
        clarifications=clarifications,
        typed_assumptions=typed_assumptions,
        planner_ready_status=status,
        readiness_policy=readiness_policy,
        verified_candidate_source_refs=verified_candidate_source_refs or {},
    )
    provenance_graph = _build_provenance_graph(
        envelope_id=f"intent_revision:{trip_id}:{next_revision_number}",
        parser_result=envelope_parser_result,
        formal_contract=formal_contract,
    )
    validation_report = {
        "schema_version": TRIP_INTENT_ENVELOPE_SCHEMA_VERSION,
        "compiler_version": TRIP_INTENT_COMPILER_VERSION,
        "precedence_version": INTENT_PRECEDENCE_VERSION,
        "readiness_policy_version": INTENT_READINESS_POLICY_VERSION,
        "date_policy_version": INTENT_DATE_POLICY_VERSION,
        "llm_proposal_validated": proposal is not None,
        "parser_status": envelope_parser_result.status,
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
        "formal_contract_authority": True,
        "formal_contract_schema_version": formal_contract.schema_version,
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
            "parser": parser_result.model_dump(mode="json", exclude={"proposal"}),
            "candidate_ids": [candidate.id for candidate in candidates],
            "base_revision_id": base_revision_id,
        }
    )
    semantic_digest = _build_semantic_digest(
        selected=selected,
        conflicts=conflicts,
        assumptions=typed_assumptions,
        formal_contract=formal_contract,
    )
    lineage_digest_value = _build_intent_lineage_digest(
        base_revision_id=base_revision_id,
        parent_intent_revision_id=parent_intent_revision_id,
        semantic_digest=semantic_digest,
        formal_contract=formal_contract,
        parser_result=envelope_parser_result,
        operation="draft_compile",
        parent_lineage_digest=None,
        restore_source_revision_id=None,
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
        "parser_result": envelope_parser_result.model_dump(mode="json"),
        "formal_contract": formal_contract.model_dump(mode="json"),
        "typed_intent": typed_intent.model_dump(mode="json"),
        "provenance_summary": [item.model_dump(mode="json") for item in provenance_summary],
        "provenance_graph": provenance_graph.model_dump(mode="json"),
        "planner_ready_intent": planner_ready.model_dump(mode="json"),
        "planner_ready_status": status.value,
        "readiness_policy": readiness_policy.model_dump(mode="json"),
        "validation_report": validation_report,
        "source_digest": source_digest,
        "semantic_digest": semantic_digest,
        "lineage_digest": lineage_digest_value,
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
        parser_result=envelope_parser_result,
        formal_contract=formal_contract,
        typed_intent=typed_intent,
        provenance_summary=provenance_summary,
        provenance_graph=provenance_graph,
        planner_ready_intent=planner_ready,
        planner_ready_status=status,
        readiness_policy=readiness_policy,
        validation_report=validation_report,
        source_digest=source_digest,
        semantic_digest=semantic_digest,
        lineage_digest=lineage_digest_value,
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


def _domain_value_for_field(field_path: str, value: Any) -> IntentFieldValue:
    if isinstance(
        value,
        (
            IntentDestinationValue,
            IntentTripDaysValue,
            IntentPaceValue,
            IntentTransportPreferenceValue,
            IntentMustCandidateValue,
            IntentFixedEventValue,
            IntentGeneralPreferenceValue,
            IntentBudgetValue,
            IntentTravelerNeedValue,
            IntentUnknownValue,
        ),
    ):
        return value
    if isinstance(value, dict) and isinstance(value.get("type"), str):
        typed = _domain_value_from_typed_dict(value)
        if typed is not None:
            return typed
    if isinstance(value, dict) and "event" in value and field_path == "time.fixed_events":
        value = value["event"]
    if field_path == "trip.city":
        city = str(_dict_get(value, "city", value)).strip()
        return IntentDestinationValue(city=city)
    if field_path == "trip.trip_days":
        return IntentTripDaysValue(days=int(_dict_get(value, "days", value)))
    if field_path == "trip.pace":
        pace = str(_dict_get(value, "pace", value)).strip()
        if pace not in {"relaxed", "balanced", "intensive"}:
            return IntentUnknownValue(raw={"pace": pace})
        return IntentPaceValue(pace=pace)  # type: ignore[arg-type]
    if field_path == "preferences.transport":
        return IntentTransportPreferenceValue(mode=str(_dict_get(value, "mode", value)).strip())
    if field_path == "poi.must_candidates":
        candidate_id = str(_dict_get(value, "candidate_id", value)).strip()
        display_name = _dict_get(value, "display_name", None)
        return IntentMustCandidateValue(
            candidate_id=candidate_id,
            display_name=str(display_name).strip() if display_name else None,
        )
    if field_path == "time.fixed_events":
        event = value if isinstance(value, dict) else {"name": str(value)}
        name = str(event.get("name") or event.get("title") or event.get("value") or "Fixed event").strip()
        fixed_day = event.get("fixed_day")
        return IntentFixedEventValue(
            name=name,
            fixed_day=int(fixed_day) if fixed_day not in (None, "") else None,
            fixed_time_start=str(event.get("fixed_time_start")).strip() if event.get("fixed_time_start") else None,
            fixed_time_end=str(event.get("fixed_time_end")).strip() if event.get("fixed_time_end") else None,
            source_label=str(event.get("source_label")).strip() if event.get("source_label") else None,
        )
    if field_path == "preferences.general":
        return IntentGeneralPreferenceValue(preference=str(_dict_get(value, "preference", value)).strip())
    if field_path == "budget":
        if isinstance(value, dict):
            return IntentBudgetValue.model_validate(value if value.get("type") else {"type": "budget", **value})
        return IntentBudgetValue(budget_level=str(value).strip())  # type: ignore[arg-type]
    if field_path == "travelers.needs":
        return IntentTravelerNeedValue(need=str(_dict_get(value, "need", value)).strip())
    return IntentUnknownValue(raw=value if isinstance(value, (str, int, float, bool, dict, list)) or value is None else str(value))


def _domain_value_from_typed_dict(value: dict[str, Any]) -> IntentFieldValue | None:
    type_name = value.get("type")
    model_by_type = {
        "destination_city": IntentDestinationValue,
        "trip_days": IntentTripDaysValue,
        "pace": IntentPaceValue,
        "transport_preference": IntentTransportPreferenceValue,
        "must_candidate": IntentMustCandidateValue,
        "fixed_event": IntentFixedEventValue,
        "general_preference": IntentGeneralPreferenceValue,
        "budget": IntentBudgetValue,
        "traveler_need": IntentTravelerNeedValue,
        "unknown": IntentUnknownValue,
    }
    model = model_by_type.get(type_name)
    return model.model_validate(value) if model else None


def _dict_get(value: Any, key: str, default: Any) -> Any:
    return value.get(key, default) if isinstance(value, dict) else default


def _domain_value_dump(value: IntentFieldValue) -> dict[str, Any]:
    return value.model_dump(mode="json", exclude_none=True)


def _domain_raw_value(value: IntentFieldValue) -> Any:
    if isinstance(value, IntentDestinationValue):
        return value.city
    if isinstance(value, IntentTripDaysValue):
        return value.days
    if isinstance(value, IntentPaceValue):
        return value.pace
    if isinstance(value, IntentTransportPreferenceValue):
        return value.mode
    if isinstance(value, IntentMustCandidateValue):
        return value.candidate_id
    if isinstance(value, IntentFixedEventValue):
        return value.model_dump(mode="json", exclude_none=True, exclude={"type"})
    if isinstance(value, IntentGeneralPreferenceValue):
        return value.preference
    if isinstance(value, IntentBudgetValue):
        return value.model_dump(mode="json", exclude_none=True, exclude={"type"})
    if isinstance(value, IntentTravelerNeedValue):
        return value.need
    return value.raw


def _candidate(
    field_path: str,
    value: Any,
    *,
    kind: IntentFieldKind,
    confidence: float,
    source_ref: IntentSourceRef,
    explanation: str,
) -> _CandidateField:
    domain_value = _domain_value_for_field(field_path, value)
    return _CandidateField(
        field_path=field_path,
        value=domain_value,
        semantic_type=_semantic_type_for_field(field_path),
        semantic_value=domain_value,
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
        "budget": IntentValueType.BUDGET,
        "travelers.needs": IntentValueType.TRAVELER_NEED,
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
    budget = payload.get("budget")
    if isinstance(budget, dict) and any(value not in (None, "", []) for value in budget.values()):
        field_path = "budget"
        fields.append(
            _candidate(
                field_path,
                budget,
                kind=IntentFieldKind.SOFT,
                confidence=1.0 if confirmed else 0.5,
                source_ref=_source_ref(
                    source_type,
                    field_path=field_path,
                    label=label,
                    source_id=f"{source_type.value}:budget",
                    priority=priority,
                    confirmed=confirmed,
                    value=budget,
                ),
                explanation=f"{label} supplied a budget preference.",
            )
        )
    for value in unique_texts(payload.get("traveler_needs") or []):
        field_path = "travelers.needs"
        fields.append(
            _candidate(
                field_path,
                value,
                kind=IntentFieldKind.HARD if confirmed else IntentFieldKind.ASSUMPTION,
                confidence=1.0 if confirmed else 0.5,
                source_ref=_source_ref(
                    source_type,
                    field_path=field_path,
                    label=label,
                    source_id=f"{source_type.value}:traveler_need",
                    priority=priority,
                    confirmed=confirmed,
                    value=value,
                ),
                explanation=f"{label} supplied a traveler need.",
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
                {"candidate_id": candidate.id, "display_name": candidate.display_name},
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
                field.get("semantic_value", field.get("value")),
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
            conflict_id=f"conf_{sha256_digest({'field_path': field_path, 'winner': _domain_value_dump(winner.value), 'losers': [_domain_value_dump(item.value) for item in losers]})[:16]}",
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
    return f"field_{sha256_digest({'field_path': item.field_path, 'value': _domain_value_dump(item.value), 'source': item.source_ref.ref_id})[:16]}"


def _value_key(value: IntentFieldValue) -> str:
    return sha256_digest(_domain_value_dump(value))


def _build_planner_ready(fields: list[IntentField]) -> PlannerReadyIntentPreview:
    preview = PlannerReadyIntentPreview()
    for field in fields:
        if field.status != IntentFieldStatus.SELECTED:
            continue
        if field.field_path == "trip.city":
            preview.city = str(_domain_raw_value(field.value))
        elif field.field_path == "trip.trip_days":
            preview.trip_days = int(_domain_raw_value(field.value))
        elif field.field_path == "trip.pace":
            preview.pace = str(_domain_raw_value(field.value))
        elif field.field_path == "poi.must_candidates":
            value = str(_domain_raw_value(field.value))
            if value not in preview.must_place_candidate_ids:
                preview.must_place_candidate_ids.append(value)
            label = field.source_refs[0].label
            if label not in preview.must_place_names:
                preview.must_place_names.append(label)
        elif field.field_path == "preferences.transport":
            value = str(_domain_raw_value(field.value))
            if value not in preview.transport_preferences:
                preview.transport_preferences.append(value)
        elif field.field_path == "time.fixed_events":
            if isinstance(field.value, IntentFixedEventValue):
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
        elif field.field_path == "budget":
            typed.budget = value
        elif field.field_path == "travelers.needs":
            typed.travelers.append(value)
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
    if typed.budget:
        names.append("budget")
    if typed.travelers:
        names.append("travelers")
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
        fixed_day = field.value.fixed_day if isinstance(field.value, IntentFixedEventValue) else None
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


def _build_parser_result(
    request: CompileTripIntentRequest,
    fields: list[IntentField],
    parse_result: IntentProposalParseResult,
) -> IntentParserResult:
    input_digests: list[str] = []
    if request.direct_user_text and request.direct_user_text.strip():
        input_digests.append(f"direct_user_text:{sha256_digest(request.direct_user_text.strip())[:16]}")
    proposal = parse_result.proposal or request.llm_proposal
    if proposal is not None:
        input_digests.append(f"llm_proposal:{sha256_digest(proposal.model_dump(mode='json'))[:16]}")
    return IntentParserResult(
        parser_name=parse_result.parser_name,
        parser_version=parse_result.parser_version,
        status=parse_result.status,
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
        warnings=unique_texts(parse_result.warning_codes),
        model_name=parse_result.model_name,
    )


def _build_formal_contract(
    *,
    selected: list[IntentField],
    conflicts: list[IntentConflict],
    clarifications: list[ClarificationQuestion],
    typed_assumptions: list[IntentAssumption],
    planner_ready_status: IntentPlannerReadyStatus,
    readiness_policy: IntentReadinessPolicy,
    verified_candidate_source_refs: dict[str, list[IntentSourceReference]],
) -> FormalTripIntentContract:
    destinations: list[DestinationIntent] = []
    fixed_events: list[FixedEventIntent] = []
    must_places: list[PlacePreferenceIntent] = []
    transport_preferences: list[TransportPreferenceIntent] = []
    traveler_needs: list[TravelerNeedIntent] = []
    date_policy: DatePolicyIntent | None = None
    budget: BudgetIntent | None = None
    pace: IntentFieldMetadata | None = None

    for field in selected:
        metadata = _formal_metadata_for_field(field, verified_candidate_source_refs)
        if field.field_path == "trip.city" and isinstance(field.value, IntentDestinationValue):
            destinations.append(
                DestinationIntent(
                    metadata=metadata,
                    city_name=field.value.city,
                    country_code=None,
                    timezone=None,
                    order=len(destinations),
                )
            )
        elif field.field_path == "trip.trip_days" and isinstance(field.value, IntentTripDaysValue):
            date_policy = DatePolicyIntent(
                metadata=metadata,
                trip_days=field.value.days,
                timezone="unknown",
                normalization_rule_codes=[INTENT_DATE_POLICY_VERSION, "duration_known_calendar_unanchored"],
            )
        elif field.field_path == "time.fixed_events" and isinstance(field.value, IntentFixedEventValue):
            fixed_events.append(
                FixedEventIntent(
                    metadata=metadata,
                    event_id=field.field_id,
                    title=field.value.name,
                    fixed_day=field.value.fixed_day,
                    location_text=field.value.source_label,
                    flexibility="fixed",
                )
            )
        elif field.field_path == "poi.must_candidates" and isinstance(field.value, IntentMustCandidateValue):
            must_places.append(
                PlacePreferenceIntent(
                    metadata=metadata,
                    trip_candidate_id=field.value.candidate_id,
                    display_name=field.value.display_name,
                    preference="must",
                    strength=100,
                )
            )
        elif field.field_path == "trip.pace":
            pace = metadata
        elif field.field_path == "preferences.transport" and isinstance(field.value, IntentTransportPreferenceValue):
            mode, custom_label = _normalize_transport_mode(field.value.mode)
            transport_preferences.append(
                TransportPreferenceIntent(
                    metadata=metadata,
                    mode=mode,
                    preference="prefer",
                    custom_label=custom_label,
                )
            )
        elif field.field_path == "budget" and isinstance(field.value, IntentBudgetValue):
            amount_minor = int(field.value.amount * 100) if field.value.amount is not None else None
            budget = BudgetIntent(
                metadata=metadata,
                amount_minor=amount_minor if amount_minor and amount_minor > 0 else None,
                currency=field.value.currency.upper() if field.value.currency else None,
                scope="total" if amount_minor else None,
                level=field.value.budget_level,
                flexibility_percent=0,
            )
        elif field.field_path == "travelers.needs" and isinstance(field.value, IntentTravelerNeedValue):
            need_type = _classify_traveler_need(field.value.need)
            traveler_needs.append(
                TravelerNeedIntent(
                    metadata=metadata,
                    need_type=need_type,
                    description=field.value.need,
                    severity="required" if field.kind == IntentFieldKind.HARD else "preferred",
                )
            )

    formal_assumptions = [
        _formal_assumption(item, verified_candidate_source_refs)
        for item in typed_assumptions
        if item.has_assumed_value and item.value not in (None, [])
    ]
    active_assumption_ids = [item.assumption_id for item in formal_assumptions]
    unresolved_required_paths = unique_texts(
        [
            *[path for question in clarifications if question.blocking for path in question.field_paths],
            *[
                assumption.field_path
                for assumption in typed_assumptions
                if assumption.blocks_planner_ready and not assumption.has_assumed_value
            ],
        ]
    )
    blocking_codes = unique_texts(
        [
            *readiness_policy.blocking_reason_codes,
            *[conflict.reason_code for conflict in conflicts if conflict.severity == "blocking"],
        ]
    )
    readiness_status: Literal["blocked", "needs_clarification", "ready_with_assumptions", "ready_for_planning"]
    if any(conflict.severity == "blocking" for conflict in conflicts):
        readiness_status = "blocked"
    elif unresolved_required_paths:
        readiness_status = "needs_clarification"
    elif active_assumption_ids:
        readiness_status = "ready_with_assumptions"
    elif planner_ready_status in {IntentPlannerReadyStatus.READY, IntentPlannerReadyStatus.READY_FOR_PLANNING}:
        readiness_status = "ready_for_planning"
    else:
        readiness_status = "needs_clarification"

    return FormalTripIntentContract(
        destinations=destinations,
        date_policy=date_policy,
        fixed_events=fixed_events,
        must_visit_places=must_places,
        pace=pace,
        transport_preferences=transport_preferences,
        budget=budget,
        traveler_needs=traveler_needs,
        assumptions=formal_assumptions,
        clarifications=clarifications,
        conflicts=conflicts,
        readiness=IntentReadiness(
            status=readiness_status,
            planner_contract_complete=(
                readiness_status in {"ready_with_assumptions", "ready_for_planning"}
                and bool(destinations)
                and date_policy is not None
                and date_policy.trip_days is not None
            ),
            blocking_issue_codes=blocking_codes,
            unresolved_required_field_paths=unresolved_required_paths,
            active_assumption_ids=active_assumption_ids,
            warning_codes=unique_texts(readiness_policy.blocking_reason_codes),
        ),
    )


def _formal_metadata_for_field(
    field: IntentField,
    verified_candidate_source_refs: dict[str, list[IntentSourceReference]],
) -> IntentFieldMetadata:
    source_refs: list[IntentSourceReference] = []
    for ref in field.source_refs:
        if ref.source_type == IntentSourceType.TRIP_CANDIDATE and ref.source_id in verified_candidate_source_refs:
            source_refs.extend(verified_candidate_source_refs[ref.source_id])
        else:
            source_refs.append(_structured_source_ref_from_legacy(ref))
    authority = _formal_authority(_strongest_authority(field.source_refs))
    confirmation_state: Literal[
        "user_confirmed",
        "review_confirmed",
        "proposed",
        "assumed",
        "conflicted",
        "superseded",
    ]
    if field.status == IntentFieldStatus.SHADOWED:
        confirmation_state = "superseded"
    elif field.kind == IntentFieldKind.ASSUMPTION:
        confirmation_state = "assumed"
    elif authority == "review_confirmed":
        confirmation_state = "review_confirmed"
    elif authority == "user_confirmed":
        confirmation_state = "user_confirmed"
    elif authority == "llm_untrusted":
        confirmation_state = "proposed"
    else:
        confirmation_state = "proposed"
    return IntentFieldMetadata(
        field_id=field.field_id,
        field_path=field.field_path,
        kind=field.kind.value,
        confirmation_state=confirmation_state,
        authority=authority,
        confidence=field.confidence,
        source_refs=source_refs,
        compiler_rule_code="deterministic_precedence_selected"
        if field.status == IntentFieldStatus.SELECTED
        else "deterministic_precedence_shadowed",
        warning_codes=list(field.validation_codes),
    )


def _structured_source_ref_from_legacy(ref: IntentSourceRef) -> IntentSourceReference:
    source_id = ref.source_id or ref.ref_id
    source_type = _formal_source_type(ref.source_type)
    return IntentSourceReference(
        source_ref_id=ref.ref_id,
        source_type=source_type,
        source_id=source_id,
        trip_candidate_id=source_id if source_type == "trip_candidate" else None,
        intent_revision_id=source_id if source_type == "existing_intent_revision" else None,
        source_digest=ref.evidence_digest,
        authority=_formal_authority(ref.authority),
        confirmed=ref.confirmed,
    )


def _formal_source_type(source_type: IntentSourceType) -> Literal[
    "direct_user_language",
    "structured_user_override",
    "trip_form",
    "source_artifact",
    "import_mention",
    "import_review_decision",
    "resolution_candidate",
    "trip_candidate",
    "existing_intent_revision",
    "llm_proposal",
    "system_assumption",
]:
    if source_type == IntentSourceType.EXISTING_TRIP_STATE:
        return "trip_form"
    if source_type == IntentSourceType.EXISTING_INTENT_REVISION:
        return "existing_intent_revision"
    if source_type == IntentSourceType.TRIP_CANDIDATE:
        return "trip_candidate"
    if source_type == IntentSourceType.STRUCTURED_USER_OVERRIDE:
        return "structured_user_override"
    if source_type == IntentSourceType.LLM_PROPOSAL:
        return "llm_proposal"
    if source_type == IntentSourceType.DIRECT_USER_LANGUAGE:
        return "direct_user_language"
    return "system_assumption"


def _formal_authority(authority: IntentAuthority) -> Literal[
    "user_confirmed",
    "review_confirmed",
    "saved_state",
    "direct_user_proposal",
    "llm_untrusted",
    "system_assumption",
]:
    if authority in {IntentAuthority.USER_CONFIRMED, IntentAuthority.DIRECT_USER_PROPOSAL}:
        return "user_confirmed"
    if authority in {IntentAuthority.REVIEWED_SOURCE, IntentAuthority.REVIEW_CONFIRMED}:
        return "review_confirmed"
    if authority == IntentAuthority.SAVED_STATE:
        return "saved_state"
    if authority == IntentAuthority.LLM_UNTRUSTED:
        return "llm_untrusted"
    return "system_assumption"


def _formal_assumption(
    assumption: IntentAssumption,
    verified_candidate_source_refs: dict[str, list[IntentSourceReference]],
) -> PlanningAssumption:
    value = assumption.value[0] if isinstance(assumption.value, list) and assumption.value else assumption.value
    raw = _domain_raw_value(value) if isinstance(value, BaseModel) else value
    if isinstance(raw, bool):
        value_type: Literal["integer", "string", "date", "datetime", "enum", "boolean"] = "boolean"
    elif isinstance(raw, int):
        value_type = "integer"
    else:
        value_type = "string"
    refs = [
        _structured_source_ref_from_legacy(ref)
        for ref in assumption.source_refs
    ]
    return PlanningAssumption(
        assumption_id=assumption.assumption_id,
        field_path=assumption.field_path,
        assumed_value=raw if isinstance(raw, (str, int, float, bool)) else str(raw),
        value_type=value_type,
        reason_code=assumption.reason_code,
        impact="low" if not assumption.blocks_planner_ready else "medium",
        source_refs=refs,
        user_acknowledged=False,
        supersedes_clarification_id=None,
    )


def _normalize_transport_mode(
    value: str,
) -> tuple[Literal["walk", "metro", "bus", "taxi", "ride_hailing", "drive", "bike", "rail", "flight", "other"], str | None]:
    normalized = value.strip().casefold().replace("-", "_").replace(" ", "_")
    aliases = {
        "walking": "walk",
        "subway": "metro",
        "underground": "metro",
        "cab": "taxi",
        "rideshare": "ride_hailing",
        "car": "drive",
        "bicycle": "bike",
        "train": "rail",
        "plane": "flight",
    }
    mode = aliases.get(normalized, normalized)
    allowed = {"walk", "metro", "bus", "taxi", "ride_hailing", "drive", "bike", "rail", "flight"}
    if mode in allowed:
        return mode, None  # type: ignore[return-value]
    return "other", value.strip()[:80] or None


def _classify_traveler_need(
    value: str,
) -> Literal["mobility", "wheelchair", "child", "elderly", "dietary", "medical", "sensory", "other"]:
    lowered = value.casefold()
    if "wheelchair" in lowered or "轮椅" in value:
        return "wheelchair"
    if "child" in lowered or "儿童" in value or "孩子" in value:
        return "child"
    if "elder" in lowered or "老人" in value:
        return "elderly"
    if "diet" in lowered or "素食" in value or "过敏" in value:
        return "dietary"
    if "medical" in lowered or "药" in value:
        return "medical"
    if "sensory" in lowered:
        return "sensory"
    if "mobility" in lowered or "行动" in value:
        return "mobility"
    return "other"


def _build_provenance_graph(
    *,
    envelope_id: str,
    parser_result: IntentParserResult,
    formal_contract: FormalTripIntentContract,
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
        confirmed=parser_result.status == "success",
        digest=sha256_digest(parser_result.model_dump(mode="json")),
    )
    edges.append(
        IntentProvenanceEdge(
            from_node_id=parser_node_id,
            to_node_id=envelope_id,
            relation=ProvenanceEdgeType.PRODUCED,
        )
    )
    for metadata, semantic_payload in _formal_metadata_items(formal_contract):
        field_node_id = f"field:{metadata.field_id}"
        nodes[field_node_id] = _provenance_node_for_metadata(metadata, semantic_payload)
        edges.append(
            IntentProvenanceEdge(
                from_node_id=field_node_id,
                to_node_id=envelope_id,
                relation=ProvenanceEdgeType.COMPILED_INTO,
            )
        )
        for ref in metadata.source_refs:
            source_node_id = _source_node_id(ref)
            for node in _provenance_nodes_for_source_ref(ref):
                nodes[node.node_id] = node
            edges.append(
                IntentProvenanceEdge(
                    from_node_id=source_node_id,
                    to_node_id=field_node_id,
                    relation=ProvenanceEdgeType.SUPPORTS,
                )
            )
            edges.extend(_provenance_edges_for_source_ref(ref))
    for assumption in formal_contract.assumptions:
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
                relation=ProvenanceEdgeType.ASSUMED_FROM,
            )
        )
    return IntentProvenanceGraph(
        nodes=sorted(nodes.values(), key=lambda node: node.node_id),
        edges=sorted(edges, key=lambda edge: (edge.from_node_id, edge.to_node_id, edge.relation.value)),
    )


def _formal_metadata_items(
    contract: FormalTripIntentContract,
) -> list[tuple[IntentFieldMetadata, dict[str, str | int | bool | None]]]:
    items: list[tuple[IntentFieldMetadata, dict[str, str | int | bool | None]]] = []
    for destination in contract.destinations:
        items.append((destination.metadata, {"city_name": destination.city_name, "order": destination.order}))
    if contract.date_policy is not None:
        items.append((contract.date_policy.metadata, {"trip_days": contract.date_policy.trip_days}))
    for event in contract.fixed_events:
        items.append((event.metadata, {"title": event.title, "fixed_day": event.fixed_day}))
    for place in [*contract.must_visit_places, *contract.optional_places, *contract.avoid_places]:
        items.append((place.metadata, {"trip_candidate_id": place.trip_candidate_id, "preference": place.preference}))
    if contract.pace is not None:
        items.append((contract.pace, {"pace": "selected"}))
    for transport in contract.transport_preferences:
        items.append((transport.metadata, {"mode": transport.mode, "preference": transport.preference}))
    if contract.budget is not None:
        items.append((contract.budget.metadata, {"amount_minor": contract.budget.amount_minor, "level": contract.budget.level}))
    for need in contract.traveler_needs:
        items.append((need.metadata, {"need_type": need.need_type, "severity": need.severity}))
    return items


def _provenance_node_for_metadata(
    metadata: IntentFieldMetadata,
    semantic_payload: dict[str, str | int | bool | None],
) -> IntentProvenanceNode:
    return IntentProvenanceNode(
        node_id=f"field:{metadata.field_id}",
        node_type=ProvenanceNodeType.FIELD,
        label=metadata.field_path,
        field_path=metadata.field_path,
        authority=_legacy_authority(metadata.authority),
        confirmed=metadata.confirmation_state in {"user_confirmed", "review_confirmed"},
        digest=sha256_digest(
            {
                "field_path": metadata.field_path,
                "kind": metadata.kind,
                "confirmation_state": metadata.confirmation_state,
                "authority": metadata.authority,
                "semantic_payload": semantic_payload,
            }
        ),
    )


def _provenance_nodes_for_source_ref(ref: IntentSourceReference) -> list[IntentProvenanceNode]:
    source_node = IntentProvenanceNode(
        node_id=_source_node_id(ref),
        node_type=_node_type_for_source_ref(ref),
        label=_display_safe_source_label(ref),
        source_type=IntentSourceType(ref.source_type)
        if ref.source_type in {item.value for item in IntentSourceType}
        else IntentSourceType.SYSTEM_ASSUMPTION,
        source_id=ref.source_id,
        artifact_id=ref.artifact_id,
        mention_id=ref.mention_id,
        review_decision_id=ref.review_decision_id,
        candidate_id=ref.trip_candidate_id,
        page_number=ref.page_number,
        authority=_legacy_authority(ref.authority),
        confirmed=ref.confirmed,
        digest=ref.source_digest,
    )
    nodes = [source_node]
    if ref.artifact_id and _source_node_id(ref) != f"source_artifact:{ref.artifact_id}":
        nodes.append(
            IntentProvenanceNode(
                node_id=f"source_artifact:{ref.artifact_id}",
                node_type=ProvenanceNodeType.SOURCE_ARTIFACT,
                label=f"SourceArtifact {ref.artifact_id}",
                source_id=ref.artifact_id,
                artifact_id=ref.artifact_id,
                authority=_legacy_authority(ref.authority),
                confirmed=ref.confirmed,
                digest=sha256_digest({"artifact_id": ref.artifact_id, "source_digest": ref.source_digest}),
            )
        )
    if ref.import_job_id:
        nodes.append(
            IntentProvenanceNode(
                node_id=f"import_job:{ref.import_job_id}",
                node_type=ProvenanceNodeType.IMPORT_JOB,
                label=f"ImportJob {ref.import_job_id}",
                source_id=ref.import_job_id,
                artifact_id=ref.artifact_id,
                authority=_legacy_authority(ref.authority),
                confirmed=ref.confirmed,
                digest=sha256_digest({"import_job_id": ref.import_job_id, "source_digest": ref.source_digest}),
            )
        )
    if ref.page_number is not None:
        nodes.append(
            IntentProvenanceNode(
                node_id=f"document_page:{ref.artifact_id or ref.source_id}:{ref.page_number}",
                node_type=ProvenanceNodeType.DOCUMENT_PAGE,
                label=f"Document page {ref.page_number}",
                source_id=ref.source_id,
                artifact_id=ref.artifact_id,
                page_number=ref.page_number,
                authority=_legacy_authority(ref.authority),
                confirmed=ref.confirmed,
                digest=sha256_digest({"page_number": ref.page_number, "source_digest": ref.source_digest}),
            )
        )
    for index, box in enumerate(ref.bounding_boxes):
        nodes.append(
            IntentProvenanceNode(
                node_id=f"bbox:{ref.source_ref_id}:{index}",
                node_type=ProvenanceNodeType.BOUNDING_BOX,
                label="Bounding box evidence",
                source_id=ref.source_id,
                artifact_id=ref.artifact_id,
                mention_id=ref.mention_id,
                page_number=ref.page_number,
                bbox=box.model_dump(mode="json"),
                authority=_legacy_authority(ref.authority),
                confirmed=ref.confirmed,
                digest=sha256_digest({"bbox": box.model_dump(mode="json"), "source_digest": ref.source_digest}),
            )
        )
    return nodes


def _provenance_edges_for_source_ref(ref: IntentSourceReference) -> list[IntentProvenanceEdge]:
    edges: list[IntentProvenanceEdge] = []
    source_node_id = _source_node_id(ref)
    if ref.trip_candidate_id and source_node_id != f"trip_candidate:{ref.trip_candidate_id}":
        edges.append(IntentProvenanceEdge(from_node_id=source_node_id, to_node_id=f"trip_candidate:{ref.trip_candidate_id}", relation=ProvenanceEdgeType.COMMITTED_AS))
    if ref.resolution_candidate_id:
        edges.append(IntentProvenanceEdge(from_node_id=f"resolution_candidate:{ref.resolution_candidate_id}", to_node_id=source_node_id, relation=ProvenanceEdgeType.RESOLVED_TO))
    if ref.review_decision_id:
        edges.append(IntentProvenanceEdge(from_node_id=f"review_decision:{ref.review_decision_id}", to_node_id=source_node_id, relation=ProvenanceEdgeType.REVIEWED_AS))
    if ref.mention_id:
        target = f"review_decision:{ref.review_decision_id}" if ref.review_decision_id else source_node_id
        edges.append(IntentProvenanceEdge(from_node_id=f"extracted_mention:{ref.mention_id}", to_node_id=target, relation=ProvenanceEdgeType.MENTIONED_IN))
    if ref.import_job_id:
        edges.append(IntentProvenanceEdge(from_node_id=f"import_job:{ref.import_job_id}", to_node_id=f"extracted_mention:{ref.mention_id}" if ref.mention_id else source_node_id, relation=ProvenanceEdgeType.DERIVED_FROM))
    if ref.artifact_id:
        edges.append(IntentProvenanceEdge(from_node_id=f"source_artifact:{ref.artifact_id}", to_node_id=f"import_job:{ref.import_job_id}" if ref.import_job_id else source_node_id, relation=ProvenanceEdgeType.DERIVED_FROM))
    if ref.page_number is not None:
        edges.append(IntentProvenanceEdge(from_node_id=f"document_page:{ref.artifact_id or ref.source_id}:{ref.page_number}", to_node_id=f"extracted_mention:{ref.mention_id}" if ref.mention_id else source_node_id, relation=ProvenanceEdgeType.EVIDENCES))
    for index, _box in enumerate(ref.bounding_boxes):
        edges.append(IntentProvenanceEdge(from_node_id=f"bbox:{ref.source_ref_id}:{index}", to_node_id=f"document_page:{ref.artifact_id or ref.source_id}:{ref.page_number}" if ref.page_number is not None else source_node_id, relation=ProvenanceEdgeType.EVIDENCES))
    return edges


def _source_node_id(ref: IntentSourceReference) -> str:
    if ref.source_type == "trip_candidate" and ref.trip_candidate_id:
        return f"trip_candidate:{ref.trip_candidate_id}"
    if ref.source_type == "import_review_decision" and ref.review_decision_id:
        return f"review_decision:{ref.review_decision_id}"
    if ref.source_type == "import_mention" and ref.mention_id:
        return f"extracted_mention:{ref.mention_id}"
    if ref.source_type == "source_artifact" and ref.artifact_id:
        return f"source_artifact:{ref.artifact_id}"
    if ref.source_type == "resolution_candidate" and ref.resolution_candidate_id:
        return f"resolution_candidate:{ref.resolution_candidate_id}"
    if ref.source_type == "direct_user_language":
        return f"direct_user_span:{ref.source_ref_id}"
    if ref.source_type == "llm_proposal":
        return f"llm_proposal:{ref.source_ref_id}"
    return f"source:{ref.source_ref_id}"


def _node_type_for_source_ref(ref: IntentSourceReference) -> ProvenanceNodeType:
    return {
        "trip_candidate": ProvenanceNodeType.TRIP_CANDIDATE,
        "import_review_decision": ProvenanceNodeType.REVIEW_DECISION,
        "import_mention": ProvenanceNodeType.EXTRACTED_MENTION,
        "source_artifact": ProvenanceNodeType.SOURCE_ARTIFACT,
        "resolution_candidate": ProvenanceNodeType.RESOLUTION_CANDIDATE,
        "direct_user_language": ProvenanceNodeType.DIRECT_USER_SPAN,
        "llm_proposal": ProvenanceNodeType.LLM_PROPOSAL,
    }.get(ref.source_type, ProvenanceNodeType.SOURCE)


def _display_safe_source_label(ref: IntentSourceReference) -> str:
    return f"{ref.source_type}:{ref.source_id}"


def _legacy_authority(
    authority: str,
) -> IntentAuthority:
    mapping = {
        "user_confirmed": IntentAuthority.USER_CONFIRMED,
        "review_confirmed": IntentAuthority.REVIEW_CONFIRMED,
        "saved_state": IntentAuthority.SAVED_STATE,
        "direct_user_proposal": IntentAuthority.DIRECT_USER_PROPOSAL,
        "llm_untrusted": IntentAuthority.LLM_UNTRUSTED,
        "system_assumption": IntentAuthority.SYSTEM_ASSUMPTION,
    }
    return mapping.get(authority, IntentAuthority.LEGACY_UNKNOWN)


def _strongest_authority(refs: list[IntentSourceRef]) -> IntentAuthority:
    rank = {
        IntentAuthority.USER_CONFIRMED: 5,
        IntentAuthority.REVIEWED_SOURCE: 4,
        IntentAuthority.REVIEW_CONFIRMED: 4,
        IntentAuthority.SAVED_STATE: 3,
        IntentAuthority.DETERMINISTIC_CONTEXT: 2,
        IntentAuthority.DIRECT_USER_PROPOSAL: 2,
        IntentAuthority.SYSTEM_ASSUMPTION: 2,
        IntentAuthority.LLM_UNTRUSTED: 1,
        IntentAuthority.LEGACY_UNKNOWN: 0,
    }
    return max((ref.authority for ref in refs), key=lambda authority: rank[authority], default=IntentAuthority.LEGACY_UNKNOWN)


def _build_semantic_digest(
    *,
    selected: list[IntentField],
    conflicts: list[IntentConflict],
    assumptions: list[IntentAssumption],
    formal_contract: FormalTripIntentContract,
) -> str:
    return sha256_digest(
        {
            "semantic_digest_schema": "intent-semantic-v2",
            "readiness_status": formal_contract.readiness.status,
            "selected_fields": sorted(
                [
                    {
                        "field_path": field.field_path,
                        "semantic_type": field.semantic_type.value,
                        "semantic_value": _domain_value_dump(field.semantic_value),
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
                        "value": _assumption_value_digest_payload(assumption.value),
                    }
                    for assumption in assumptions
                ],
                key=lambda item: (str(item["field_path"]), str(item["reason_code"])),
            ),
            "formal_contract": _semantic_formal_contract_payload(formal_contract),
        }
    )


def _build_intent_lineage_digest(
    *,
    base_revision_id: str,
    parent_intent_revision_id: str | None,
    semantic_digest: str,
    formal_contract: FormalTripIntentContract,
    parser_result: IntentParserResult,
    operation: str,
    parent_lineage_digest: str | None,
    restore_source_revision_id: str | None,
) -> str:
    return sha256_digest(
        {
            "lineage_digest_schema": "intent-lineage-v2",
            "semantic_digest": semantic_digest,
            "base_trip_revision_id": base_revision_id,
            "parent_intent_revision_id": parent_intent_revision_id,
            "parent_lineage_digest": parent_lineage_digest,
            "structured_source_refs": _formal_source_digest_payload(formal_contract),
            "parser": parser_result.model_dump(mode="json"),
            "compiler_version": TRIP_INTENT_COMPILER_VERSION,
            "precedence_version": INTENT_PRECEDENCE_VERSION,
            "readiness_policy_version": INTENT_READINESS_POLICY_VERSION,
            "date_policy_version": INTENT_DATE_POLICY_VERSION,
            "operation": operation,
            "restore_source_revision_id": restore_source_revision_id,
        }
    )


def finalize_intent_envelope_for_revision(
    envelope: SourceLinkedTripIntentEnvelope,
    *,
    revision_id: str,
    revision_number: int,
    base_trip_revision_id: str,
    parent_intent_revision_id: str | None,
    parent_lineage_digest: str | None,
    operation: str,
    restore_source_revision_id: str | None,
    created_at: str,
) -> SourceLinkedTripIntentEnvelope:
    semantic_digest = _build_semantic_digest(
        selected=[field for field in envelope.fields if field.status == IntentFieldStatus.SELECTED],
        conflicts=envelope.conflicts,
        assumptions=envelope.typed_assumptions,
        formal_contract=envelope.formal_contract,
    )
    lineage_digest_value = _build_intent_lineage_digest(
        base_revision_id=base_trip_revision_id,
        parent_intent_revision_id=parent_intent_revision_id,
        semantic_digest=semantic_digest,
        formal_contract=envelope.formal_contract,
        parser_result=envelope.parser_result,
        operation=operation,
        parent_lineage_digest=parent_lineage_digest,
        restore_source_revision_id=restore_source_revision_id,
    )
    finalized = envelope.model_copy(
        update={
            "id": revision_id,
            "revision_number": revision_number,
            "base_trip_revision_id": base_trip_revision_id,
            "parent_intent_revision_id": parent_intent_revision_id,
            "semantic_digest": semantic_digest,
            "lineage_digest": lineage_digest_value,
            "created_at": created_at,
        },
        deep=True,
    )
    finalized.provenance_graph = _build_provenance_graph(
        envelope_id=f"intent_revision:{revision_id}",
        parser_result=finalized.parser_result,
        formal_contract=finalized.formal_contract,
    )
    finalized.validation_report.update(
        {
            "semantic_digest_schema": "intent-semantic-v2",
            "lineage_digest_schema": "intent-lineage-v2",
            "transaction_owned_revision_number": True,
            "idempotency_replay_precedes_stale_check": True,
        }
    )
    finalized.content_digest = sha256_digest(
        finalized.model_dump(mode="json", exclude={"content_digest"})
    )
    return finalized


def _semantic_formal_contract_payload(contract: FormalTripIntentContract) -> dict[str, Any]:
    return {
        "destinations": [
            {"city_name": item.city_name, "order": item.order, "kind": item.metadata.kind, "confirmation_state": item.metadata.confirmation_state}
            for item in contract.destinations
        ],
        "date_policy": contract.date_policy.model_dump(
            mode="json",
            exclude={"metadata": {"source_refs"}},
            exclude_none=True,
        )
        if contract.date_policy
        else None,
        "fixed_events": [
            item.model_dump(mode="json", exclude={"metadata": {"source_refs"}}, exclude_none=True)
            for item in contract.fixed_events
        ],
        "must_visit_places": [
            item.model_dump(mode="json", exclude={"metadata": {"source_refs"}}, exclude_none=True)
            for item in contract.must_visit_places
        ],
        "transport_preferences": [
            item.model_dump(mode="json", exclude={"metadata": {"source_refs"}}, exclude_none=True)
            for item in contract.transport_preferences
        ],
        "budget": contract.budget.model_dump(mode="json", exclude={"metadata": {"source_refs"}}, exclude_none=True)
        if contract.budget
        else None,
        "traveler_needs": [
            item.model_dump(mode="json", exclude={"metadata": {"source_refs"}}, exclude_none=True)
            for item in contract.traveler_needs
        ],
        "assumptions": [item.model_dump(mode="json", exclude={"source_refs"}) for item in contract.assumptions],
        "clarifications": [
            {"question_id": item.question_id, "reason_code": item.reason_code, "field_paths": item.field_paths, "blocking": item.blocking}
            for item in contract.clarifications
        ],
        "conflicts": [
            {"field_path": item.field_path, "severity": item.severity, "reason_code": item.reason_code}
            for item in contract.conflicts
        ],
        "readiness": contract.readiness.model_dump(mode="json"),
    }


def _formal_source_digest_payload(contract: FormalTripIntentContract) -> list[dict[str, Any]]:
    refs: list[IntentSourceReference] = []
    for metadata, _semantic_payload in _formal_metadata_items(contract):
        refs.extend(metadata.source_refs)
    for assumption in contract.assumptions:
        refs.extend(assumption.source_refs)
    return sorted(
        [
            {
                "source_type": ref.source_type,
                "source_id": ref.source_id,
                "source_digest": ref.source_digest,
                "authority": ref.authority,
                "confirmed": ref.confirmed,
            }
            for ref in refs
        ],
        key=lambda item: (
            str(item["source_type"]),
            str(item["source_id"]),
            str(item["source_digest"]),
            str(item["authority"]),
        ),
    )


def _assumption_value_digest_payload(
    value: IntentFieldValue | list[IntentFieldValue] | None,
) -> Any:
    if isinstance(value, list):
        return [_domain_value_dump(item) for item in value]
    if value is None:
        return None
    return _domain_value_dump(value)


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

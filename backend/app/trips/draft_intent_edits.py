from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .intent_contracts import IntentFixedEventValue, IntentStructuredOverrides, SourceLinkedTripIntentEnvelope


class _Operation(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UpdateDestinationOperation(_Operation):
    operation: Literal["update_destination"]
    city: str = Field(..., min_length=1, max_length=120)
    timezone: str | None = Field(default=None, min_length=1, max_length=80)


class UpdateDatePolicyOperation(_Operation):
    operation: Literal["update_date_policy"]
    start_date: date | None = None
    end_date: date | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=80)
    reference_date: date | None = None

    @model_validator(mode="after")
    def validates_date_range(self) -> "UpdateDatePolicyOperation":
        if self.start_date is None and self.end_date is None and self.timezone is None and self.reference_date is None:
            raise ValueError("empty_date_policy_update")
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_after_end")
        return self


class UpdateTripDaysOperation(_Operation):
    operation: Literal["update_trip_days"]
    trip_days: int = Field(..., ge=1, le=60)


class UpdatePaceOperation(_Operation):
    operation: Literal["update_pace"]
    pace: Literal["relaxed", "balanced", "intensive"]


class FixedEventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=240)
    fixed_day: int | None = Field(default=None, ge=1, le=60)
    start_at: datetime | None = None
    end_at: datetime | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=80)
    place_candidate_id: str | None = Field(default=None, max_length=120)
    location_text: str | None = Field(default=None, max_length=240)
    flexibility: Literal["fixed", "movable_with_confirmation"] = "fixed"

    @model_validator(mode="after")
    def validates_interval(self) -> "FixedEventInput":
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValueError("fixed_event_end_before_start")
        if (self.start_at or self.end_at) and not self.timezone:
            raise ValueError("fixed_event_timezone_required")
        return self


class AddFixedEventOperation(_Operation):
    operation: Literal["add_fixed_event"]
    event: FixedEventInput


class UpdateFixedEventOperation(_Operation):
    operation: Literal["update_fixed_event"]
    fixed_event_id: str = Field(..., min_length=1, max_length=120)
    event: FixedEventInput


class RemoveFixedEventOperation(_Operation):
    operation: Literal["remove_fixed_event"]
    fixed_event_id: str = Field(..., min_length=1, max_length=120)


PlacePolicy = Literal["must", "optional", "avoid"]


class AddPlacePolicyOperation(_Operation):
    operation: Literal["add_must_place", "add_optional_place", "add_avoid_place"]
    candidate_id: str = Field(..., min_length=1, max_length=120)

    @property
    def policy(self) -> PlacePolicy:
        return {"add_must_place": "must", "add_optional_place": "optional", "add_avoid_place": "avoid"}[self.operation]


class MovePlacePolicyOperation(_Operation):
    operation: Literal["move_place_policy"]
    candidate_id: str = Field(..., min_length=1, max_length=120)
    from_policy: PlacePolicy
    to_policy: PlacePolicy

    @model_validator(mode="after")
    def validates_policies(self) -> "MovePlacePolicyOperation":
        if self.from_policy == self.to_policy:
            raise ValueError("place_policy_move_no_effect")
        return self


class RemovePlaceOperation(_Operation):
    operation: Literal["remove_place"]
    candidate_id: str = Field(..., min_length=1, max_length=120)
    policy: PlacePolicy


class ConfirmPlaceIdentityOperation(_Operation):
    """Confirm one bounded Amap choice from the current immutable Draft revision."""

    operation: Literal["confirm_place_identity"]
    place_stable_id: str = Field(..., min_length=1, max_length=160)
    provider_place_id: str = Field(..., min_length=1, max_length=160)


DraftIntentEditOperation = Annotated[
    UpdateDestinationOperation
    | UpdateDatePolicyOperation
    | UpdateTripDaysOperation
    | UpdatePaceOperation
    | AddFixedEventOperation
    | UpdateFixedEventOperation
    | RemoveFixedEventOperation
    | AddPlacePolicyOperation
    | MovePlacePolicyOperation
    | RemovePlaceOperation
    | ConfirmPlaceIdentityOperation,
    Field(discriminator="operation"),
]


class DraftIntentEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_intent_revision_id: str = Field(..., min_length=1, max_length=120)
    base_draft_version: int = Field(..., ge=0)
    operations: list[DraftIntentEditOperation] = Field(..., min_length=1, max_length=20)
    # Only the clarification endpoint sets this. It becomes immutable audit metadata
    # on the resulting revision rather than a second mutation path.
    clarification_resolution_id: str | None = Field(default=None, min_length=1, max_length=180)


class _ClarificationAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DestinationClarificationAnswer(_ClarificationAnswer):
    answer_type: Literal["destination"]
    city: str = Field(..., min_length=1, max_length=160)
    timezone: str | None = Field(default=None, max_length=80)


class TripDaysClarificationAnswer(_ClarificationAnswer):
    answer_type: Literal["trip_days"]
    trip_days: int = Field(..., ge=1, le=60)


class DateRangeClarificationAnswer(_ClarificationAnswer):
    answer_type: Literal["date_range"]
    start_date: date
    end_date: date
    timezone: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def validates_range(self) -> "DateRangeClarificationAnswer":
        if self.end_date < self.start_date:
            raise ValueError("date_range_invalid")
        return self


class DatePolicyChoiceClarificationAnswer(_ClarificationAnswer):
    answer_type: Literal["date_policy_choice"]
    policy: Literal["trip_days", "date_range"]
    trip_days: int | None = Field(default=None, ge=1, le=60)
    start_date: date | None = None
    end_date: date | None = None
    timezone: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def validates_choice(self) -> "DatePolicyChoiceClarificationAnswer":
        if self.policy == "trip_days" and self.trip_days is not None:
            return self
        if self.policy == "date_range" and self.start_date and self.end_date and self.end_date >= self.start_date:
            return self
        raise ValueError("date_policy_choice_invalid")


DraftClarificationAnswer = Annotated[
    DestinationClarificationAnswer
    | TripDaysClarificationAnswer
    | DateRangeClarificationAnswer
    | DatePolicyChoiceClarificationAnswer,
    Field(discriminator="answer_type"),
]


class DraftClarificationResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_intent_revision_id: str = Field(..., min_length=1, max_length=120)
    base_draft_version: int = Field(..., ge=0)
    answer: DraftClarificationAnswer


def clarification_answer_to_operation(
    answer: DraftClarificationAnswer,
) -> DraftIntentEditOperation:
    """Translate a typed answer into the one authoritative Draft edit command."""

    if isinstance(answer, DestinationClarificationAnswer):
        return UpdateDestinationOperation(operation="update_destination", city=answer.city, timezone=answer.timezone)
    if isinstance(answer, TripDaysClarificationAnswer):
        return UpdateTripDaysOperation(operation="update_trip_days", trip_days=answer.trip_days)
    if isinstance(answer, DateRangeClarificationAnswer):
        return UpdateDatePolicyOperation(
            operation="update_date_policy",
            start_date=answer.start_date,
            end_date=answer.end_date,
            timezone=answer.timezone,
        )
    if answer.policy == "trip_days":
        return UpdateTripDaysOperation(operation="update_trip_days", trip_days=answer.trip_days or 1)
    return UpdateDatePolicyOperation(
        operation="update_date_policy",
        start_date=answer.start_date,
        end_date=answer.end_date,
        timezone=answer.timezone,
    )


class DraftIntentEditValidationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def apply_operations_to_overrides(
    envelope: SourceLinkedTripIntentEnvelope,
    operations: list[DraftIntentEditOperation],
) -> IntentStructuredOverrides:
    """Apply only typed user edits to a copy of the current formal contract."""

    formal = envelope.formal_contract
    date_policy = formal.date_policy
    city = formal.destinations[0].city_name if formal.destinations else None
    timezone = date_policy.timezone if date_policy and date_policy.timezone != "unknown" else None
    fixed_events = [
        IntentFixedEventValue(
            name=item.title,
            fixed_day=item.fixed_day,
            fixed_time_start=item.fixed_time_start,
            fixed_time_end=item.fixed_time_end,
            event_id=item.event_id,
            start_at=item.start_at,
            end_at=item.end_at,
            timezone=item.timezone,
            place_candidate_id=item.place_candidate_id,
            location_text=item.location_text,
            flexibility=item.flexibility,
        )
        for item in formal.fixed_events
    ]
    policies: dict[PlacePolicy, list[str]] = {
        "must": [item.trip_candidate_id for item in formal.must_visit_places],
        "optional": [item.trip_candidate_id for item in formal.optional_places],
        "avoid": [item.trip_candidate_id for item in formal.avoid_places],
    }
    trip_days = date_policy.trip_days if date_policy else None
    start_date = date_policy.start_date if date_policy else None
    end_date = date_policy.end_date if date_policy else None
    reference_date = date_policy.reference_date if date_policy else None
    pace = formal.pace.value if formal.pace else None

    for operation in operations:
        if isinstance(operation, UpdateDestinationOperation):
            city, timezone = operation.city.strip(), operation.timezone or timezone
        elif isinstance(operation, UpdateDatePolicyOperation):
            start_date = operation.start_date if operation.start_date is not None else start_date
            end_date = operation.end_date if operation.end_date is not None else end_date
            timezone = operation.timezone or timezone
            reference_date = operation.reference_date if operation.reference_date is not None else reference_date
            if operation.start_date is not None and operation.end_date is not None:
                # A user-selected date range authoritatively determines its inclusive
                # trip length; retaining an older day count would manufacture a conflict.
                trip_days = (operation.end_date - operation.start_date).days + 1
        elif isinstance(operation, UpdateTripDaysOperation):
            trip_days = operation.trip_days
        elif isinstance(operation, UpdatePaceOperation):
            pace = operation.pace
        elif isinstance(operation, AddFixedEventOperation):
            fixed_events.append(_event_value(operation.event, event_id=f"draft_fixed_event_{uuid4().hex}"))
        elif isinstance(operation, UpdateFixedEventOperation):
            index = next((index for index, item in enumerate(fixed_events) if item.event_id == operation.fixed_event_id), None)
            if index is None:
                raise DraftIntentEditValidationError("fixed_event_not_found")
            fixed_events[index] = _event_value(operation.event, event_id=operation.fixed_event_id)
        elif isinstance(operation, RemoveFixedEventOperation):
            original_count = len(fixed_events)
            fixed_events = [item for item in fixed_events if item.event_id != operation.fixed_event_id]
            if len(fixed_events) == original_count:
                raise DraftIntentEditValidationError("fixed_event_not_found")
        elif isinstance(operation, AddPlacePolicyOperation):
            _remove_candidate_from_policies(policies, operation.candidate_id)
            policies[operation.policy].append(operation.candidate_id)
        elif isinstance(operation, MovePlacePolicyOperation):
            if operation.candidate_id not in policies[operation.from_policy]:
                raise DraftIntentEditValidationError("place_policy_conflict")
            _remove_candidate_from_policies(policies, operation.candidate_id)
            policies[operation.to_policy].append(operation.candidate_id)
        elif isinstance(operation, RemovePlaceOperation):
            if operation.candidate_id not in policies[operation.policy]:
                raise DraftIntentEditValidationError("place_policy_conflict")
            policies[operation.policy].remove(operation.candidate_id)
        elif isinstance(operation, ConfirmPlaceIdentityOperation):
            # The service re-reads this provider choice and adds it to the next
            # immutable envelope. It must not be expressed as a generic override.
            continue

    _validate_final_state(start_date, end_date, trip_days, fixed_events)
    return IntentStructuredOverrides(
        city=city,
        trip_days=trip_days,
        start_date=start_date,
        end_date=end_date,
        timezone=timezone,
        reference_date=reference_date,
        pace=pace,
        fixed_events=fixed_events,
        must_candidate_ids=policies["must"],
        optional_candidate_ids=policies["optional"],
        avoid_candidate_ids=policies["avoid"],
    )


def _event_value(event: FixedEventInput, *, event_id: str) -> IntentFixedEventValue:
    return IntentFixedEventValue(
        name=event.title,
        event_id=event_id,
        fixed_day=event.fixed_day,
        start_at=event.start_at,
        end_at=event.end_at,
        timezone=event.timezone,
        place_candidate_id=event.place_candidate_id,
        location_text=event.location_text,
        flexibility=event.flexibility,
    )


def _remove_candidate_from_policies(policies: dict[PlacePolicy, list[str]], candidate_id: str) -> None:
    for values in policies.values():
        while candidate_id in values:
            values.remove(candidate_id)


def _validate_final_state(
    start_date: date | None,
    end_date: date | None,
    trip_days: int | None,
    fixed_events: list[IntentFixedEventValue],
) -> None:
    if start_date and end_date and start_date > end_date:
        raise DraftIntentEditValidationError("invalid_intent_edit")
    if start_date and end_date and trip_days and (end_date - start_date).days + 1 != trip_days:
        raise DraftIntentEditValidationError("invalid_intent_edit")
    for event in fixed_events:
        if trip_days and event.fixed_day and event.fixed_day > trip_days:
            raise DraftIntentEditValidationError("fixed_event_outside_trip")
        if start_date and end_date and event.start_at and not (start_date <= event.start_at.date() <= end_date):
            raise DraftIntentEditValidationError("fixed_event_outside_trip")
    for left_index, left in enumerate(fixed_events):
        if left.start_at is None or left.end_at is None:
            continue
        for right in fixed_events[left_index + 1:]:
            if right.start_at is not None and right.end_at is not None and left.start_at < right.end_at and right.start_at < left.end_at:
                raise DraftIntentEditValidationError("fixed_event_conflict")

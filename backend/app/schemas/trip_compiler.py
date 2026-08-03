from __future__ import annotations

from datetime import time
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .itinerary import TravelMode


TripOwnership = Literal["user_fixed", "user_must", "user_optional", "system_suggested"]
TripPace = Literal["relaxed", "balanced", "intensive"]


class SourceFragment(BaseModel):
    """A user-visible, stable reference to the language that supplied a field."""

    model_config = ConfigDict(extra="forbid")

    stable_id: str
    text: str
    source_type: Literal["direct_user_text"] = "direct_user_text"


class TripCompilerPlace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stable_id: str
    name: str = Field(min_length=1, max_length=180)
    ownership: TripOwnership
    confidence: float = Field(ge=0, le=1)
    source_fragment_ids: list[str] = Field(default_factory=list)


class TripCompilerFixedEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stable_id: str
    name: str = Field(min_length=1, max_length=180)
    day: int | None = Field(default=None, ge=1, le=60)
    start_time: str | None = None
    end_time: str | None = None
    fixed_reason: str
    confidence: float = Field(ge=0, le=1)
    source_fragment_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_time_range(self) -> "TripCompilerFixedEvent":
        if (self.start_time is None) != (self.end_time is None):
            raise ValueError("Fixed events require both start_time and end_time.")
        if self.start_time and self.end_time and time.fromisoformat(self.start_time) >= time.fromisoformat(self.end_time):
            raise ValueError("Fixed event start_time must be earlier than end_time.")
        return self


class TripCompilerPreference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stable_id: str
    value: str = Field(min_length=1, max_length=180)
    confidence: float = Field(ge=0, le=1)
    source_fragment_ids: list[str] = Field(default_factory=list)


class TripCompilerConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stable_id: str
    value: str = Field(min_length=1, max_length=240)
    kind: Literal["availability", "arrival", "departure", "avoid"]
    hard: bool = True
    source_fragment_ids: list[str] = Field(default_factory=list)


class TripCompilerUnresolvedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stable_id: str
    field: str
    question: str
    blocking: bool
    source_fragment_ids: list[str] = Field(default_factory=list)


class TravelIntent(BaseModel):
    """A UI contract compiled from untrusted language before deterministic planning.

    This is intentionally an API view, not a second persistence model: confirmed
    values are mapped into the established ItineraryRequest and TripRevision flow.
    """

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1"] = "1"
    destination: str | None = None
    date_window: dict[str, str | None] = Field(default_factory=dict)
    trip_days: int | None = Field(default=None, ge=1, le=3)
    pace: TripPace = "balanced"
    must_visit_places: list[TripCompilerPlace] = Field(default_factory=list)
    optional_places: list[TripCompilerPlace] = Field(default_factory=list)
    fixed_events: list[TripCompilerFixedEvent] = Field(default_factory=list)
    preferences: list[TripCompilerPreference] = Field(default_factory=list)
    constraints: list[TripCompilerConstraint] = Field(default_factory=list)
    avoid_items: list[TripCompilerConstraint] = Field(default_factory=list)
    unresolved_items: list[TripCompilerUnresolvedItem] = Field(default_factory=list)
    source_fragments: list[SourceFragment] = Field(default_factory=list)
    travel_mode: TravelMode | None = None

    @model_validator(mode="after")
    def validate_v1_place_limit(self) -> "TravelIntent":
        if len(self.must_visit_places) + len(self.optional_places) > 8:
            raise ValueError("AI Trip Compiler V1 supports at most eight user places.")
        return self

    @property
    def has_blocking_unresolved_items(self) -> bool:
        return any(item.blocking for item in self.unresolved_items)


class TripCompilerCompileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=10000)


class TripCompilerCompileResponse(BaseModel):
    intent: TravelIntent
    status: Literal["ready", "needs_confirmation", "hard_conflict"]
    conflicts: list[str] = Field(default_factory=list)


class TripCompilerPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: TravelIntent


def stable_compiler_id(kind: str, value: str, index: int = 0) -> str:
    digest = sha256(f"{kind}:{index}:{value}".encode("utf-8")).hexdigest()[:16]
    return f"{kind}_{digest}"

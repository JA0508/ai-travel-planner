from pydantic import BaseModel, Field, PrivateAttr

from .availability import AvailabilityWindow


class ParseTripTextRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Free-form trip planning text.")


class ParsedFixedEvent(BaseModel):
    name: str
    fixed_day: int | None = Field(default=None, ge=1)
    fixed_time_start: str | None = None
    fixed_time_end: str | None = None
    category: str | None = None


class PlaceDisambiguationResolution(BaseModel):
    input_name: str
    resolved_name: str
    poi_type: str
    city: str | None = None
    confidence: str
    source: str
    reason: str
    candidate_names: list[str] = Field(default_factory=list)


class IntentDisambiguationSummary(BaseModel):
    city_hint: str | None = None
    resolved_city: str | None = None
    city_source: str = "parser"
    place_resolutions: list[PlaceDisambiguationResolution] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ParsedTripIntentResponse(BaseModel):
    city: str | None = None
    trip_days: int | None = Field(default=None, ge=1)
    hotel: str | None = None
    arrival_anchor: str | None = None
    departure_anchor: str | None = None
    availability_windows: list[AvailabilityWindow] = Field(default_factory=list)
    scenic_spots: list[str] = Field(default_factory=list)
    restaurants: list[str] = Field(default_factory=list)
    fixed_events: list[ParsedFixedEvent] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    style_preferences: list[str] = Field(default_factory=list)
    style_preference_sources: dict[str, str] = Field(default_factory=dict)
    disambiguation_summary: IntentDisambiguationSummary | None = None
    _style_preference_evidence: dict[str, str] = PrivateAttr(default_factory=dict)

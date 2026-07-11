from pydantic import BaseModel, Field


class AvailabilityWindow(BaseModel):
    day: int | None = Field(default=None, ge=1)
    label: str | None = None
    available_start: str | None = None
    available_end: str | None = None

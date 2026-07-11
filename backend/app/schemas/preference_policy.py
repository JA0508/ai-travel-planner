from pydantic import BaseModel


class PlannerPreferencePolicy(BaseModel):
    walking_tolerance: str = "normal"
    dining_priority: str = "normal"
    scenic_priority: str = "normal"
    pace: str = "balanced"

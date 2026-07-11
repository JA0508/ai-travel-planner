from fastapi import APIRouter, status

from app.schemas.intent import ParseTripTextRequest, ParsedTripIntentResponse
from app.schemas.planning_state import PlanningInputState
from app.services.intent_disambiguation import disambiguate_trip_intent
from app.services.nl_parser import parse_trip_text
from app.services.planning_state_transformer import build_planning_input_state

router = APIRouter()


@router.post(
    "/parse-trip-intent",
    response_model=ParsedTripIntentResponse,
    status_code=status.HTTP_200_OK,
)
def parse_trip_intent(payload: ParseTripTextRequest) -> ParsedTripIntentResponse:
    """
    Parse free-form trip text into a structured intent schema.

    This endpoint is parse-only. It does not schedule an itinerary.
    """
    parsed_intent = parse_trip_text(payload.text)
    return disambiguate_trip_intent(parsed_intent, raw_text=payload.text)


@router.post(
    "/parse-planning-state",
    response_model=PlanningInputState,
    status_code=status.HTTP_200_OK,
)
def parse_planning_state(payload: ParseTripTextRequest) -> PlanningInputState:
    """
    Parse free-form trip text into a normalized planning input state.

    This endpoint is parse-and-normalize only. It does not schedule an itinerary.
    """
    parsed_intent = disambiguate_trip_intent(
        parse_trip_text(payload.text),
        raw_text=payload.text,
    )
    return build_planning_input_state(parsed_intent)

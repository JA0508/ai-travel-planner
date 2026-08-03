from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, Response, status

from app.api.routes.trips import set_trip_capability_cookie, validate_write_origin
from app.schemas.trip_compiler import TripCompilerCompileRequest, TripCompilerCompileResponse, TripCompilerPlanRequest
from app.services.trip_compiler import build_itinerary_request, compile_travel_intent
from app.trips.dependencies import get_trip_persistence_service
from app.trips.schemas import TripPlanRequest, TripPlanResponse

router = APIRouter(prefix="/trip-compiler", tags=["trip-compiler"])


@router.post("/intents/compile", response_model=TripCompilerCompileResponse)
def compile_intent(payload: TripCompilerCompileRequest) -> TripCompilerCompileResponse:
    return compile_travel_intent(payload.text)


@router.post("/trips", response_model=TripPlanResponse, status_code=status.HTTP_201_CREATED)
def plan_confirmed_intent(
    payload: TripCompilerPlanRequest,
    request: Request,
    response: Response,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> TripPlanResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    if not x_idempotency_key:
        raise HTTPException(status_code=400, detail="X-Idempotency-Key is required.")
    try:
        itinerary_request = build_itinerary_request(payload.intent)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    result = get_trip_persistence_service().create_persisted_plan(
        TripPlanRequest(itinerary_request=itinerary_request),
    )
    set_trip_capability_cookie(response, result.response.trip.id, result.capability)
    return result.response

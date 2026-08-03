from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.routes.trips import set_trip_capability_cookie, validate_write_origin
from app.schemas.plan_candidates import PlanCandidateRequest, PlanCandidateResponse, SelectPlanCandidateRequest
from app.schemas.trip_compiler import TripCompilerCompileRequest, TripCompilerCompileResponse, TripCompilerPlanRequest
from app.services.constraint_planning import generate_candidates, intent_digest, itinerary_request_for_strategy
from app.services.plan_candidate_store import CandidateProposalError, get_plan_candidate_store
from app.services.trip_compiler import build_itinerary_request, compile_travel_intent
from app.trips.dependencies import get_trip_persistence_service
from app.trips.schemas import TripPlanRequest, TripPlanResponse

router = APIRouter(prefix="/trip-compiler", tags=["trip-compiler"])


@router.post("/intents/compile", response_model=TripCompilerCompileResponse)
def compile_intent(payload: TripCompilerCompileRequest) -> TripCompilerCompileResponse:
    return compile_travel_intent(payload.text)


@router.post("/plan-candidates", response_model=PlanCandidateResponse)
def generate_plan_candidates(payload: PlanCandidateRequest) -> PlanCandidateResponse:
    graph, cores, candidates, comparison = generate_candidates(payload.intent)
    if cores:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "hard_constraint_conflict", "message": "当前确认的信息无法同时满足。", "conflict_cores": [core.model_dump(mode="json") for core in cores]},
        )
    if not candidates:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="当前信息无法生成可执行路线候选。")
    digest = intent_digest(payload.intent)
    store = get_plan_candidate_store()
    for candidate in candidates:
        store.put(
            candidate=candidate, intent_digest=digest, intent=payload.intent.model_copy(deep=True),
            itinerary_request=itinerary_request_for_strategy(payload.intent, candidate.strategy),
        )
    return PlanCandidateResponse(intent_digest=digest, constraint_graph=graph, candidates=candidates, comparison=comparison)


@router.post("/plan-candidates/{candidate_id}/select", response_model=TripPlanResponse, status_code=status.HTTP_201_CREATED)
def select_plan_candidate(
    candidate_id: str,
    payload: SelectPlanCandidateRequest,
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
        stored, replay = get_plan_candidate_store().select(
            candidate_id=candidate_id, candidate_hash=payload.candidate_hash,
            intent_digest=payload.intent_digest, idempotency_key=x_idempotency_key,
        )
    except CandidateProposalError as exc:
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"error": {"code": exc.code, "message": str(exc), "recoverable": True}})
    if replay and stored.selected_result is not None:
        return stored.selected_result
    result = get_trip_persistence_service().create_persisted_plan(TripPlanRequest(itinerary_request=stored.itinerary_request))
    set_trip_capability_cookie(response, result.response.trip.id, result.capability)
    stored.selected_result = result.response
    return result.response


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

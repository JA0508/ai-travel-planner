from __future__ import annotations

from typing import Annotated

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.routes.trips import get_trip_capability_from_request, set_trip_capability_cookie, validate_write_origin
from app.schemas.plan_candidates import PlanCandidateRequest, PlanCandidateResponse, PlanningRunHistoryResponse, PlanningRunRecordResponse, SelectPlanCandidateRequest
from app.schemas.trip_compiler import TripCompilerCompileRequest, TripCompilerCompileResponse, TripCompilerPlanRequest
from app.services.constraint_planning import PLANNER_POLICY_VERSION, SNAPSHOT_CONTRACT_VERSION, build_planning_snapshot_manifest, canonical_digest, generate_candidates, intent_digest, itinerary_request_for_strategy
from app.services.planning_run_dependencies import get_planning_run_repository
from app.services.planning_run_repository import PlanningRunError
from app.services.trip_compiler import build_itinerary_request, compile_travel_intent
from app.trips.dependencies import get_trip_persistence_service, get_trip_repository
from app.trips.access import generate_capability, hash_capability, hash_idempotency_key
from app.trips.schemas import TripMetadata, TripPersistenceInfo, TripPlanRequest, TripPlanResponse, TripRevisionMetadata
from app.trips.service import deserialize_itinerary_snapshot

router = APIRouter(prefix="/trip-compiler", tags=["trip-compiler"])


@router.post("/intents/compile", response_model=TripCompilerCompileResponse)
def compile_intent(payload: TripCompilerCompileRequest) -> TripCompilerCompileResponse:
    return compile_travel_intent(payload.text)


PLANNING_RUN_COOKIE = "planning_run_capability"


@router.post("/planning-runs", response_model=PlanningRunRecordResponse)
def create_planning_run(payload: PlanCandidateRequest, response: Response) -> PlanningRunRecordResponse:
    graph, cores, candidates, comparison = generate_candidates(payload.intent)
    if cores:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "hard_constraint_conflict", "message": "当前确认的信息无法同时满足。", "conflict_cores": [core.model_dump(mode="json") for core in cores]},
        )
    if not candidates:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="当前信息无法生成可执行路线候选。")
    digest = intent_digest(payload.intent)
    run_id = f"planning_run_{uuid4().hex}"
    capability = generate_capability()
    now = datetime.now(timezone.utc)
    strategy_inputs = {candidate.id: itinerary_request_for_strategy(payload.intent, candidate.strategy).model_dump(mode="json") for candidate in candidates}
    manifest, poi_snapshot, route_snapshot, strategy_manifest = build_planning_snapshot_manifest(
        intent=payload.intent, graph=graph, candidates=candidates, strategy_inputs=strategy_inputs,
    )
    record = get_planning_run_repository().create(
        run_id=run_id, capability_hash=hash_capability(capability), intent_digest=digest,
        intent_json=payload.intent.model_dump(mode="json"), graph=graph, candidates=candidates,
        comparison=comparison, strategy_inputs=strategy_inputs, planner_policy_version=PLANNER_POLICY_VERSION,
        snapshot_contract_version=SNAPSHOT_CONTRACT_VERSION,
        candidate_set_hash=canonical_digest([candidate.candidate_hash for candidate in candidates]),
        poi_snapshot=poi_snapshot, route_snapshot=route_snapshot,
        strategy_manifest=strategy_manifest, snapshot_manifest=manifest,
        created_at=now.isoformat().replace("+00:00", "Z"), expires_at=(now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z"),
    )
    _set_planning_run_capability_cookie(response, capability)
    return record


@router.post("/plan-candidates", response_model=PlanCandidateResponse, deprecated=True)
def generate_plan_candidates(payload: PlanCandidateRequest, response: Response) -> PlanCandidateResponse:
    record = create_planning_run(payload, response)
    return PlanCandidateResponse(intent_digest=record.intent_digest, constraint_graph=record.constraint_graph, candidates=record.candidates, comparison=record.comparison, planning_run_id=record.planning_run_id, status=record.status, expires_at=record.expires_at)


@router.get("/planning-runs/{run_id}", response_model=PlanningRunRecordResponse)
def get_planning_run(run_id: str, request: Request) -> PlanningRunRecordResponse:
    try:
        return get_planning_run_repository().get(run_id=run_id, capability_hash=_planning_capability_hash(request))
    except PlanningRunError as exc:
        raise HTTPException(status_code=403 if exc.code == "planning_run_access_denied" else 409, detail={"code": exc.code, "message": str(exc), "recoverable": exc.recoverable}) from exc


@router.get("/planning-runs/{run_id}/record", response_model=PlanningRunHistoryResponse)
def get_planning_run_record(run_id: str, request: Request) -> PlanningRunHistoryResponse:
    try:
        return get_planning_run_repository().history(run_id=run_id, capability_hash=_planning_capability_hash(request))
    except PlanningRunError as exc:
        raise HTTPException(status_code=403, detail={"code": exc.code, "message": str(exc)}) from exc


@router.post("/planning-runs/{run_id}/candidates/{candidate_id}/select", response_model=TripPlanResponse, status_code=status.HTTP_201_CREATED)
def select_plan_candidate(
    run_id: str,
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
    planning_capability_hash = _planning_capability_hash(request)
    idempotency_key_hash = hash_idempotency_key(x_idempotency_key)
    trip_capability = generate_capability()
    selection_request_digest = canonical_digest({"candidate_id": candidate_id, "candidate_hash": payload.candidate_hash, "intent_digest": payload.intent_digest})
    try:
        selection = get_planning_run_repository().select_candidate_atomically(
            trip_repository=get_trip_repository(),
            run_id=run_id,
            candidate_id=candidate_id,
            candidate_hash=payload.candidate_hash,
            intent_digest=payload.intent_digest,
            planning_capability_hash=planning_capability_hash,
            trip_capability_hash=hash_capability(trip_capability),
            idempotency_key_hash=idempotency_key_hash,
            request_digest=selection_request_digest,
        )
    except PlanningRunError as exc:
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"error": {"code": exc.code, "message": str(exc), "recoverable": exc.recoverable, "selected_candidate_id": exc.selected_candidate_id, "trip_id": exc.trip_id}})
    if selection.idempotent_replay:
        # A matching Planning Run capability and idempotency payload can recover
        # an already-committed selection after its original response was lost.
        # The repository has rotated the durable hash for this newly-issued cookie.
        aggregate = get_trip_repository().get_trip_with_current_revision(selection.trip_id)
        set_trip_capability_cookie(response, selection.trip_id, trip_capability)
        return TripPlanResponse(
            trip=TripMetadata.from_record(aggregate.trip),
            current_revision=TripRevisionMetadata.from_record(aggregate.current_revision),
            itinerary=deserialize_itinerary_snapshot(aggregate.current_revision.itinerary_snapshot),
            persistence=TripPersistenceInfo(idempotent_replay=True),
        )
    # The selection transaction already authorized and materialized this exact
    # Trip. Read its aggregate directly so a concurrent idempotent recovery
    # cannot turn a just-created response into a stale-capability 500.
    aggregate = get_trip_repository().get_trip_with_current_revision(selection.trip_id)
    set_trip_capability_cookie(response, aggregate.trip.id, trip_capability)
    return TripPlanResponse(
        trip=TripMetadata.from_record(aggregate.trip),
        current_revision=TripRevisionMetadata.from_record(aggregate.current_revision),
        itinerary=deserialize_itinerary_snapshot(aggregate.current_revision.itinerary_snapshot),
        persistence=TripPersistenceInfo(idempotent_replay=False),
    )


@router.post("/plan-candidates/{candidate_id}/select", response_model=TripPlanResponse, status_code=status.HTTP_201_CREATED, deprecated=True)
def select_legacy_plan_candidate(
    candidate_id: str,
    payload: SelectPlanCandidateRequest,
    request: Request,
    response: Response,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> TripPlanResponse:
    run_id = get_planning_run_repository().find_run_for_candidate(candidate_id=candidate_id, capability_hash=_planning_capability_hash(request))
    return select_plan_candidate(run_id, candidate_id, payload, request, response, x_idempotency_key)


def _set_planning_run_capability_cookie(response: Response, capability: str) -> None:
    from os import getenv

    secure = getenv("TRIP_CAPABILITY_COOKIE_SECURE", "false").strip().lower() == "true"
    response.set_cookie(key=PLANNING_RUN_COOKIE, value=capability, httponly=True, secure=secure, samesite="strict", path="/")


def _planning_capability_hash(request: Request) -> str:
    capability = request.cookies.get(PLANNING_RUN_COOKIE)
    if not capability:
        return ""
    return hash_capability(capability)


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

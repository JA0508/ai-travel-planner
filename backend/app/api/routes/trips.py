from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, File, Form, Header, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse, PlainTextResponse

from app.core.runtime_config import parse_cors_allow_origins
from app.imports.dependencies import get_text_import_service
from app.imports.domain import (
    ImportCommitRequest,
    ImportCommitResponse,
    ArtifactInspectionResponse,
    BinaryImportCreateResponse,
    DocumentExtractionCreateResponse,
    DocumentExtractionEvidenceResponse,
    ImportReviewDecisionRequest,
    ImportReviewResponse,
    TextImportCreateRequest,
    TextImportCreateResponse,
    URLImportCreateRequest,
    URLImportCreateResponse,
)
from app.trips.access import capability_cookie_name
from app.trips.dependencies import get_trip_persistence_service, get_trip_repository
from app.trips.errors import TripError
from app.trips.candidates import (
    TripCandidateCreateRequest,
    TripCandidateDecisionRequest,
    TripCandidateDecisionResponse,
    TripCandidateListResponse,
    TripCandidateRegistrationResponse,
)
from app.trips.intent_contracts import (
    AnswerIntentClarificationRequest,
    CompileTripIntentRequest,
    CompileTripIntentResponse,
    EditTripIntentEnvelopeRequest,
    RestoreTripIntentEnvelopeRequest,
    TripIntentRevisionDetailResponse,
    TripIntentRevisionListResponse,
)
from app.trips.schemas import (
    ApplyPersistedMutationProposalRequest,
    ApplyPlannerHandoffProposalRequest,
    DraftTripCreateRequest,
    DraftTripCreateResponse,
    DraftTripDetailResponse,
    PrePlanHandoffApplyRequest,
    PrePlanHandoffApplyResponse,
    PrePlanHandoffPreviewRequest,
    PrePlanHandoffPreviewResponse,
    PrePlanIntentCompileResponse,
    ApplyPersistedReplanProposalRequest,
    PersistedCompletionTaskActionRequest,
    PersistedCompletionTaskActionResponse,
    PersistedMutationApplyResponse,
    PersistedMutationPreviewRequest,
    PersistedMutationPreviewResponse,
    PlannerHandoffApplyResponse,
    PlannerHandoffPreviewRequest,
    PlannerHandoffPreviewResponse,
    PersistedReplanRequest,
    PersistedReplanPreviewResponse,
    PersistedReplanResponse,
    RestoreRevisionRequest,
    RestoreRevisionResponse,
    TripCurrentResponse,
    TripPlanRequest,
    TripPlanResponse,
    TripRevisionDetailResponse,
    TripRevisionListResponse,
    UndoPersistedMutationRequest,
    UndoPersistedMutationResponse,
)

router = APIRouter(prefix="/trips", tags=["trips"])


@router.post("/drafts", response_model=DraftTripCreateResponse, status_code=status.HTTP_201_CREATED)
def create_draft_trip(
    payload: DraftTripCreateRequest,
    response: Response,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> DraftTripCreateResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        result = get_trip_persistence_service().create_draft_trip(
            direct_user_text=payload.direct_user_text,
            idempotency_key=x_idempotency_key,
        )
        set_trip_capability_cookie(response, result.response.trip.id, result.capability)
        return result.response
    except TripError as exc:
        return trip_error_response(exc)


@router.get("/{trip_id}/draft", response_model=DraftTripDetailResponse)
def get_draft_trip(trip_id: str, request: Request) -> DraftTripDetailResponse | JSONResponse:
    try:
        return get_trip_persistence_service().get_draft_trip(
            trip_id=trip_id,
            capability=get_trip_capability_from_request(request, trip_id),
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post("/plan", response_model=TripPlanResponse, status_code=status.HTTP_201_CREATED)
def create_persisted_plan(payload: TripPlanRequest, response: Response) -> TripPlanResponse:
    try:
        result = get_trip_persistence_service().create_persisted_plan(payload)
        set_trip_capability_cookie(response, result.response.trip.id, result.capability)
        return result.response
    except TripError as exc:
        return trip_error_response(exc)


@router.get("/{trip_id}", response_model=TripCurrentResponse)
def get_trip(
    trip_id: str,
    request: Request,
) -> TripCurrentResponse | JSONResponse:
    try:
        return get_trip_persistence_service().get_current_trip(
            trip_id,
            get_trip_capability_from_request(request, trip_id),
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.get("/{trip_id}/revisions", response_model=TripRevisionListResponse)
def list_trip_revisions(
    trip_id: str,
    request: Request,
) -> TripRevisionListResponse | JSONResponse:
    try:
        return get_trip_persistence_service().list_revisions(
            trip_id,
            get_trip_capability_from_request(request, trip_id),
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.get("/{trip_id}/revisions/{revision_id}", response_model=TripRevisionDetailResponse)
def get_trip_revision(
    trip_id: str,
    revision_id: str,
    request: Request,
) -> TripRevisionDetailResponse | JSONResponse:
    try:
        return get_trip_persistence_service().get_revision_detail(
            trip_id,
            revision_id,
            get_trip_capability_from_request(request, trip_id),
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/candidates",
    response_model=TripCandidateRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_trip_candidate(
    trip_id: str,
    payload: TripCandidateCreateRequest,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> TripCandidateRegistrationResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_trip_persistence_service().register_candidate(
            trip_id=trip_id,
            capability=get_trip_capability_from_request(request, trip_id),
            idempotency_key=x_idempotency_key,
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.get("/{trip_id}/candidates", response_model=TripCandidateListResponse)
def list_trip_candidates(
    trip_id: str,
    request: Request,
    state: str | None = None,
) -> TripCandidateListResponse | JSONResponse:
    try:
        return get_trip_persistence_service().list_candidates(
            trip_id=trip_id,
            capability=get_trip_capability_from_request(request, trip_id),
            state=state,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/intent-envelope/compile",
    response_model=CompileTripIntentResponse,
    status_code=status.HTTP_201_CREATED,
)
def compile_trip_intent_envelope(
    trip_id: str,
    payload: CompileTripIntentRequest,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> CompileTripIntentResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_trip_persistence_service().compile_intent_envelope(
            trip_id=trip_id,
            capability=get_trip_capability_from_request(request, trip_id),
            idempotency_key=x_idempotency_key,
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/preplan-intent/compile",
    response_model=PrePlanIntentCompileResponse,
    status_code=status.HTTP_201_CREATED,
)
def compile_preplan_intent_envelope(
    trip_id: str,
    payload: CompileTripIntentRequest,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> PrePlanIntentCompileResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_trip_persistence_service().compile_draft_intent_envelope(
            trip_id=trip_id,
            capability=get_trip_capability_from_request(request, trip_id),
            idempotency_key=x_idempotency_key,
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post("/{trip_id}/preplan-handoff/preview", response_model=PrePlanHandoffPreviewResponse)
def preview_preplan_handoff(
    trip_id: str,
    payload: PrePlanHandoffPreviewRequest,
    request: Request,
) -> PrePlanHandoffPreviewResponse | JSONResponse:
    try:
        return get_trip_persistence_service().preview_preplan_handoff(
            trip_id=trip_id,
            capability=get_trip_capability_from_request(request, trip_id),
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/preplan-handoff/runs/{run_id}/apply",
    response_model=PrePlanHandoffApplyResponse,
)
def apply_preplan_handoff(
    trip_id: str,
    run_id: str,
    payload: PrePlanHandoffApplyRequest,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> PrePlanHandoffApplyResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_trip_persistence_service().apply_preplan_handoff(
            trip_id=trip_id,
            run_id=run_id,
            capability=get_trip_capability_from_request(request, trip_id),
            idempotency_key=x_idempotency_key,
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.get("/{trip_id}/intent-envelope", response_model=TripIntentRevisionListResponse)
def list_trip_intent_envelopes(
    trip_id: str,
    request: Request,
) -> TripIntentRevisionListResponse | JSONResponse:
    try:
        return get_trip_persistence_service().list_intent_envelopes(
            trip_id=trip_id,
            capability=get_trip_capability_from_request(request, trip_id),
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.get(
    "/{trip_id}/intent-envelope/{intent_revision_id}",
    response_model=TripIntentRevisionDetailResponse,
)
def get_trip_intent_envelope(
    trip_id: str,
    intent_revision_id: str,
    request: Request,
) -> TripIntentRevisionDetailResponse | JSONResponse:
    try:
        return get_trip_persistence_service().get_intent_envelope_detail(
            trip_id=trip_id,
            capability=get_trip_capability_from_request(request, trip_id),
            revision_id=intent_revision_id,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/intent-envelope/{intent_revision_id}/edit",
    response_model=CompileTripIntentResponse,
    status_code=status.HTTP_201_CREATED,
)
def edit_trip_intent_envelope(
    trip_id: str,
    intent_revision_id: str,
    payload: EditTripIntentEnvelopeRequest,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> CompileTripIntentResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_trip_persistence_service().edit_intent_envelope(
            trip_id=trip_id,
            capability=get_trip_capability_from_request(request, trip_id),
            revision_id=intent_revision_id,
            idempotency_key=x_idempotency_key,
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/intent-envelope/{intent_revision_id}/clarifications/{question_id}/answer",
    response_model=CompileTripIntentResponse,
    status_code=status.HTTP_201_CREATED,
)
def answer_trip_intent_clarification(
    trip_id: str,
    intent_revision_id: str,
    question_id: str,
    payload: AnswerIntentClarificationRequest,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> CompileTripIntentResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_trip_persistence_service().answer_intent_clarification(
            trip_id=trip_id,
            capability=get_trip_capability_from_request(request, trip_id),
            revision_id=intent_revision_id,
            question_id=question_id,
            idempotency_key=x_idempotency_key,
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/intent-envelope/{intent_revision_id}/restore",
    response_model=CompileTripIntentResponse,
    status_code=status.HTTP_201_CREATED,
)
def restore_trip_intent_envelope(
    trip_id: str,
    intent_revision_id: str,
    payload: RestoreTripIntentEnvelopeRequest,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> CompileTripIntentResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_trip_persistence_service().restore_intent_envelope(
            trip_id=trip_id,
            capability=get_trip_capability_from_request(request, trip_id),
            revision_id=intent_revision_id,
            idempotency_key=x_idempotency_key,
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/candidates/{candidate_id}/decisions",
    response_model=TripCandidateDecisionResponse,
)
def record_trip_candidate_decision(
    trip_id: str,
    candidate_id: str,
    payload: TripCandidateDecisionRequest,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> TripCandidateDecisionResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_trip_persistence_service().record_candidate_decision(
            trip_id=trip_id,
            candidate_id=candidate_id,
            capability=get_trip_capability_from_request(request, trip_id),
            idempotency_key=x_idempotency_key,
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/imports/text",
    response_model=TextImportCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_text_import(
    trip_id: str,
    payload: TextImportCreateRequest,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> TextImportCreateResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_text_import_service().create_text_import(
            trip_id=trip_id,
            capability=get_trip_capability_from_request(request, trip_id),
            idempotency_key=x_idempotency_key,
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/imports/url",
    response_model=URLImportCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_url_import(
    trip_id: str,
    payload: URLImportCreateRequest,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> URLImportCreateResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_text_import_service().create_url_import(
            trip_id=trip_id,
            capability=get_trip_capability_from_request(request, trip_id),
            idempotency_key=x_idempotency_key,
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/imports/artifacts",
    response_model=BinaryImportCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_binary_artifact_import(
    trip_id: str,
    request: Request,
    file: UploadFile = File(...),
    declared_kind: str = Form(...),
    original_label: str | None = Form(default=None),
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> BinaryImportCreateResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return await get_text_import_service().create_binary_import(
            trip_id=trip_id,
            capability=get_trip_capability_from_request(request, trip_id),
            idempotency_key=x_idempotency_key,
            upload_file=file,
            declared_kind=declared_kind,
            original_label=original_label,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.get("/{trip_id}/imports/{import_job_id}", response_model=ImportReviewResponse)
def get_text_import(
    trip_id: str,
    import_job_id: str,
    request: Request,
) -> ImportReviewResponse | JSONResponse:
    try:
        return get_text_import_service().get_import(
            trip_id=trip_id,
            import_job_id=import_job_id,
            capability=get_trip_capability_from_request(request, trip_id),
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.get("/{trip_id}/imports/{import_job_id}/inspection", response_model=ArtifactInspectionResponse)
def get_binary_artifact_inspection(
    trip_id: str,
    import_job_id: str,
    request: Request,
) -> ArtifactInspectionResponse | JSONResponse:
    try:
        return get_text_import_service().get_binary_inspection(
            trip_id=trip_id,
            import_job_id=import_job_id,
            capability=get_trip_capability_from_request(request, trip_id),
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.get("/{trip_id}/imports/{import_job_id}/sanitized-image", response_model=None)
def get_binary_artifact_sanitized_image(
    trip_id: str,
    import_job_id: str,
    request: Request,
) -> Response | JSONResponse:
    try:
        content, mime_type = get_text_import_service().get_sanitized_image_bytes(
            trip_id=trip_id,
            import_job_id=import_job_id,
            capability=get_trip_capability_from_request(request, trip_id),
        )
        return Response(
            content,
            media_type=mime_type,
            headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/imports/{import_job_id}/extract-document",
    response_model=DocumentExtractionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def extract_document_import(
    trip_id: str,
    import_job_id: str,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> DocumentExtractionCreateResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_text_import_service().extract_document_import(
            trip_id=trip_id,
            import_job_id=import_job_id,
            capability=get_trip_capability_from_request(request, trip_id),
            idempotency_key=x_idempotency_key,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/imports/{import_job_id}/document-extraction/pages/{page_number}/retry",
    response_model=DocumentExtractionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def retry_document_extraction_page(
    trip_id: str,
    import_job_id: str,
    page_number: int,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> DocumentExtractionCreateResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_text_import_service().retry_document_extraction_page(
            trip_id=trip_id,
            import_job_id=import_job_id,
            page_number=page_number,
            capability=get_trip_capability_from_request(request, trip_id),
            idempotency_key=x_idempotency_key,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.get(
    "/{trip_id}/imports/{import_job_id}/document-extraction",
    response_model=DocumentExtractionEvidenceResponse,
)
def get_document_extraction_evidence(
    trip_id: str,
    import_job_id: str,
    request: Request,
) -> DocumentExtractionEvidenceResponse | JSONResponse:
    try:
        return get_text_import_service().get_document_extraction_evidence(
            trip_id=trip_id,
            import_job_id=import_job_id,
            capability=get_trip_capability_from_request(request, trip_id),
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.get("/{trip_id}/imports/{import_job_id}/document-extraction/pages/{page_number}/preview", response_model=None)
def get_document_extraction_page_preview(
    trip_id: str,
    import_job_id: str,
    page_number: int,
    request: Request,
) -> Response | JSONResponse:
    try:
        content, mime_type = get_text_import_service().get_document_page_preview_bytes(
            trip_id=trip_id,
            import_job_id=import_job_id,
            page_number=page_number,
            capability=get_trip_capability_from_request(request, trip_id),
        )
        return Response(
            content,
            media_type=mime_type,
            headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.get("/{trip_id}/imports/{import_job_id}/artifact", response_model=None)
def get_text_import_artifact(
    trip_id: str,
    import_job_id: str,
    request: Request,
) -> PlainTextResponse | JSONResponse:
    try:
        text = get_text_import_service().get_artifact_text(
            trip_id=trip_id,
            import_job_id=import_job_id,
            capability=get_trip_capability_from_request(request, trip_id),
        )
        return PlainTextResponse(
            text,
            media_type="text/plain; charset=utf-8",
            headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.get("/{trip_id}/imports/{import_job_id}/mentions", response_model=ImportReviewResponse)
def list_text_import_mentions(
    trip_id: str,
    import_job_id: str,
    request: Request,
) -> ImportReviewResponse | JSONResponse:
    try:
        return get_text_import_service().get_import(
            trip_id=trip_id,
            import_job_id=import_job_id,
            capability=get_trip_capability_from_request(request, trip_id),
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/imports/{import_job_id}/mentions/{mention_id}/decisions",
    response_model=ImportReviewResponse,
)
def record_text_import_decision(
    trip_id: str,
    import_job_id: str,
    mention_id: str,
    payload: ImportReviewDecisionRequest,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> ImportReviewResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_text_import_service().record_decision(
            trip_id=trip_id,
            import_job_id=import_job_id,
            mention_id=mention_id,
            capability=get_trip_capability_from_request(request, trip_id),
            idempotency_key=x_idempotency_key,
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/imports/{import_job_id}/commit",
    response_model=ImportCommitResponse,
)
def commit_text_import(
    trip_id: str,
    import_job_id: str,
    payload: ImportCommitRequest,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> ImportCommitResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_text_import_service().commit_import(
            trip_id=trip_id,
            import_job_id=import_job_id,
            capability=get_trip_capability_from_request(request, trip_id),
            idempotency_key=x_idempotency_key,
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/completion-task",
    response_model=PersistedCompletionTaskActionResponse,
)
def apply_persisted_completion_task(
    trip_id: str,
    payload: PersistedCompletionTaskActionRequest,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> PersistedCompletionTaskActionResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_trip_persistence_service().apply_completion_task(
            trip_id=trip_id,
            capability=get_trip_capability_from_request(request, trip_id),
            idempotency_key=x_idempotency_key,
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/planner-handoff/preview",
    response_model=PlannerHandoffPreviewResponse,
)
def preview_planner_handoff(
    trip_id: str,
    payload: PlannerHandoffPreviewRequest,
    request: Request,
) -> PlannerHandoffPreviewResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_trip_persistence_service().preview_planner_handoff(
            trip_id=trip_id,
            capability=get_trip_capability_from_request(request, trip_id),
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/planner-handoff/proposals/{proposal_id}/apply",
    response_model=PlannerHandoffApplyResponse,
)
def apply_planner_handoff_proposal(
    trip_id: str,
    proposal_id: str,
    payload: ApplyPlannerHandoffProposalRequest,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> PlannerHandoffApplyResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_trip_persistence_service().apply_planner_handoff_proposal(
            trip_id=trip_id,
            proposal_id=proposal_id,
            capability=get_trip_capability_from_request(request, trip_id),
            idempotency_key=x_idempotency_key,
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/replan/preview",
    response_model=PersistedReplanPreviewResponse,
)
def preview_persisted_replan(
    trip_id: str,
    payload: PersistedReplanRequest,
    request: Request,
) -> PersistedReplanPreviewResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_trip_persistence_service().preview_replan(
            trip_id=trip_id,
            capability=get_trip_capability_from_request(request, trip_id),
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/replan/proposals/{proposal_id}/apply",
    response_model=PersistedReplanResponse,
)
def apply_persisted_replan_proposal(
    trip_id: str,
    proposal_id: str,
    payload: ApplyPersistedReplanProposalRequest,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> PersistedReplanResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_trip_persistence_service().apply_replan_proposal(
            trip_id=trip_id,
            proposal_id=proposal_id,
            capability=get_trip_capability_from_request(request, trip_id),
            idempotency_key=x_idempotency_key,
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/mutations/preview",
    response_model=PersistedMutationPreviewResponse,
)
def preview_typed_mutation(
    trip_id: str,
    payload: PersistedMutationPreviewRequest,
    request: Request,
) -> PersistedMutationPreviewResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_trip_persistence_service().preview_typed_mutation(
            trip_id=trip_id,
            capability=get_trip_capability_from_request(request, trip_id),
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/mutation-proposals/{proposal_id}/apply",
    response_model=PersistedMutationApplyResponse,
)
def apply_typed_mutation_proposal(
    trip_id: str,
    proposal_id: str,
    payload: ApplyPersistedMutationProposalRequest,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> PersistedMutationApplyResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_trip_persistence_service().apply_mutation_proposal(
            trip_id=trip_id,
            proposal_id=proposal_id,
            capability=get_trip_capability_from_request(request, trip_id),
            idempotency_key=x_idempotency_key,
            payload=payload,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/revisions/{target_revision_id}/undo",
    response_model=UndoPersistedMutationResponse,
)
def undo_persisted_revision(
    trip_id: str,
    target_revision_id: str,
    payload: UndoPersistedMutationRequest,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> UndoPersistedMutationResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_trip_persistence_service().undo_revision(
            trip_id=trip_id,
            target_revision_id=target_revision_id,
            capability=get_trip_capability_from_request(request, trip_id),
            idempotency_key=x_idempotency_key,
            base_revision_id=payload.base_revision_id,
        )
    except TripError as exc:
        return trip_error_response(exc)


@router.post(
    "/{trip_id}/revisions/{target_revision_id}/restore",
    response_model=RestoreRevisionResponse,
)
def restore_trip_revision(
    trip_id: str,
    target_revision_id: str,
    payload: RestoreRevisionRequest,
    request: Request,
    x_idempotency_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
) -> RestoreRevisionResponse | JSONResponse:
    origin_error = validate_write_origin(request)
    if origin_error is not None:
        return origin_error
    try:
        return get_trip_persistence_service().restore_revision(
            trip_id=trip_id,
            target_revision_id=target_revision_id,
            capability=get_trip_capability_from_request(request, trip_id),
            idempotency_key=x_idempotency_key,
            base_revision_id=payload.base_revision_id,
        )
    except TripError as exc:
        return trip_error_response(exc)


def trip_error_response(exc: TripError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_error_payload())


def get_trip_capability_from_request(request: Request, trip_id: str) -> str | None:
    return request.cookies.get(capability_cookie_name(trip_id))


def set_trip_capability_cookie(response: Response, trip_id: str, capability: str) -> None:
    secure = os.getenv("TRIP_CAPABILITY_COOKIE_SECURE", "false").strip().lower() == "true"
    response.set_cookie(
        key=capability_cookie_name(trip_id),
        value=capability,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )


def validate_write_origin(request: Request) -> JSONResponse | None:
    origin = request.headers.get("origin")
    if origin is None:
        return None
    allowed = parse_cors_allow_origins(os.getenv("TRIP_ALLOWED_ORIGINS") or os.getenv("CORS_ALLOW_ORIGINS"))
    if "*" in allowed or origin in allowed:
        return None
    return trip_error_response(
        TripError(
            code="trip_access_denied",
            message="Write origin is not allowed.",
            status_code=403,
        )
    )


def persistence_readiness() -> dict:
    return get_trip_repository().health_check()

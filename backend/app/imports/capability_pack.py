from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field

from app.core.runtime_config import (
    get_import_binary_enabled,
    get_import_document_extraction_enabled,
    get_import_inspection_mode,
    get_import_text_enabled,
    get_import_url_enabled,
)
from app.imports.document_extraction_runner import document_extraction_resource_capabilities
from app.imports.inspection_runner import resource_capabilities
from app.trips.access import hash_capability
from app.trips.errors import TripError
from app.trips.repository import TripRepository


IMPORT_CAPABILITY_PACK_SCHEMA_VERSION = "1.0"


class ImportForm(str, Enum):
    TEXT = "text"
    URL = "url"
    IMAGE = "image"
    PDF = "pdf"


class ImportAvailability(str, Enum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class ImportCapabilityReasonCode(str, Enum):
    TEXT_IMPORT_DISABLED = "text_import_disabled"
    URL_IMPORT_DISABLED = "url_import_disabled"
    BINARY_IMPORT_DISABLED = "binary_import_disabled"
    BINARY_INSPECTION_UNAVAILABLE = "binary_inspection_unavailable"
    DOCUMENT_EXTRACTION_DISABLED = "document_extraction_disabled"
    OCR_UNAVAILABLE = "ocr_unavailable"
    PDF_RENDERER_UNAVAILABLE = "pdf_renderer_unavailable"


class ImportProcessingStage(str, Enum):
    SOURCE_ARTIFACT = "source_artifact"
    URL_POLICY = "url_policy"
    BOUNDED_FETCH = "bounded_fetch"
    BINARY_INSPECTION = "binary_inspection"
    DOCUMENT_EXTRACTION = "document_extraction"
    DERIVED_TEXT = "derived_text"
    MENTION_EXTRACTION = "mention_extraction"
    RESOLUTION = "resolution"
    REVIEW = "review"


class ImportSafetyBoundaryCode(str, Enum):
    PRIVATE_SOURCE_ARTIFACT = "private_source_artifact"
    REVIEW_REQUIRED = "review_required"
    URL_POLICY = "url_policy"
    ROBOTS_POLICY = "robots_policy"
    BOUNDED_FETCH = "bounded_fetch"
    QUARANTINE_FIRST = "quarantine_first"
    BINARY_INSPECTION = "binary_inspection"
    PRIVATE_BINARY = "private_binary"


class ImportFormCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    form: ImportForm
    availability: ImportAvailability
    reason_codes: list[ImportCapabilityReasonCode] = Field(default_factory=list)
    processing_stages: list[ImportProcessingStage]
    safety_boundary_codes: list[ImportSafetyBoundaryCode]


class ImportCapabilityPackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = IMPORT_CAPABILITY_PACK_SCHEMA_VERSION
    forms: list[ImportFormCapability]


@dataclass(frozen=True, slots=True)
class ImportRuntimeCapabilities:
    text_enabled: bool
    url_enabled: bool
    binary_enabled: bool
    inspection_available: bool
    document_extraction_enabled: bool
    ocr_available: bool
    pdf_renderer_available: bool


def get_import_runtime_capabilities() -> ImportRuntimeCapabilities:
    inspection_resources = resource_capabilities()
    extraction_resources = document_extraction_resource_capabilities()
    return ImportRuntimeCapabilities(
        text_enabled=get_import_text_enabled(),
        url_enabled=get_import_url_enabled(),
        binary_enabled=get_import_binary_enabled(),
        inspection_available=(
            get_import_inspection_mode() == "subprocess"
            and inspection_resources.wall_clock
            and inspection_resources.memory
            and inspection_resources.cpu
        ),
        document_extraction_enabled=get_import_document_extraction_enabled(),
        ocr_available=extraction_resources.ocr_engine,
        pdf_renderer_available=extraction_resources.pdf_renderer,
    )


def build_import_capability_pack(runtime: ImportRuntimeCapabilities) -> ImportCapabilityPackResponse:
    return ImportCapabilityPackResponse(
        forms=[
            _text_capability(runtime),
            _url_capability(runtime),
            _image_capability(runtime),
            _pdf_capability(runtime),
        ]
    )


class ImportCapabilityPackService:
    def __init__(
        self,
        *,
        trip_repository: TripRepository,
        runtime_capabilities: Callable[[], ImportRuntimeCapabilities] = get_import_runtime_capabilities,
    ) -> None:
        self._trip_repository = trip_repository
        self._runtime_capabilities = runtime_capabilities

    def get_snapshot(self, *, trip_id: str, capability: str | None) -> ImportCapabilityPackResponse:
        if not capability:
            raise TripError("trip_access_denied", "Trip access denied.", 403)
        self._trip_repository.get_trip_for_access(trip_id, hash_capability(capability))
        return build_import_capability_pack(self._runtime_capabilities())


def _text_capability(runtime: ImportRuntimeCapabilities) -> ImportFormCapability:
    return ImportFormCapability(
        form=ImportForm.TEXT,
        availability=ImportAvailability.AVAILABLE if runtime.text_enabled else ImportAvailability.UNAVAILABLE,
        reason_codes=[] if runtime.text_enabled else [ImportCapabilityReasonCode.TEXT_IMPORT_DISABLED],
        processing_stages=[
            ImportProcessingStage.SOURCE_ARTIFACT,
            ImportProcessingStage.MENTION_EXTRACTION,
            ImportProcessingStage.RESOLUTION,
            ImportProcessingStage.REVIEW,
        ],
        safety_boundary_codes=[
            ImportSafetyBoundaryCode.PRIVATE_SOURCE_ARTIFACT,
            ImportSafetyBoundaryCode.REVIEW_REQUIRED,
        ],
    )


def _url_capability(runtime: ImportRuntimeCapabilities) -> ImportFormCapability:
    return ImportFormCapability(
        form=ImportForm.URL,
        availability=ImportAvailability.AVAILABLE if runtime.url_enabled else ImportAvailability.UNAVAILABLE,
        reason_codes=[] if runtime.url_enabled else [ImportCapabilityReasonCode.URL_IMPORT_DISABLED],
        processing_stages=[
            ImportProcessingStage.URL_POLICY,
            ImportProcessingStage.BOUNDED_FETCH,
            ImportProcessingStage.SOURCE_ARTIFACT,
            ImportProcessingStage.DERIVED_TEXT,
            ImportProcessingStage.MENTION_EXTRACTION,
            ImportProcessingStage.RESOLUTION,
            ImportProcessingStage.REVIEW,
        ],
        safety_boundary_codes=[
            ImportSafetyBoundaryCode.URL_POLICY,
            ImportSafetyBoundaryCode.ROBOTS_POLICY,
            ImportSafetyBoundaryCode.BOUNDED_FETCH,
            ImportSafetyBoundaryCode.PRIVATE_SOURCE_ARTIFACT,
            ImportSafetyBoundaryCode.REVIEW_REQUIRED,
        ],
    )


def _image_capability(runtime: ImportRuntimeCapabilities) -> ImportFormCapability:
    reason_codes = _binary_reason_codes(runtime, requires_pdf_renderer=False)
    return _binary_capability(
        form=ImportForm.IMAGE,
        reason_codes=reason_codes,
        processing_stages=[
            ImportProcessingStage.SOURCE_ARTIFACT,
            ImportProcessingStage.BINARY_INSPECTION,
            ImportProcessingStage.DOCUMENT_EXTRACTION,
            ImportProcessingStage.REVIEW,
        ],
    )


def _pdf_capability(runtime: ImportRuntimeCapabilities) -> ImportFormCapability:
    reason_codes = _binary_reason_codes(runtime, requires_pdf_renderer=True)
    return _binary_capability(
        form=ImportForm.PDF,
        reason_codes=reason_codes,
        processing_stages=[
            ImportProcessingStage.SOURCE_ARTIFACT,
            ImportProcessingStage.BINARY_INSPECTION,
            ImportProcessingStage.DOCUMENT_EXTRACTION,
            ImportProcessingStage.REVIEW,
        ],
    )


def _binary_reason_codes(
    runtime: ImportRuntimeCapabilities,
    *,
    requires_pdf_renderer: bool,
) -> list[ImportCapabilityReasonCode]:
    if not runtime.binary_enabled:
        return [ImportCapabilityReasonCode.BINARY_IMPORT_DISABLED]
    if not runtime.inspection_available:
        return [ImportCapabilityReasonCode.BINARY_INSPECTION_UNAVAILABLE]

    reason_codes: list[ImportCapabilityReasonCode] = []
    if not runtime.document_extraction_enabled:
        reason_codes.append(ImportCapabilityReasonCode.DOCUMENT_EXTRACTION_DISABLED)
    if not runtime.ocr_available:
        reason_codes.append(ImportCapabilityReasonCode.OCR_UNAVAILABLE)
    if requires_pdf_renderer and not runtime.pdf_renderer_available:
        reason_codes.append(ImportCapabilityReasonCode.PDF_RENDERER_UNAVAILABLE)
    return reason_codes


def _binary_capability(
    *,
    form: ImportForm,
    reason_codes: list[ImportCapabilityReasonCode],
    processing_stages: list[ImportProcessingStage],
) -> ImportFormCapability:
    if not reason_codes:
        availability = ImportAvailability.AVAILABLE
    elif reason_codes[0] in {
        ImportCapabilityReasonCode.BINARY_IMPORT_DISABLED,
        ImportCapabilityReasonCode.BINARY_INSPECTION_UNAVAILABLE,
    }:
        availability = ImportAvailability.UNAVAILABLE
    else:
        availability = ImportAvailability.DEGRADED
    return ImportFormCapability(
        form=form,
        availability=availability,
        reason_codes=reason_codes,
        processing_stages=processing_stages,
        safety_boundary_codes=[
            ImportSafetyBoundaryCode.QUARANTINE_FIRST,
            ImportSafetyBoundaryCode.BINARY_INSPECTION,
            ImportSafetyBoundaryCode.PRIVATE_BINARY,
            ImportSafetyBoundaryCode.REVIEW_REQUIRED,
        ],
    )

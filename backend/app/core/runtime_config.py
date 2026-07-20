from __future__ import annotations

import logging
import os
from typing import Any


DEFAULT_AMAP_REQUEST_TIMEOUT_SECONDS = 10.0
DEFAULT_OPENAI_INTENT_TIMEOUT_SECONDS = 20.0
DEFAULT_OPENAI_DISAMBIGUATION_TIMEOUT_SECONDS = 15.0
DEFAULT_OPENAI_INTENT_MODEL = "gpt-4o-mini"
DEFAULT_TRIP_STORE_BUSY_TIMEOUT_SECONDS = 5.0
DEFAULT_TRIP_REPLAN_PROPOSAL_TTL_SECONDS = 900.0
DEFAULT_IMPORT_TEXT_MAX_BYTES = 100 * 1024
DEFAULT_IMPORT_MAX_MENTIONS = 60
DEFAULT_IMPORT_MAX_RESOLUTION_CANDIDATES = 5
DEFAULT_IMPORT_URL_MAX_REDIRECTS = 5
DEFAULT_IMPORT_URL_MAX_COMPRESSED_BYTES = 2 * 1024 * 1024
DEFAULT_IMPORT_URL_MAX_DECODED_BYTES = 5 * 1024 * 1024
DEFAULT_IMPORT_URL_MAX_TEXT_BYTES = 500 * 1024
DEFAULT_IMPORT_URL_CACHE_TTL_SECONDS = 900
DEFAULT_IMPORT_BINARY_MAX_IMAGE_BYTES = 12 * 1024 * 1024
DEFAULT_IMPORT_BINARY_MAX_PDF_BYTES = 20 * 1024 * 1024
DEFAULT_IMPORT_BINARY_UPLOAD_CHUNK_BYTES = 64 * 1024
DEFAULT_IMPORT_INSPECTION_TIMEOUT_SECONDS = 10.0
DEFAULT_IMPORT_INSPECTION_MAX_MEMORY_MB = 512
DEFAULT_IMPORT_INSPECTION_MAX_OUTPUT_BYTES = 256 * 1024
DEFAULT_IMPORT_IMAGE_MAX_PIXELS = 40_000_000
DEFAULT_IMPORT_IMAGE_MAX_DIMENSION = 12_000
DEFAULT_IMPORT_PDF_MAX_PAGES = 80
DEFAULT_IMPORT_PDF_MAX_OBJECTS = 5_000
DEFAULT_IMPORT_DOCUMENT_EXTRACTION_TIMEOUT_SECONDS = 20.0
DEFAULT_IMPORT_DOCUMENT_EXTRACTION_MAX_MEMORY_MB = 768
DEFAULT_IMPORT_DOCUMENT_EXTRACTION_MAX_OUTPUT_BYTES = 1024 * 1024
DEFAULT_IMPORT_DOCUMENT_MAX_TEXT_BYTES = 500 * 1024
DEFAULT_IMPORT_DOCUMENT_OCR_TIMEOUT_SECONDS = 10.0


def parse_cors_allow_origins(raw_value: str | None) -> list[str]:
    if raw_value is None:
        return ["*"]

    origins = [origin.strip() for origin in raw_value.split(",") if origin.strip()]
    return origins or ["*"]


def get_amap_request_timeout_seconds() -> float:
    return parse_positive_float_env(
        "AMAP_REQUEST_TIMEOUT_SECONDS",
        DEFAULT_AMAP_REQUEST_TIMEOUT_SECONDS,
    )


def get_openai_intent_timeout_seconds() -> float:
    return parse_positive_float_env(
        "OPENAI_INTENT_TIMEOUT_SECONDS",
        DEFAULT_OPENAI_INTENT_TIMEOUT_SECONDS,
    )


def get_openai_disambiguation_timeout_seconds() -> float:
    return parse_positive_float_env(
        "OPENAI_DISAMBIGUATION_TIMEOUT_SECONDS",
        DEFAULT_OPENAI_DISAMBIGUATION_TIMEOUT_SECONDS,
    )


def get_openai_intent_model() -> str:
    configured_model = os.getenv("OPENAI_INTENT_MODEL", DEFAULT_OPENAI_INTENT_MODEL).strip()
    return configured_model or DEFAULT_OPENAI_INTENT_MODEL


def get_trip_persistence_configuration_summary() -> dict[str, Any]:
    return {
        "mode": os.getenv("TRIP_STORE_MODE", "sqlite").strip().lower() or "sqlite",
        "busy_timeout_seconds": parse_positive_float_env(
            "TRIP_STORE_BUSY_TIMEOUT_SECONDS",
            DEFAULT_TRIP_STORE_BUSY_TIMEOUT_SECONDS,
        ),
        "capability_cookie_secure": os.getenv(
            "TRIP_CAPABILITY_COOKIE_SECURE",
            "false",
        ).strip().lower()
        == "true",
        "allowed_origins": parse_cors_allow_origins(
            os.getenv("TRIP_ALLOWED_ORIGINS") or os.getenv("CORS_ALLOW_ORIGINS")
        ),
        "replan_proposal_ttl_seconds": parse_positive_float_env(
            "TRIP_REPLAN_PROPOSAL_TTL_SECONDS",
            DEFAULT_TRIP_REPLAN_PROPOSAL_TTL_SECONDS,
        ),
    }


def get_trip_replan_proposal_ttl_seconds() -> float:
    return parse_positive_float_env(
        "TRIP_REPLAN_PROPOSAL_TTL_SECONDS",
        DEFAULT_TRIP_REPLAN_PROPOSAL_TTL_SECONDS,
    )


def get_import_text_enabled() -> bool:
    return os.getenv("IMPORT_TEXT_ENABLED", "true").strip().lower() not in {"0", "false", "no"}


def get_import_text_max_bytes() -> int:
    return parse_positive_int_env("IMPORT_TEXT_MAX_BYTES", DEFAULT_IMPORT_TEXT_MAX_BYTES)


def get_import_url_enabled() -> bool:
    return os.getenv("IMPORT_URL_ENABLED", "true").strip().lower() not in {"0", "false", "no"}


def get_import_url_fetcher_mode() -> str:
    return os.getenv("IMPORT_URL_FETCHER_MODE", "network").strip().lower() or "network"


def get_import_url_max_redirects() -> int:
    return parse_positive_int_env("IMPORT_URL_MAX_REDIRECTS", DEFAULT_IMPORT_URL_MAX_REDIRECTS)


def get_import_url_max_compressed_bytes() -> int:
    return parse_positive_int_env("IMPORT_URL_MAX_COMPRESSED_BYTES", DEFAULT_IMPORT_URL_MAX_COMPRESSED_BYTES)


def get_import_url_max_decoded_bytes() -> int:
    return parse_positive_int_env("IMPORT_URL_MAX_DECODED_BYTES", DEFAULT_IMPORT_URL_MAX_DECODED_BYTES)


def get_import_url_max_text_bytes() -> int:
    return parse_positive_int_env("IMPORT_URL_MAX_TEXT_BYTES", DEFAULT_IMPORT_URL_MAX_TEXT_BYTES)


def get_import_url_cache_ttl_seconds() -> int:
    return parse_positive_int_env("IMPORT_URL_CACHE_TTL_SECONDS", DEFAULT_IMPORT_URL_CACHE_TTL_SECONDS)


def get_import_url_connect_timeout_seconds() -> float:
    return parse_positive_float_env("IMPORT_URL_CONNECT_TIMEOUT_SECONDS", 5.0)


def get_import_url_read_timeout_seconds() -> float:
    return parse_positive_float_env("IMPORT_URL_READ_TIMEOUT_SECONDS", 10.0)


def get_import_url_total_timeout_seconds() -> float:
    return parse_positive_float_env("IMPORT_URL_TOTAL_TIMEOUT_SECONDS", 20.0)


def get_import_url_allowed_ports() -> set[int]:
    raw_value = os.getenv("IMPORT_URL_ALLOWED_PORTS", "80,443")
    ports: set[int] = set()
    for value in raw_value.split(","):
        try:
            port = int(value.strip())
        except ValueError:
            continue
        if 1 <= port <= 65535:
            ports.add(port)
    return ports or {80, 443}


def get_import_url_user_agent() -> str:
    value = os.getenv("IMPORT_URL_USER_AGENT", "AITravelPlannerURLImporter/1.0").strip()
    return value or "AITravelPlannerURLImporter/1.0"


def get_import_url_robots_fail_closed() -> bool:
    return os.getenv("IMPORT_URL_ROBOTS_FAIL_CLOSED", "true").strip().lower() not in {"0", "false", "no"}


def get_import_artifact_store_mode() -> str:
    return os.getenv("IMPORT_ARTIFACT_STORE_MODE", "local").strip().lower() or "local"


def get_import_artifact_root() -> str:
    return os.getenv("IMPORT_ARTIFACT_ROOT", "data/import-artifacts").strip() or "data/import-artifacts"


def get_import_binary_enabled() -> bool:
    return os.getenv("IMPORT_BINARY_ENABLED", "true").strip().lower() not in {"0", "false", "no"}


def get_import_binary_max_image_bytes() -> int:
    return parse_positive_int_env("IMPORT_BINARY_MAX_IMAGE_BYTES", DEFAULT_IMPORT_BINARY_MAX_IMAGE_BYTES)


def get_import_binary_max_pdf_bytes() -> int:
    return parse_positive_int_env("IMPORT_BINARY_MAX_PDF_BYTES", DEFAULT_IMPORT_BINARY_MAX_PDF_BYTES)


def get_import_binary_upload_chunk_bytes() -> int:
    return parse_positive_int_env("IMPORT_BINARY_UPLOAD_CHUNK_BYTES", DEFAULT_IMPORT_BINARY_UPLOAD_CHUNK_BYTES)


def get_import_binary_staging_root() -> str:
    return os.getenv("IMPORT_BINARY_STAGING_ROOT", "data/import-staging").strip() or "data/import-staging"


def get_import_inspection_mode() -> str:
    return os.getenv("IMPORT_INSPECTION_MODE", "subprocess").strip().lower() or "subprocess"


def get_import_inspection_timeout_seconds() -> float:
    return parse_positive_float_env("IMPORT_INSPECTION_TIMEOUT_SECONDS", DEFAULT_IMPORT_INSPECTION_TIMEOUT_SECONDS)


def get_import_inspection_max_memory_mb() -> int:
    return parse_positive_int_env("IMPORT_INSPECTION_MAX_MEMORY_MB", DEFAULT_IMPORT_INSPECTION_MAX_MEMORY_MB)


def get_import_inspection_max_output_bytes() -> int:
    return parse_positive_int_env("IMPORT_INSPECTION_MAX_OUTPUT_BYTES", DEFAULT_IMPORT_INSPECTION_MAX_OUTPUT_BYTES)


def get_import_image_max_pixels() -> int:
    return parse_positive_int_env("IMPORT_IMAGE_MAX_PIXELS", DEFAULT_IMPORT_IMAGE_MAX_PIXELS)


def get_import_image_max_dimension() -> int:
    return parse_positive_int_env("IMPORT_IMAGE_MAX_DIMENSION", DEFAULT_IMPORT_IMAGE_MAX_DIMENSION)


def get_import_pdf_max_pages() -> int:
    return parse_positive_int_env("IMPORT_PDF_MAX_PAGES", DEFAULT_IMPORT_PDF_MAX_PAGES)


def get_import_pdf_max_objects() -> int:
    return parse_positive_int_env("IMPORT_PDF_MAX_OBJECTS", DEFAULT_IMPORT_PDF_MAX_OBJECTS)


def get_import_document_extraction_enabled() -> bool:
    return os.getenv("IMPORT_DOCUMENT_EXTRACTION_ENABLED", "true").strip().lower() not in {"0", "false", "no"}


def get_import_document_extraction_timeout_seconds() -> float:
    return parse_positive_float_env(
        "IMPORT_DOCUMENT_EXTRACTION_TIMEOUT_SECONDS",
        DEFAULT_IMPORT_DOCUMENT_EXTRACTION_TIMEOUT_SECONDS,
    )


def get_import_document_extraction_max_memory_mb() -> int:
    return parse_positive_int_env(
        "IMPORT_DOCUMENT_EXTRACTION_MAX_MEMORY_MB",
        DEFAULT_IMPORT_DOCUMENT_EXTRACTION_MAX_MEMORY_MB,
    )


def get_import_document_extraction_max_output_bytes() -> int:
    return parse_positive_int_env(
        "IMPORT_DOCUMENT_EXTRACTION_MAX_OUTPUT_BYTES",
        DEFAULT_IMPORT_DOCUMENT_EXTRACTION_MAX_OUTPUT_BYTES,
    )


def get_import_document_max_text_bytes() -> int:
    return parse_positive_int_env("IMPORT_DOCUMENT_MAX_TEXT_BYTES", DEFAULT_IMPORT_DOCUMENT_MAX_TEXT_BYTES)


def get_import_document_ocr_command() -> str:
    return os.getenv("IMPORT_DOCUMENT_OCR_COMMAND", "tesseract").strip() or "tesseract"


def get_import_document_ocr_languages() -> str:
    return os.getenv("IMPORT_DOCUMENT_OCR_LANGUAGES", "eng+chi_sim").strip() or "eng+chi_sim"


def get_import_document_ocr_timeout_seconds() -> float:
    return parse_positive_float_env("IMPORT_DOCUMENT_OCR_TIMEOUT_SECONDS", DEFAULT_IMPORT_DOCUMENT_OCR_TIMEOUT_SECONDS)


def get_import_pdf_page_ocr_enabled() -> bool:
    return os.getenv("IMPORT_PDF_PAGE_OCR_ENABLED", "true").strip().lower() not in {"0", "false", "no"}


def get_import_processing_mode() -> str:
    return os.getenv("IMPORT_PROCESSING_MODE", "inline").strip().lower() or "inline"


def get_import_extractor_mode() -> str:
    return os.getenv("IMPORT_EXTRACTOR_MODE", "deterministic").strip().lower() or "deterministic"


def get_import_resolver_mode() -> str:
    return os.getenv("IMPORT_RESOLVER_MODE", "deterministic").strip().lower() or "deterministic"


def get_import_max_mentions() -> int:
    return parse_positive_int_env("IMPORT_MAX_MENTIONS", DEFAULT_IMPORT_MAX_MENTIONS)


def get_import_max_resolution_candidates() -> int:
    return parse_positive_int_env(
        "IMPORT_MAX_RESOLUTION_CANDIDATES",
        DEFAULT_IMPORT_MAX_RESOLUTION_CANDIDATES,
    )


def get_import_configuration_summary() -> dict[str, Any]:
    from app.imports.document_extraction_runner import document_extraction_resource_capabilities
    from app.imports.domain import ARTIFACT_INSPECTION_SCHEMA_VERSION, ARTIFACT_INSPECTOR_VERSION, DOCUMENT_EXTRACTION_SCHEMA_VERSION, DOCUMENT_EXTRACTOR_VERSION, IMPORT_EXTRACTION_SCHEMA_VERSION, URL_IMPORT_FETCHER_VERSION, URL_IMPORT_POLICY_VERSION
    from app.imports.inspection_runner import resource_capabilities

    fetcher_mode = get_import_url_fetcher_mode()
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    resources = resource_capabilities()
    extraction_resources = document_extraction_resource_capabilities()
    binary_status = "healthy" if resources.wall_clock and get_import_inspection_mode() == "subprocess" else "degraded"
    if not (resources.memory and resources.cpu):
        binary_status = "degraded"

    return {
        "text_enabled": get_import_text_enabled(),
        "url_enabled": get_import_url_enabled(),
        "binary_enabled": get_import_binary_enabled(),
        "binary_supported_types": ["pdf", "jpeg", "png", "webp"],
        "inspection_mode": get_import_inspection_mode(),
        "inspection_schema_version": ARTIFACT_INSPECTION_SCHEMA_VERSION,
        "inspector_version": ARTIFACT_INSPECTOR_VERSION,
        "document_extraction_enabled": get_import_document_extraction_enabled(),
        "document_extraction_schema_version": DOCUMENT_EXTRACTION_SCHEMA_VERSION,
        "document_extractor_version": DOCUMENT_EXTRACTOR_VERSION,
        "document_extraction_capabilities": {
            "wall_clock": extraction_resources.wall_clock,
            "memory": extraction_resources.memory,
            "cpu": extraction_resources.cpu,
            "ocr_engine": extraction_resources.ocr_engine,
            "pdf_renderer": extraction_resources.pdf_renderer,
            "ocr_languages": get_import_document_ocr_languages(),
            "silent_ocr_fallback": False,
        },
        "resource_limits": {
            "wall_clock": resources.wall_clock,
            "memory": resources.memory,
            "cpu": resources.cpu,
        },
        "url_fetcher_mode": fetcher_mode,
        "url_policy_version": URL_IMPORT_POLICY_VERSION,
        "url_fetcher_version": URL_IMPORT_FETCHER_VERSION,
        "robots_fail_closed": get_import_url_robots_fail_closed(),
        "processing_mode": get_import_processing_mode(),
        "artifact_store": get_import_artifact_store_mode(),
        "extraction_schema_version": IMPORT_EXTRACTION_SCHEMA_VERSION,
        "extractor_mode": get_import_extractor_mode(),
        "resolver_mode": get_import_resolver_mode(),
        "max_text_bytes": get_import_text_max_bytes(),
        "max_mentions": get_import_max_mentions(),
        "max_resolution_candidates": get_import_max_resolution_candidates(),
        "status": "unhealthy" if app_env == "production" and fetcher_mode == "fixture" else binary_status,
    }


def parse_positive_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default

    try:
        parsed = float(raw_value)
    except ValueError:
        return default

    return parsed if parsed > 0 else default


def parse_positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default

    try:
        parsed = int(raw_value)
    except ValueError:
        return default

    return parsed if parsed > 0 else default


def configure_logging() -> None:
    level_name = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def get_runtime_configuration_summary() -> dict[str, Any]:
    return {
        "app_env": os.getenv("APP_ENV", "development"),
        "cors_allow_origins": parse_cors_allow_origins(os.getenv("CORS_ALLOW_ORIGINS")),
        "amap": {
            "api_key_configured": bool(os.getenv("AMAP_API_KEY")),
            "request_timeout_seconds": get_amap_request_timeout_seconds(),
        },
        "openai": {
            "api_key_configured": bool(os.getenv("OPENAI_API_KEY")),
            "intent_model": get_openai_intent_model(),
            "intent_timeout_seconds": get_openai_intent_timeout_seconds(),
            "disambiguation_timeout_seconds": get_openai_disambiguation_timeout_seconds(),
        },
        "trip_persistence": get_trip_persistence_configuration_summary(),
        "imports": get_import_configuration_summary(),
    }

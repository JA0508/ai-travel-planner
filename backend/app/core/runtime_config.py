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


def get_import_artifact_store_mode() -> str:
    return os.getenv("IMPORT_ARTIFACT_STORE_MODE", "local").strip().lower() or "local"


def get_import_artifact_root() -> str:
    return os.getenv("IMPORT_ARTIFACT_ROOT", "data/import-artifacts").strip() or "data/import-artifacts"


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
    from app.imports.domain import IMPORT_EXTRACTION_SCHEMA_VERSION

    return {
        "text_enabled": get_import_text_enabled(),
        "processing_mode": get_import_processing_mode(),
        "artifact_store": get_import_artifact_store_mode(),
        "extraction_schema_version": IMPORT_EXTRACTION_SCHEMA_VERSION,
        "extractor_mode": get_import_extractor_mode(),
        "resolver_mode": get_import_resolver_mode(),
        "max_text_bytes": get_import_text_max_bytes(),
        "max_mentions": get_import_max_mentions(),
        "max_resolution_candidates": get_import_max_resolution_candidates(),
        "status": "healthy",
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

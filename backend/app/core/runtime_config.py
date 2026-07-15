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


def parse_positive_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default

    try:
        parsed = float(raw_value)
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
    }

"""Fail closed on development cookie/origin settings in production."""

from collections.abc import Mapping
from urllib.parse import urlsplit


def validate_production_security(environment: Mapping[str, str]) -> None:
    app_env = environment.get("APP_ENV") or environment.get("ENVIRONMENT") or environment.get("NODE_ENV", "development")
    if app_env.strip().lower() != "production":
        return
    if environment.get("TRIP_CAPABILITY_COOKIE_SECURE", "").strip().lower() != "true":
        raise ValueError("Production requires TRIP_CAPABILITY_COOKIE_SECURE=true")
    for field in ("CORS_ALLOW_ORIGINS", "TRIP_ALLOWED_ORIGINS"):
        origins = environment.get(field, "").split(",")
        if not all(_is_https_origin(origin.strip()) for origin in origins):
            raise ValueError(f"Production requires explicit HTTPS origins in {field}")


def _is_https_origin(value: str) -> bool:
    try:
        url = urlsplit(value)
        port = url.port
        return bool(
            url.scheme == "https" and url.hostname and "*" not in value
            and not url.username and not url.password
            and not url.path and not url.query and not url.fragment
            and (port is None or 0 < port <= 65535)
        )
    except ValueError:
        return False

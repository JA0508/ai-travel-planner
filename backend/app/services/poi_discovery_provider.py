from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Protocol

from app.services.amap_client import (
    GeocodingError,
    search_place_around_candidates,
    search_place_candidates,
)


class PoiDiscoveryUnavailable(Exception):
    """Raised when a configured POI provider cannot serve realtime discovery."""


class PoiDiscoveryConfigurationError(RuntimeError):
    """Raised when runtime config forbids running without realtime POI discovery."""


@dataclass(frozen=True, slots=True)
class PoiDiscoveryCandidate:
    name: str | None
    address: str | None
    type: str | None
    typecode: str | None
    business_area: str | None
    latitude: float | None
    longitude: float | None


@dataclass(frozen=True, slots=True)
class PoiDiscoveryCapability:
    provider: str
    app_env: str
    mode: str
    required: bool
    poi_discovery_enabled: bool
    text_search_enabled: bool
    around_search_enabled: bool
    catalog_fallback_enabled: bool
    missing_config: tuple[str, ...]
    production_ready: bool
    failure_reason: str | None = None

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["missing_config"] = list(self.missing_config)
        return payload


class PoiDiscoveryProvider(Protocol):
    def capability(self) -> PoiDiscoveryCapability:
        ...

    def search_text(self, *, keyword: str, city: str, offset: int) -> list[PoiDiscoveryCandidate]:
        ...

    def search_around(
        self,
        *,
        keyword: str,
        city: str,
        latitude: float,
        longitude: float,
        radius: int,
        offset: int,
    ) -> list[PoiDiscoveryCandidate]:
        ...


class AmapPoiDiscoveryProvider:
    provider_name = "amap"

    def capability(self) -> PoiDiscoveryCapability:
        return get_poi_discovery_capability()

    def search_text(self, *, keyword: str, city: str, offset: int) -> list[PoiDiscoveryCandidate]:
        try:
            return [
                candidate_from_mapping(candidate)
                for candidate in search_place_candidates(keyword=keyword, city=city, offset=offset)
            ]
        except GeocodingError as exc:
            raise PoiDiscoveryUnavailable(str(exc)) from exc

    def search_around(
        self,
        *,
        keyword: str,
        city: str,
        latitude: float,
        longitude: float,
        radius: int,
        offset: int,
    ) -> list[PoiDiscoveryCandidate]:
        try:
            return [
                candidate_from_mapping(candidate)
                for candidate in search_place_around_candidates(
                    keyword=keyword,
                    city=city,
                    latitude=latitude,
                    longitude=longitude,
                    radius=radius,
                    offset=offset,
                )
            ]
        except GeocodingError as exc:
            raise PoiDiscoveryUnavailable(str(exc)) from exc


def candidate_from_mapping(candidate: dict) -> PoiDiscoveryCandidate:
    return PoiDiscoveryCandidate(
        name=candidate.get("name"),
        address=candidate.get("address"),
        type=candidate.get("type"),
        typecode=candidate.get("typecode"),
        business_area=candidate.get("business_area"),
        latitude=candidate.get("latitude"),
        longitude=candidate.get("longitude"),
    )


def get_poi_discovery_capability(*, validate_provider: bool = False) -> PoiDiscoveryCapability:
    app_env = normalized_app_env()
    mode = normalized_poi_discovery_mode(app_env)
    required = mode == "required"
    missing_config = tuple(
        config_name for config_name in ("AMAP_API_KEY",) if not os.getenv(config_name)
    )
    enabled = not missing_config
    provider_failure_reason = None
    if validate_provider and enabled:
        provider_failure_reason = validate_amap_provider()
        if provider_failure_reason:
            enabled = False
    catalog_fallback_enabled = not required
    if missing_config:
        failure_reason = f"Missing required config: {', '.join(missing_config)}"
    else:
        failure_reason = provider_failure_reason
    return PoiDiscoveryCapability(
        provider="amap",
        app_env=app_env,
        mode=mode,
        required=required,
        poi_discovery_enabled=enabled,
        text_search_enabled=enabled,
        around_search_enabled=enabled,
        catalog_fallback_enabled=catalog_fallback_enabled,
        missing_config=missing_config,
        production_ready=enabled or not required,
        failure_reason=failure_reason,
    )


def normalized_app_env() -> str:
    return (
        os.getenv("APP_ENV")
        or os.getenv("ENVIRONMENT")
        or os.getenv("NODE_ENV")
        or "development"
    ).strip().lower()


def normalized_poi_discovery_mode(app_env: str) -> str:
    configured = os.getenv("POI_DISCOVERY_MODE")
    if configured:
        normalized = configured.strip().lower()
        if normalized in {"required", "fallback"}:
            return normalized
    return "required" if app_env == "production" else "fallback"


def validate_amap_provider() -> str | None:
    try:
        search_place_candidates(keyword="上海", city="上海", offset=1)
    except GeocodingError as exc:
        return str(exc)
    return None


def enforce_poi_discovery_configuration() -> None:
    capability = get_poi_discovery_capability(validate_provider=True)
    if capability.production_ready:
        return
    raise PoiDiscoveryConfigurationError(
        "Realtime POI discovery is required but not configured. "
        f"Missing config: {', '.join(capability.missing_config) or 'unknown'}. "
        "Set AMAP_API_KEY or explicitly set POI_DISCOVERY_MODE=fallback for demo/dev deployments."
    )


def default_poi_discovery_provider() -> PoiDiscoveryProvider:
    return AmapPoiDiscoveryProvider()

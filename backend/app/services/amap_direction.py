from __future__ import annotations

import os
import logging

import requests

from app.core.runtime_config import get_amap_request_timeout_seconds


AMAP_WALKING_URL = "https://restapi.amap.com/v5/direction/walking"
AMAP_DRIVING_URL = "https://restapi.amap.com/v5/direction/driving"
AMAP_TRANSIT_URL = "https://restapi.amap.com/v3/direction/transit/integrated"
ROUTE_CACHE: dict[tuple[str, float, float, float, float, str | None], dict[str, object]] = {}
logger = logging.getLogger(__name__)


class RoutePlanningError(Exception):
    """Raised when Amap route planning cannot return a valid route."""


def get_walking_route(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
) -> dict:
    """
    Get walking distance and duration between two coordinates using Amap.

    Returns:
    - distance_m: walking distance in meters
    - duration_s: walking duration in seconds
    - path_points: ordered route geometry points for map rendering
    """
    return get_route(
        mode="walk",
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        dest_lat=dest_lat,
        dest_lng=dest_lng,
    )


def get_route(
    *,
    mode: str,
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    city: str | None = None,
) -> dict:
    if mode == "drive":
        return get_amap_v5_route(
            mode="driving",
            url=AMAP_DRIVING_URL,
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            dest_lat=dest_lat,
            dest_lng=dest_lng,
            city=None,
        )
    if mode == "transit":
        return get_transit_route(
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            dest_lat=dest_lat,
            dest_lng=dest_lng,
            city=city,
        )
    return get_amap_v5_route(
        mode="walking",
        url=AMAP_WALKING_URL,
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        dest_lat=dest_lat,
        dest_lng=dest_lng,
        city=None,
    )


def get_amap_v5_route(
    *,
    mode: str,
    url: str,
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    city: str | None,
) -> dict:
    api_key = require_amap_api_key()
    cache_key = route_cache_key(mode, origin_lat, origin_lng, dest_lat, dest_lng, city)
    if cache_key in ROUTE_CACHE:
        logger.debug("Amap %s route cache hit.", mode)
        return ROUTE_CACHE[cache_key]

    payload = call_amap_route_api(
        url,
        {
            "key": api_key,
            "origin": f"{origin_lng},{origin_lat}",
            "destination": f"{dest_lng},{dest_lat}",
            "output": "JSON",
            "show_fields": "cost,polyline",
        },
        mode,
    )

    route = payload.get("route") or {}
    paths = route.get("paths") or []
    if not paths:
        raise RoutePlanningError(f"No {mode} route found for the given coordinates.")

    first_path = paths[0]
    distance = first_path.get("distance")
    duration = first_path.get("cost", {}).get("duration")
    if duration is None:
        duration = first_path.get("duration")

    if distance is None or duration is None:
        raise RoutePlanningError(f"{mode} route response is missing distance or duration.")

    try:
        result = {
            "distance_m": int(float(distance)),
            "duration_s": int(float(duration)),
            "path_points": _extract_path_points(first_path),
            "source": f"amap_{mode}",
        }
    except (TypeError, ValueError) as exc:
        raise RoutePlanningError(f"{mode} route response contains invalid distance or duration.") from exc

    ROUTE_CACHE[cache_key] = result
    return result


def get_transit_route(
    *,
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    city: str | None,
) -> dict:
    if not city:
        raise RoutePlanningError("Transit route requires a city hint.")

    api_key = require_amap_api_key()
    normalized_city = city.strip() or None
    if not normalized_city:
        raise RoutePlanningError("Transit route requires a city hint.")

    cache_key = route_cache_key("transit", origin_lat, origin_lng, dest_lat, dest_lng, normalized_city)
    if cache_key in ROUTE_CACHE:
        logger.debug("Amap transit route cache hit.")
        return ROUTE_CACHE[cache_key]

    payload = call_amap_route_api(
        AMAP_TRANSIT_URL,
        {
            "key": api_key,
            "origin": f"{origin_lng},{origin_lat}",
            "destination": f"{dest_lng},{dest_lat}",
            "city": normalized_city,
            "cityd": normalized_city,
            "output": "JSON",
        },
        "transit",
    )

    route = payload.get("route") or {}
    transits = route.get("transits") or []
    if not transits:
        raise RoutePlanningError("No transit route found for the given coordinates.")

    first_transit = transits[0]
    distance = first_transit.get("distance") or route.get("distance")
    duration = first_transit.get("duration")
    if distance is None or duration is None:
        raise RoutePlanningError("Transit route response is missing distance or duration.")

    try:
        result = {
            "distance_m": int(float(distance)),
            "duration_s": int(float(duration)),
            "path_points": _extract_transit_path_points(first_transit),
            "source": "amap_transit",
        }
    except (TypeError, ValueError) as exc:
        raise RoutePlanningError("Transit route response contains invalid distance or duration.") from exc

    ROUTE_CACHE[cache_key] = result
    return result


def require_amap_api_key() -> str:
    api_key = os.getenv("AMAP_API_KEY")
    if not api_key:
        raise RoutePlanningError("AMAP_API_KEY is not configured.")
    return api_key


def call_amap_route_api(url: str, params: dict[str, object], mode: str) -> dict:
    try:
        response = requests.get(
            url,
            params=params,
            timeout=get_amap_request_timeout_seconds(),
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RoutePlanningError(f"Failed to call Amap {mode} route API.") from exc

    if str(payload.get("status")) != "1":
        info = payload.get("info") or "Unknown Amap route planning error."
        raise RoutePlanningError(f"Amap {mode} route failed: {info}")

    return payload


def route_cache_key(
    mode: str,
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    city: str | None,
) -> tuple[str, float, float, float, float, str | None]:
    return (
        mode,
        round(origin_lat, 6),
        round(origin_lng, 6),
        round(dest_lat, 6),
        round(dest_lng, 6),
        city,
    )


def _extract_path_points(path_payload: dict) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for step in path_payload.get("steps") or []:
        raw_polyline = step.get("polyline")
        if not isinstance(raw_polyline, str):
            continue
        for raw_point in raw_polyline.split(";"):
            longitude_text, _, latitude_text = raw_point.partition(",")
            if not longitude_text or not latitude_text:
                continue
            try:
                point = {
                    "latitude": float(latitude_text),
                    "longitude": float(longitude_text),
                }
            except ValueError:
                continue
            if points and points[-1] == point:
                continue
            points.append(point)
    return points


def _extract_transit_path_points(transit_payload: dict) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for segment in transit_payload.get("segments") or []:
        walking = segment.get("walking") or {}
        for point in _extract_path_points_from_steps(walking.get("steps") or []):
            if not points or points[-1] != point:
                points.append(point)
        bus = segment.get("bus") or {}
        for busline in bus.get("buslines") or []:
            raw_polyline = busline.get("polyline")
            if not isinstance(raw_polyline, str):
                continue
            for point in _parse_polyline(raw_polyline):
                if not points or points[-1] != point:
                    points.append(point)
    return points


def _extract_path_points_from_steps(steps: list[dict]) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for step in steps:
        raw_polyline = step.get("polyline")
        if not isinstance(raw_polyline, str):
            continue
        for point in _parse_polyline(raw_polyline):
            if points and points[-1] == point:
                continue
            points.append(point)
    return points


def _parse_polyline(raw_polyline: str) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for raw_point in raw_polyline.split(";"):
        longitude_text, _, latitude_text = raw_point.partition(",")
        if not longitude_text or not latitude_text:
            continue
        try:
            points.append(
                {
                    "latitude": float(latitude_text),
                    "longitude": float(longitude_text),
                }
            )
        except ValueError:
            continue
    return points

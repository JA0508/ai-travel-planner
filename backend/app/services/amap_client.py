from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import requests

from app.core.runtime_config import get_amap_request_timeout_seconds


AMAP_GEOCODE_URL = "https://restapi.amap.com/v3/geocode/geo"
AMAP_PLACE_TEXT_URL = "https://restapi.amap.com/v3/place/text"
AMAP_PLACE_AROUND_URL = "https://restapi.amap.com/v3/place/around"
GEOCODE_CACHE: dict[tuple[str, str | None], tuple[float, float]] = {}
GEOCODE_CACHE_FILE = Path(__file__).resolve().parents[2] / ".amap_geocode_cache.json"
MAX_QPS_RETRIES = 2
QPS_LIMIT_INFO = "CUQPS_HAS_EXCEEDED_THE_LIMIT"
logger = logging.getLogger(__name__)


class GeocodingError(Exception):
    """Raised when Amap geocoding cannot return valid coordinates."""


def _load_persistent_cache() -> None:
    if not GEOCODE_CACHE_FILE.exists():
        return

    try:
        payload = json.loads(GEOCODE_CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.debug("Failed to load persistent Amap geocode cache.", exc_info=True)
        return

    for item in payload:
        name = item.get("name")
        city = item.get("city")
        latitude = item.get("latitude")
        longitude = item.get("longitude")
        if not isinstance(name, str):
            continue
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            continue
        GEOCODE_CACHE[(name, city)] = (float(latitude), float(longitude))


def _save_persistent_cache() -> None:
    payload = [
        {
            "name": name,
            "city": city,
            "latitude": latitude,
            "longitude": longitude,
        }
        for (name, city), (latitude, longitude) in sorted(GEOCODE_CACHE.items())
    ]
    try:
        GEOCODE_CACHE_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        logger.debug("Failed to persist Amap geocode cache.", exc_info=True)
        return


_load_persistent_cache()


def geocode_place(name: str, city: str | None = None) -> tuple[float, float]:
    """
    Geocode a place name with the Amap Web Service geocoding API.

    Amap returns the first match with location formatted as "longitude,latitude".
    This function converts it into (latitude, longitude) for internal use.
    """
    api_key = os.getenv("AMAP_API_KEY")
    if not api_key:
        raise GeocodingError("AMAP_API_KEY is not configured.")

    cache_key = (name.strip(), city.strip() if city else None)
    if cache_key in GEOCODE_CACHE:
        logger.debug("Amap geocode cache hit for %r.", cache_key[0])
        return GEOCODE_CACHE[cache_key]

    query_params = {
        "key": api_key,
        "address": cache_key[0],
        "output": "JSON",
    }
    if cache_key[1]:
        query_params["city"] = cache_key[1]

    payload: dict | None = None
    for attempt in range(MAX_QPS_RETRIES + 1):
        try:
            response = requests.get(
                AMAP_GEOCODE_URL,
                params=query_params,
                timeout=get_amap_request_timeout_seconds(),
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise GeocodingError(f"Failed to call Amap geocoding for '{name}'.") from exc

        if payload.get("status") == "1":
            break

        if payload.get("info") == QPS_LIMIT_INFO and attempt < MAX_QPS_RETRIES:
            logger.warning(
                "Amap geocoding QPS limit hit for %r; retrying attempt %s/%s.",
                name,
                attempt + 1,
                MAX_QPS_RETRIES,
            )
            time.sleep(0.5 * (attempt + 1))
            continue
        break

    if payload is None:
        raise GeocodingError(f"Failed to call Amap geocoding for '{name}'.")

    if payload.get("status") != "1":
        info = payload.get("info") or "Unknown Amap geocoding error."
        raise GeocodingError(f"Amap geocoding failed for '{name}': {info}")

    geocodes = payload.get("geocodes") or []
    if not geocodes:
        raise GeocodingError(f"No geocoding result found for '{name}'.")

    location = geocodes[0].get("location")
    if not location or "," not in location:
        raise GeocodingError(f"Invalid geocoding location returned for '{name}'.")

    longitude_str, latitude_str = location.split(",", 1)

    try:
        coordinates = (float(latitude_str), float(longitude_str))
    except ValueError as exc:
        raise GeocodingError(f"Invalid coordinate format returned for '{name}'.") from exc

    GEOCODE_CACHE[cache_key] = coordinates
    _save_persistent_cache()
    return coordinates


def geocode_place_details(name: str, city: str | None = None) -> dict:
    """
    Return the first full Amap geocode payload item for a place.
    """
    api_key = os.getenv("AMAP_API_KEY")
    if not api_key:
        raise GeocodingError("AMAP_API_KEY is not configured.")

    query_params = {
        "key": api_key,
        "address": name.strip(),
        "output": "JSON",
    }
    if city:
        query_params["city"] = city.strip()

    try:
        response = requests.get(
            AMAP_GEOCODE_URL,
            params=query_params,
            timeout=get_amap_request_timeout_seconds(),
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise GeocodingError(f"Failed to call Amap geocoding for '{name}'.") from exc

    if payload.get("status") != "1":
        info = payload.get("info") or "Unknown Amap geocoding error."
        raise GeocodingError(f"Amap geocoding failed for '{name}': {info}")

    geocodes = payload.get("geocodes") or []
    if not geocodes:
        raise GeocodingError(f"No geocoding result found for '{name}'.")

    geocode = dict(geocodes[0])
    location = geocode.get("location")
    if location and "," in location:
        longitude_str, latitude_str = location.split(",", 1)
        geocode["latitude"] = float(latitude_str)
        geocode["longitude"] = float(longitude_str)
    return geocode


def search_place_candidates(
    keyword: str,
    city: str,
    *,
    offset: int = 10,
) -> list[dict]:
    """
    Search named POI candidates inside one city with Amap place text search.
    """
    api_key = os.getenv("AMAP_API_KEY")
    if not api_key:
        raise GeocodingError("AMAP_API_KEY is not configured.")

    query_params = {
        "key": api_key,
        "keywords": keyword.strip(),
        "city": city.strip(),
        "citylimit": "true",
        "offset": str(offset),
        "page": "1",
        "extensions": "base",
    }

    try:
        response = requests.get(
            AMAP_PLACE_TEXT_URL,
            params=query_params,
            timeout=get_amap_request_timeout_seconds(),
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise GeocodingError(f"Failed to call Amap place search for '{keyword}'.") from exc

    if payload.get("status") != "1":
        info = payload.get("info") or "Unknown Amap place search error."
        raise GeocodingError(f"Amap place search failed for '{keyword}': {info}")

    return _extract_place_search_results(payload)


def search_place_detail_candidates(
    keyword: str,
    city: str | None = None,
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    offset: int = 5,
) -> list[dict]:
    """
    Search detailed POI candidates for a stop detail card.

    This is still a bounded POI provider call, not a full research system. When
    coordinates are available, candidates are sorted by proximity to the current
    scheduled stop so the card is less likely to show a same-name place in the
    wrong part of the city.
    """
    api_key = os.getenv("AMAP_API_KEY")
    if not api_key:
        raise GeocodingError("AMAP_API_KEY is not configured.")

    query_params = {
        "key": api_key,
        "keywords": keyword.strip(),
        "offset": str(offset),
        "page": "1",
        "extensions": "all",
    }
    if city:
        query_params["city"] = city.strip()
        query_params["citylimit"] = "true"

    try:
        response = requests.get(
            AMAP_PLACE_TEXT_URL,
            params=query_params,
            timeout=get_amap_request_timeout_seconds(),
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise GeocodingError(f"Failed to call Amap place detail search for '{keyword}'.") from exc

    if payload.get("status") != "1":
        info = payload.get("info") or "Unknown Amap place detail search error."
        raise GeocodingError(f"Amap place detail search failed for '{keyword}': {info}")

    candidates = _extract_place_search_results(payload)
    if latitude is not None and longitude is not None:
        candidates.sort(
            key=lambda candidate: _squared_distance(
                latitude,
                longitude,
                candidate["latitude"],
                candidate["longitude"],
            )
        )
    return candidates


def search_place_around_candidates(
    keyword: str,
    city: str,
    *,
    latitude: float,
    longitude: float,
    radius: int = 3000,
    offset: int = 10,
) -> list[dict]:
    """
    Search POI candidates near a route-context coordinate with Amap place around search.
    """
    api_key = os.getenv("AMAP_API_KEY")
    if not api_key:
        raise GeocodingError("AMAP_API_KEY is not configured.")

    query_params = {
        "key": api_key,
        "keywords": keyword.strip(),
        "city": city.strip(),
        "location": f"{longitude},{latitude}",
        "radius": str(radius),
        "sortrule": "distance",
        "offset": str(offset),
        "page": "1",
        "extensions": "base",
    }

    try:
        response = requests.get(
            AMAP_PLACE_AROUND_URL,
            params=query_params,
            timeout=get_amap_request_timeout_seconds(),
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise GeocodingError(f"Failed to call Amap around search for '{keyword}'.") from exc

    if payload.get("status") != "1":
        info = payload.get("info") or "Unknown Amap around search error."
        raise GeocodingError(f"Amap around search failed for '{keyword}': {info}")

    return _extract_place_search_results(payload)


def _extract_place_search_results(payload: dict) -> list[dict]:
    results: list[dict] = []
    for poi in payload.get("pois") or []:
        location = poi.get("location")
        if not isinstance(location, str) or "," not in location:
            continue
        longitude_str, latitude_str = location.split(",", 1)
        try:
            latitude = float(latitude_str)
            longitude = float(longitude_str)
        except ValueError:
            continue
        biz_ext = poi.get("biz_ext") if isinstance(poi.get("biz_ext"), dict) else {}
        photos = poi.get("photos") if isinstance(poi.get("photos"), list) else []
        photo_urls = [
            photo.get("url")
            for photo in photos
            if isinstance(photo, dict) and isinstance(photo.get("url"), str)
        ]
        results.append(
            {
                "name": poi.get("name"),
                "address": poi.get("address"),
                "type": poi.get("type"),
                "typecode": poi.get("typecode"),
                "business_area": poi.get("business_area"),
                "tel": poi.get("tel"),
                "website": poi.get("website"),
                "rating": biz_ext.get("rating"),
                "cost": biz_ext.get("cost"),
                "open_time": biz_ext.get("open_time"),
                "photo_url": photo_urls[0] if photo_urls else None,
                "latitude": latitude,
                "longitude": longitude,
            }
        )
    return results


def _squared_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    return (lat1 - lat2) ** 2 + (lng1 - lng2) ** 2

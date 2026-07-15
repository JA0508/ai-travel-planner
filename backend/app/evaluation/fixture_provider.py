from __future__ import annotations

import math

from app.schemas import HotelInput, HotelStay, NormalizedPOI, POIType, RawPOIInput
from app.services.amap_client import GeocodingError
from app.services.amap_direction import RoutePlanningError
from app.services.mock_normalizer import infer_poi_profile


class FixtureProviderSnapshot:
    def __init__(self, case: dict) -> None:
        self.case = case
        self.place_snapshots = {
            self._place_key(snapshot["query"], snapshot.get("poi_type"), snapshot.get("city")): snapshot
            for snapshot in case.get("provider_snapshot", {}).get("places", [])
        }
        self.route_availability = case.get("provider_snapshot", {}).get(
            "default_route_availability",
            "known",
        )

    def normalize_poi(
        self,
        raw_poi: RawPOIInput,
        poi_type: POIType,
        city: str | None = None,
    ) -> NormalizedPOI:
        snapshot = self._lookup_place(raw_poi.name, poi_type.value, city)
        status = snapshot.get("resolution_status")
        if status != "known":
            raise GeocodingError(f"Fixture place snapshot is {status}: {raw_poi.name}")
        profile = infer_poi_profile(raw_poi.name, poi_type)
        return NormalizedPOI(
            name=snapshot.get("canonical_name") or raw_poi.name,
            type=poi_type,
            city=snapshot.get("city") or city,
            latitude=float(snapshot["latitude"]),
            longitude=float(snapshot["longitude"]),
            duration_minutes=int(snapshot.get("duration_minutes") or profile.typical_duration_minutes),
            profile=profile,
            fixed_day=raw_poi.fixed_day,
            fixed_time_start=raw_poi.fixed_time_start,
            fixed_time_end=raw_poi.fixed_time_end,
        )

    def normalize_hotel(self, hotel: HotelInput, city: str | None = None) -> HotelStay:
        snapshot = self._lookup_place(hotel.name, "hotel", city)
        status = snapshot.get("resolution_status")
        if status != "known":
            raise GeocodingError(f"Fixture hotel snapshot is {status}: {hotel.name}")
        return HotelStay(
            name=snapshot.get("canonical_name") or hotel.name,
            city=snapshot.get("city") or city,
            latitude=float(snapshot["latitude"]),
            longitude=float(snapshot["longitude"]),
        )

    def normalize_anchor(self, name: str, city: str | None = None) -> HotelStay:
        snapshot = self._lookup_place(name, "anchor", city)
        status = snapshot.get("resolution_status")
        if status != "known":
            raise GeocodingError(f"Fixture anchor snapshot is {status}: {name}")
        return HotelStay(
            name=snapshot.get("canonical_name") or name,
            city=snapshot.get("city") or city,
            latitude=float(snapshot["latitude"]),
            longitude=float(snapshot["longitude"]),
        )

    def get_route(
        self,
        *,
        mode: str,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        city: str | None = None,
    ) -> dict:
        if self.route_availability in {"missing", "failed"}:
            raise RoutePlanningError(f"Fixture route snapshot is {self.route_availability}")
        distance_km = haversine_km(origin_lat, origin_lng, dest_lat, dest_lng)
        speed_kmh = {"walk": 4.5, "drive": 30.0, "transit": 24.0}.get(mode, 24.0)
        overhead_seconds = 0 if mode == "walk" else 6 * 60 if mode == "drive" else 10 * 60
        duration_s = int(overhead_seconds + (max(distance_km * 1.25, distance_km) / speed_kmh) * 3600)
        return {
            "distance_m": max(1, int(distance_km * 1250)),
            "duration_s": max(60, duration_s),
            "source": f"fixture_{mode}",
            "path_points": [],
        }

    def _lookup_place(self, query: str, poi_type: str, city: str | None) -> dict:
        key = self._place_key(query, poi_type, city)
        snapshot = self.place_snapshots.get(key)
        if snapshot is None:
            raise GeocodingError(f"No fixture place snapshot for {query}")
        return snapshot

    @staticmethod
    def _place_key(query: str, poi_type: str | None, city: str | None) -> tuple[str, str, str]:
        return (query.strip().casefold(), (poi_type or "").casefold(), (city or "").casefold())


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius_km = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lng / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

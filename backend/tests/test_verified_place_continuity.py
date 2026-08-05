from __future__ import annotations

import unittest
from unittest.mock import patch

from app.api.routes.itinerary import normalize_optional_pois
from app.core.scheduler import Scheduler
from app.schemas.itinerary import POIType, VerifiedPlaceRef
from app.schemas.trip_compiler import TripCompilerFixedEvent, TripCompilerPlace, TravelIntent
from app.services.amap_direction import RoutePlanningError
from app.services.trip_compiler import build_itinerary_request
from app.services.constraint_planning import generate_candidates


def verified_place(stable_id: str, name: str, provider_id: str, latitude: float, longitude: float) -> VerifiedPlaceRef:
    return VerifiedPlaceRef(
        stable_id=stable_id,
        original_name=name,
        canonical_name=name,
        provider="amap",
        provider_place_id=provider_id,
        latitude=latitude,
        longitude=longitude,
        category="风景名胜",
        source_fragment_ids=["source_hangzhou"],
    )


class VerifiedPlaceContinuityTests(unittest.TestCase):
    def _hangzhou_intent(self) -> TravelIntent:
        west_lake = verified_place("place_west_lake", "西湖风景名胜区", "amap-west-lake", 30.235, 120.148)
        lingyin = verified_place("place_lingyin", "灵隐寺", "amap-lingyin", 30.240, 120.102)
        tea_museum = verified_place("fixed_tea_museum", "中国茶叶博物馆（双峰馆区）", "amap-tea-museum", 30.218, 120.104)
        return TravelIntent(
            destination="杭州",
            trip_days=2,
            must_visit_places=[
                TripCompilerPlace(stable_id=west_lake.stable_id, name="西湖", ownership="user_must", confidence=1, verified_place=west_lake),
                TripCompilerPlace(stable_id=lingyin.stable_id, name="灵隐寺", ownership="user_must", confidence=1, verified_place=lingyin),
            ],
            optional_places=[
                TripCompilerPlace(stable_id="place_longjing", name="龙井村", ownership="user_optional", confidence=1, verified_place=verified_place("place_longjing", "龙井村", "amap-longjing", 30.216, 120.112)),
            ],
            fixed_events=[
                TripCompilerFixedEvent(
                    stable_id="fixed_tea_museum", name="下午预约", day=2, start_time="14:00", end_time="16:00",
                    fixed_reason="用户预约", confidence=1, verified_place=tea_museum,
                )
            ],
        )

    def test_confirmed_place_handoff_reuses_provider_identity_without_name_resolution(self) -> None:
        intent = self._hangzhou_intent()

        request = build_itinerary_request(intent)
        raw = request.scenic_spots
        self.assertEqual([item.candidate_id for item in raw], ["place_west_lake", "place_lingyin", "place_longjing", "fixed_tea_museum"])
        self.assertEqual([item.canonical_place_id for item in raw], ["amap-west-lake", "amap-lingyin", "amap-longjing", "amap-tea-museum"])
        self.assertEqual(raw[-1].name, "中国茶叶博物馆（双峰馆区）")
        self.assertEqual((raw[-1].fixed_day, raw[-1].fixed_time_start.isoformat(), raw[-1].fixed_time_end.isoformat()), (2, "14:00:00", "16:00:00"))

        with patch("app.api.routes.itinerary.normalize_poi", side_effect=AssertionError("confirmed places must not be re-resolved by name")):
            normalized = normalize_optional_pois(raw, poi_type=POIType.SCENIC, city="杭州")
        self.assertEqual([item.candidate_id for item in normalized], ["place_west_lake", "place_lingyin", "place_longjing", "fixed_tea_museum"])
        self.assertEqual([item.canonical_place_id for item in normalized], ["amap-west-lake", "amap-lingyin", "amap-longjing", "amap-tea-museum"])
        self.assertEqual(normalized[0].verified_place.provider_place_id, "amap-west-lake")

    def test_candidate_snapshot_keeps_fixed_verified_place_and_route_leg(self) -> None:
        with patch("app.core.scheduler.get_route", return_value={"distance_m": 1100, "duration_s": 840, "source": "amap_fixture"}):
            _graph, cores, candidates, _comparison = generate_candidates(self._hangzhou_intent())
        self.assertEqual(cores, [])
        self.assertTrue(candidates)
        items = [item for day in candidates[0].itinerary.days for block in day.blocks for item in block.items]
        tea_museum = next(item for item in items if item.canonical_place_id == "amap-tea-museum")
        self.assertEqual(tea_museum.stable_id, "fixed_tea_museum")
        self.assertTrue(tea_museum.is_fixed)
        self.assertEqual((tea_museum.day, tea_museum.start_time.isoformat(), tea_museum.end_time.isoformat()), (2, "14:00:00", "16:00:00"))
        self.assertTrue(any(item.travel_data_status == "confirmed" and item.travel_duration_s == 840 for item in items))

    def test_route_provider_failure_keeps_persisted_leg_unavailable(self) -> None:
        with patch("app.core.scheduler.get_route", side_effect=RoutePlanningError("provider unavailable")):
            route = Scheduler().estimate_city_travel_info(
                origin_lat=30.235,
                origin_lng=120.148,
                dest_lat=30.240,
                dest_lng=120.102,
                city="杭州",
            )
        self.assertIsNone(route["distance_m"])
        self.assertIsNone(route["duration_s"])
        self.assertEqual(route["data_status"], "unavailable")
        self.assertEqual(route["provider"], "amap")
        self.assertGreater(int(route["scheduling_duration_s"]), 0)

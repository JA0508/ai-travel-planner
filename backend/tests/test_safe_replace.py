from __future__ import annotations

import tempfile
import unittest
from datetime import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import (
    DayItinerary,
    DayTimeBlock,
    HotelStay,
    ItineraryResponse,
    PlanningAnchorSource,
    POIType,
    ScheduledPOI,
    ScheduledPOISourceType,
    TimeBlockType,
)
from app.schemas.itinerary import VerifiedPlaceRef
from app.services.poi_discovery_provider import (
    PoiDiscoveryCandidate,
    PoiDiscoveryCapability,
)
from app.services.itinerary_completion_recommendation import replacement_route_impact
from app.trips.dependencies import reset_trip_repository_cache_for_tests


class SafeReplaceProvider:
    candidates = (
        PoiDiscoveryCandidate(
            name="青芝坞餐厅",
            address="杭州市西湖区青芝坞",
            type="中餐厅",
            typecode="050100",
            business_area="杭州",
            latitude=30.26049,
            longitude=120.12745,
            provider_place_id="amap-qingzhiwu",
        ),
        PoiDiscoveryCandidate(
            name="茶人村",
            address="杭州市西湖区龙井路",
            type="杭帮菜",
            typecode="050100",
            business_area="杭州",
            latitude=30.229,
            longitude=120.111,
            provider_place_id="amap-tea-village",
        ),
        PoiDiscoveryCandidate(
            name="龙井草堂",
            address="杭州市西湖区龙井路",
            type="杭帮菜",
            typecode="050100",
            business_area="杭州",
            latitude=30.226,
            longitude=120.109,
            provider_place_id="amap-longjing-cottage",
        ),
        PoiDiscoveryCandidate(
            name="远山宴",
            address="杭州市临安区",
            type="中餐厅",
            typecode="050100",
            business_area="杭州",
            latitude=30.5,
            longitude=119.7,
            provider_place_id="amap-far-dinner",
        ),
        PoiDiscoveryCandidate(
            name="无身份候选",
            address=None,
            type="中餐厅",
            typecode="050100",
            business_area="杭州",
            latitude=30.23,
            longitude=120.11,
            provider_place_id=None,
        ),
    )

    def capability(self) -> PoiDiscoveryCapability:
        return PoiDiscoveryCapability(
            provider="amap",
            app_env="test",
            mode="required",
            required=True,
            poi_discovery_enabled=True,
            text_search_enabled=True,
            around_search_enabled=True,
            catalog_fallback_enabled=False,
            missing_config=(),
            production_ready=True,
        )

    def search_text(self, *, keyword: str, city: str, offset: int) -> list[PoiDiscoveryCandidate]:
        del offset
        normalized = keyword.strip()
        return [
            candidate
            for candidate in self.candidates
            if candidate.business_area == city.strip() and candidate.name == normalized
        ]

    def search_around(self, **_: object) -> list[PoiDiscoveryCandidate]:
        return list(self.candidates)


class ManySafeReplaceCandidatesProvider(SafeReplaceProvider):
    candidates = SafeReplaceProvider.candidates + (
        PoiDiscoveryCandidate(
            name="西湖小馆",
            address="杭州市西湖区龙井路",
            type="杭帮菜",
            typecode="050100",
            business_area="杭州",
            latitude=30.228,
            longitude=120.112,
            provider_place_id="amap-west-lake-bistro",
        ),
        PoiDiscoveryCandidate(
            name="茶山餐厅",
            address="杭州市西湖区龙井路",
            type="杭帮菜",
            typecode="050100",
            business_area="杭州",
            latitude=30.227,
            longitude=120.113,
            provider_place_id="amap-tea-hill-restaurant",
        ),
    )


def verified_route(*, origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> dict:
    del origin_lng, dest_lng
    unsafe = origin_lat >= 30.4 or dest_lat >= 30.4
    return {
        "distance_m": 8_000 if unsafe else 800,
        "duration_s": 9_000 if unsafe else 600,
        "path_points": [],
        "source": "amap_test",
    }


class SafeReplaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            "os.environ",
            {
                "TRIP_STORE_MODE": "sqlite",
                "TRIP_STORE_PATH": str(Path(self.temp_dir.name) / "safe-replace.sqlite3"),
                "TRIP_ALLOWED_ORIGINS": "http://testserver",
                "CORS_ALLOW_ORIGINS": "http://testserver",
            },
        )
        self.env.start()
        reset_trip_repository_cache_for_tests()

    def tearDown(self) -> None:
        reset_trip_repository_cache_for_tests()
        self.env.stop()
        self.temp_dir.cleanup()

    def test_replacement_candidates_are_bounded_verified_and_exclude_current_place(self) -> None:
        client = TestClient(app)
        itinerary = safe_replace_itinerary()

        with (
            patch(
                "app.services.itinerary_completion_recommendation.default_poi_discovery_provider",
                return_value=ManySafeReplaceCandidatesProvider(),
            ),
            patch(
                "app.services.itinerary_completion_recommendation.get_walking_route",
                side_effect=verified_route,
            ) as route_lookup,
        ):
            response = client.post(
                "/preview-completion-task-candidates",
                json={
                    "itinerary": itinerary.model_dump(mode="json"),
                    "task_id": "replace_stop",
                    "replacement_stop_id": "stop-meal",
                    "day": 1,
                    "block_type": "afternoon",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        options = response.json()["options"]
        self.assertGreaterEqual(len(options), 2)
        self.assertLessEqual(len(options), 3)
        self.assertNotIn("青芝坞餐厅", {option["name"] for option in options})
        self.assertTrue(all(option["verified_place"]["provider"] == "amap" for option in options))
        self.assertTrue(all(option["verified_place"]["provider_place_id"] for option in options))
        self.assertTrue(all(option["stable_id"] for option in options))
        self.assertTrue(any(option["route_impact"]["safe_to_apply"] is False for option in options))
        self.assertTrue(any(option["route_impact"]["safe_to_apply"] is True for option in options))
        self.assertLessEqual(route_lookup.call_count, 6)

    def test_replacement_can_reuse_the_confirmed_adjacent_route_budget(self) -> None:
        itinerary = safe_replace_itinerary(no_outbound_slack=True)
        day = itinerary.days[0]
        target = next(
            item
            for block in day.blocks
            for item in block.items
            if item.stable_id == "stop-meal"
        )
        with patch(
            "app.services.itinerary_completion_recommendation.get_walking_route",
            side_effect=verified_route,
        ):
            impact = replacement_route_impact(
                day=day,
                target=target,
                candidate_name="茶人村",
                candidate_latitude=30.229,
                candidate_longitude=120.111,
            )

        self.assertTrue(impact.safe_to_apply)
        self.assertIsNone(impact.blocking_reason)

    def test_unverified_replacement_and_user_owned_target_are_rejected_without_revision(self) -> None:
        client, trip_id, revision_id, itinerary = self.create_trip()
        target_id = item_by_name(itinerary, "青芝坞餐厅")["stable_id"]
        user_target_id = item_by_name(itinerary, "灵隐寺")["stable_id"]
        unverified = replacement_command(
            base_revision_id=revision_id,
            stop_id=target_id,
            option={
                "name": "虚构餐厅",
                "type": "restaurant",
                "reasoning_summary": "候选没有来源。",
                "itinerary_relation_summary": "不能进入正式替换。",
            },
        )

        unverified_response = client.post(
            f"/trips/{trip_id}/mutations/preview",
            json=unverified,
            headers={"Origin": "http://testserver"},
        )
        user_owned_response = client.post(
            f"/trips/{trip_id}/mutations/preview",
            json=replacement_command(
                base_revision_id=revision_id,
                stop_id=user_target_id,
                option=verified_option("茶人村", "amap-tea-village", 30.229, 120.111),
            ),
            headers={"Origin": "http://testserver"},
        )

        self.assertEqual(unverified_response.status_code, 422, unverified_response.text)
        self.assertEqual(user_owned_response.status_code, 422, user_owned_response.text)
        self.assertEqual(user_owned_response.json()["error"]["reason_code"], "replace_target_not_eligible")
        self.assertEqual(len(client.get(f"/trips/{trip_id}/revisions").json()["revisions"]), 1)

    def test_safe_replace_apply_reload_and_undo_preserve_other_stops_and_routes(self) -> None:
        client, trip_id, revision_id, itinerary = self.create_trip()
        target = item_by_name(itinerary, "青芝坞餐厅")
        original_fixed = item_by_name(itinerary, "中国茶叶博物馆")
        original_lingyin = item_by_name(itinerary, "灵隐寺")
        provider = SafeReplaceProvider()

        with (
            patch(
                "app.services.itinerary_completion_recommendation.default_poi_discovery_provider",
                return_value=provider,
            ),
            patch(
                "app.services.itinerary_completion_recommendation.get_walking_route",
                side_effect=verified_route,
            ),
        ):
            candidates = client.post(
                "/preview-completion-task-candidates",
                json={
                    "itinerary": itinerary,
                    "task_id": "replace_stop",
                    "replacement_stop_id": target["stable_id"],
                    "day": 1,
                    "block_type": "afternoon",
                },
            ).json()["options"]
        selected = next(option for option in candidates if option["name"] == "茶人村")

        with (
            patch("app.trips.service.default_poi_discovery_provider", return_value=provider),
            patch(
                "app.services.itinerary_completion_recommendation.get_walking_route",
                side_effect=verified_route,
            ),
        ):
            preview = client.post(
                f"/trips/{trip_id}/mutations/preview",
                json=replacement_command(
                    base_revision_id=revision_id,
                    stop_id=target["stable_id"],
                    option=selected,
                ),
                headers={"Origin": "http://testserver"},
            )

        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(len(client.get(f"/trips/{trip_id}/revisions").json()["revisions"]), 1)
        preview_itinerary = preview.json()["itinerary"]
        replacement = item_by_name(preview_itinerary, "茶人村")
        preview_fixed = item_by_name(preview_itinerary, "中国茶叶博物馆")
        preview_lingyin = item_by_name(preview_itinerary, "灵隐寺")
        self.assertEqual(replacement["stable_id"], target["stable_id"])
        self.assertEqual(replacement["canonical_place_id"], "amap-tea-village")
        self.assertEqual(replacement["travel_data_status"], "confirmed")
        self.assertEqual(preview_fixed["start_time"], original_fixed["start_time"])
        self.assertEqual(preview_fixed["travel_from_name"], "茶人村")
        self.assertEqual(preview_fixed["travel_data_status"], "confirmed")
        self.assertEqual(preview_lingyin, original_lingyin)

        proposal = preview.json()["proposal"]
        applied = client.post(
            f"/trips/{trip_id}/mutation-proposals/{proposal['id']}/apply",
            json={"base_revision_id": revision_id, "proposal_digest": proposal["proposal_digest"]},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "safe-replace-apply"},
        )
        self.assertEqual(applied.status_code, 200, applied.text)
        self.assertEqual(applied.json()["current_revision"]["revision_number"], 2)
        self.assertEqual(applied.json()["current_revision"]["source_type"], "swap")

        reloaded = client.get(f"/trips/{trip_id}")
        self.assertEqual(reloaded.status_code, 200)
        self.assertEqual(item_by_name(reloaded.json()["itinerary"], "茶人村")["canonical_place_id"], "amap-tea-village")

        applied_revision_id = applied.json()["current_revision"]["id"]
        undone = client.post(
            f"/trips/{trip_id}/revisions/{applied_revision_id}/undo",
            json={"base_revision_id": applied_revision_id},
            headers={"Origin": "http://testserver", "X-Idempotency-Key": "safe-replace-undo"},
        )
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertEqual(undone.json()["current_revision"]["source_type"], "mutation_undo")
        restored = client.get(f"/trips/{trip_id}").json()["itinerary"]
        restored_target = item_by_name(restored, "青芝坞餐厅")
        restored_fixed = item_by_name(restored, "中国茶叶博物馆")
        self.assertEqual(restored_target["canonical_place_id"], "amap-qingzhiwu")
        self.assertEqual(restored_fixed["travel_from_name"], "青芝坞餐厅")
        self.assertEqual(restored_fixed["travel_duration_s"], original_fixed["travel_duration_s"])

    def create_trip(self) -> tuple[TestClient, str, str, dict]:
        client = TestClient(app)
        with patch("app.trips.service.build_itinerary_response", return_value=safe_replace_itinerary()):
            created = client.post(
                "/trips/plan",
                json={
                    "itinerary_request": {
                        "city": "杭州",
                        "trip_days": 1,
                        "scenic_spots": [],
                        "restaurants": [],
                    }
                },
            )
        self.assertEqual(created.status_code, 201, created.text)
        body = created.json()
        return client, body["trip"]["id"], body["current_revision"]["id"], body["itinerary"]


def safe_replace_itinerary(*, no_outbound_slack: bool = False) -> ItineraryResponse:
    hotel = HotelStay(name="西湖边酒店", city="杭州", latitude=30.247, longitude=120.145)
    return ItineraryResponse(
        trip_days=1,
        hotel=hotel,
        planning_anchor_source=PlanningAnchorSource(
            source_type="provided_hotel",
            source_name=hotel.name,
            latitude=hotel.latitude,
            longitude=hotel.longitude,
        ),
        days=[
            DayItinerary(
                day=1,
                hotel=hotel,
                blocks=[
                    DayTimeBlock(
                        block_type=TimeBlockType.MORNING,
                        start_time=time(9, 0),
                        end_time=time(11, 0),
                        items=[
                            stop(
                                stable_id="stop-lingyin",
                                name="灵隐寺",
                                provider_place_id="amap-lingyin",
                                latitude=30.24,
                                longitude=120.102,
                                start=time(9, 0),
                                end=time(10, 30),
                                source_type=ScheduledPOISourceType.USER_SEED,
                                source_label="必去",
                                travel_from_name=hotel.name,
                                travel_duration_s=900,
                            )
                        ],
                    ),
                    DayTimeBlock(
                        block_type=TimeBlockType.AFTERNOON,
                        start_time=time(11, 0),
                        end_time=time(17, 0),
                        items=[
                            stop(
                                stable_id="stop-meal",
                                name="青芝坞餐厅",
                                provider_place_id="amap-qingzhiwu",
                                latitude=30.26049,
                                longitude=120.12745,
                                start=time(11, 0),
                                end=time(14, 0) if no_outbound_slack else time(12, 0),
                                poi_type=POIType.RESTAURANT,
                                source_type=ScheduledPOISourceType.AUTO_SEEDED_MEAL,
                                source_label="系统补充",
                                travel_from_name="灵隐寺",
                                travel_duration_s=900,
                            ),
                            stop(
                                stable_id="stop-museum",
                                name="中国茶叶博物馆",
                                provider_place_id="amap-tea-museum",
                                latitude=30.218,
                                longitude=120.104,
                                start=time(14, 0),
                                end=time(16, 0),
                                source_type=ScheduledPOISourceType.USER_FIXED,
                                source_label="固定安排",
                                travel_from_name="青芝坞餐厅",
                                travel_duration_s=1_200,
                                fixed=True,
                            ),
                        ],
                    ),
                ],
            )
        ],
    )


def stop(
    *,
    stable_id: str,
    name: str,
    provider_place_id: str,
    latitude: float,
    longitude: float,
    start: time,
    end: time,
    source_type: ScheduledPOISourceType,
    source_label: str,
    travel_from_name: str,
    travel_duration_s: int,
    poi_type: POIType = POIType.SCENIC,
    fixed: bool = False,
) -> ScheduledPOI:
    verified_place = VerifiedPlaceRef(
        stable_id=f"place-{provider_place_id}",
        original_name=name,
        canonical_name=name,
        provider="amap",
        provider_place_id=provider_place_id,
        latitude=latitude,
        longitude=longitude,
        category="中餐厅" if poi_type == POIType.RESTAURANT else "风景名胜",
    )
    return ScheduledPOI(
        stable_id=stable_id,
        name=name,
        type=poi_type,
        city="杭州",
        latitude=latitude,
        longitude=longitude,
        duration_minutes=max(1, int((end.hour * 60 + end.minute) - (start.hour * 60 + start.minute))),
        day=1,
        start_time=start,
        end_time=end,
        is_fixed=fixed,
        source_type=source_type,
        source_label=source_label,
        travel_from_name=travel_from_name,
        travel_distance_m=900,
        travel_duration_s=travel_duration_s,
        travel_calculation_status="provider_verified",
        canonical_place_id=provider_place_id,
        verified_place=verified_place,
        travel_from_place_id=None,
        travel_to_place_id=provider_place_id,
        travel_provider="amap",
        travel_data_status="confirmed",
    )


def verified_option(name: str, provider_place_id: str, latitude: float, longitude: float) -> dict:
    return {
        "stable_id": f"place-{provider_place_id}",
        "name": name,
        "type": "restaurant",
        "reasoning_summary": "它与这一段路线相邻。",
        "itinerary_relation_summary": "只替换当前午餐停留点。",
        "verified_place": {
            "stable_id": f"place-{provider_place_id}",
            "original_name": name,
            "canonical_name": name,
            "provider": "amap",
            "provider_place_id": provider_place_id,
            "latitude": latitude,
            "longitude": longitude,
            "category": "杭帮菜",
            "source_fragment_ids": [],
        },
        "route_impact": {
            "safe_to_apply": True,
            "before_duration_s": 2_100,
            "after_duration_s": 1_200,
            "delta_duration_s": -900,
            "inbound": {
                "from_name": "灵隐寺",
                "to_name": name,
                "distance_m": 800,
                "duration_s": 600,
                "provider": "amap",
                "data_status": "confirmed",
            },
            "outbound": {
                "from_name": name,
                "to_name": "中国茶叶博物馆",
                "distance_m": 800,
                "duration_s": 600,
                "provider": "amap",
                "data_status": "confirmed",
            },
        },
    }


def replacement_command(*, base_revision_id: str, stop_id: str, option: dict) -> dict:
    return {
        "schema_version": "1.0",
        "base_revision_id": base_revision_id,
        "mutation_kind": "swap",
        "commands": [
            {
                "type": "replace_stop",
                "stop_id": stop_id,
                "replacement": {
                    key: value
                    for key, value in option.items()
                    if key
                    in {
                        "name",
                        "type",
                        "reasoning_summary",
                        "itinerary_relation_summary",
                        "verified_place",
                        "route_impact",
                    }
                },
            }
        ],
    }


def item_by_name(itinerary: dict, name: str) -> dict:
    return next(
        item
        for day in itinerary["days"]
        for block in day["blocks"]
        for item in block["items"]
        if item["name"] == name
    )


if __name__ == "__main__":
    unittest.main()

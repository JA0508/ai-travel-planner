from __future__ import annotations

from datetime import time
from unittest.mock import patch

import pytest

from app.schemas import (
    DayAvailabilitySummary,
    DayItinerary,
    DayTimeBlock,
    HotelStay,
    ItineraryCompletionOption,
    ItineraryCompletionRecommendation,
    ItineraryResponse,
    MealAdjacentRouteEvidence,
    MealCoverageStatus,
    MealRole,
    MealRouteEvidence,
    PlanningAnchorSource,
    POIType,
    ScheduledPOI,
    ScheduledPOISourceType,
    TimeBlockType,
    VerifiedPlaceRef,
)
from app.schemas.plan_candidates import CandidateMetrics, ConstraintGraph, PlanCandidate
from app.schemas.trip_compiler import TravelIntent
from app.services.amap_direction import RoutePlanningError
from app.services.constraint_planning import _metrics, build_planning_snapshot_manifest
from app.services.itinerary_completion_recommendation import (
    apply_completion_recommendation_autofill,
    complete_meal_rhythm,
)
from app.services.meal_rhythm import assess_meal_rhythm, is_meal_capable_item
from app.services.poi_discovery_provider import PoiDiscoveryCandidate, PoiDiscoveryCapability


HOTEL = HotelStay(
    name="杭州住宿锚点",
    city="杭州",
    latitude=30.230,
    longitude=120.120,
)


class MealFixtureProvider:
    def __init__(self, candidates: list[PoiDiscoveryCandidate]) -> None:
        self.candidates = candidates
        self.search_calls = 0

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

    def search_text(self, *, keyword: str, city: str, offset: int):
        del keyword, city, offset
        return self.candidates

    def search_around(self, **query: object):
        del query
        self.search_calls += 1
        return self.candidates


def verified_place(
    name: str,
    provider_id: str,
    *,
    category: str,
    latitude: float,
    longitude: float,
) -> VerifiedPlaceRef:
    return VerifiedPlaceRef(
        stable_id=f"amap:{provider_id}",
        original_name=name,
        canonical_name=name,
        provider="amap",
        provider_place_id=provider_id,
        latitude=latitude,
        longitude=longitude,
        category=category,
    )


def stop(
    name: str,
    *,
    start: time,
    end: time,
    poi_type: POIType = POIType.SCENIC,
    fixed: bool = False,
    source_type: ScheduledPOISourceType = ScheduledPOISourceType.USER_SEED,
    source_label: str | None = None,
    category: str | None = None,
    latitude: float = 30.240,
    longitude: float = 120.110,
    meal_role: MealRole | None = None,
) -> ScheduledPOI:
    identity = (
        verified_place(
            name,
            f"fixture-{name}",
            category=category or ("中餐厅" if poi_type == POIType.RESTAURANT else "风景名胜"),
            latitude=latitude,
            longitude=longitude,
        )
        if category is not None
        else None
    )
    return ScheduledPOI(
        stable_id=f"stop-{name}",
        name=name,
        type=poi_type,
        city="杭州",
        latitude=latitude,
        longitude=longitude,
        duration_minutes=(end.hour * 60 + end.minute) - (start.hour * 60 + start.minute),
        day=1,
        start_time=start,
        end_time=end,
        is_fixed=fixed,
        source_type=source_type,
        source_label=source_label,
        canonical_place_id=identity.provider_place_id if identity else None,
        verified_place=identity,
        meal_role=meal_role,
    )


def itinerary(
    items: list[ScheduledPOI],
    *,
    effective_start: time = time(9, 0),
    effective_end: time = time(21, 0),
) -> ItineraryResponse:
    blocks = []
    for block_type, start_at, end_at in (
        (TimeBlockType.MORNING, time(9, 0), time(12, 0)),
        (TimeBlockType.AFTERNOON, time(13, 0), time(17, 0)),
        (TimeBlockType.EVENING, time(17, 30), time(21, 0)),
    ):
        blocks.append(
            DayTimeBlock(
                block_type=block_type,
                start_time=max(start_at, effective_start),
                end_time=min(end_at, effective_end),
                items=[
                    item
                    for item in items
                    if (
                        start_at <= item.start_time < end_at
                        or (
                            block_type == TimeBlockType.AFTERNOON
                            and time(12, 0) <= item.start_time < time(13, 0)
                        )
                    )
                ],
            )
        )
    return ItineraryResponse(
        trip_days=1,
        hotel=HOTEL,
        planning_anchor_source=PlanningAnchorSource(
            source_type="provided_hotel",
            source_name=HOTEL.name,
        ),
        days=[
            DayItinerary(
                day=1,
                hotel=HOTEL,
                availability_summary=DayAvailabilitySummary(
                    effective_start=effective_start,
                    effective_end=effective_end,
                ),
                blocks=blocks,
            )
        ],
    )


def status_for(response: ItineraryResponse, role: MealRole) -> MealCoverageStatus:
    slot = next(
        slot
        for day in response.meal_rhythm.days
        for slot in day.slots
        if slot.role == role
    )
    return slot.status


def terminal_meal_itinerary() -> ItineraryResponse:
    meal = stop(
        "湖滨晚饭",
        start=time(18, 0),
        end=time(19, 0),
        poi_type=POIType.RESTAURANT,
        source_type=ScheduledPOISourceType.AUTO_SEEDED_MEAL,
        category="餐饮服务;中餐厅",
        meal_role=MealRole.DINNER,
    ).model_copy(
        update={
            "travel_from_name": HOTEL.name,
            "travel_from_place_id": "hotel-anchor",
            "travel_to_place_id": "fixture-湖滨晚饭",
            "travel_distance_m": 700,
            "travel_duration_s": 600,
            "travel_provider": "amap",
            "travel_data_status": "confirmed",
            "meal_route_evidence": MealRouteEvidence(
                inbound=MealAdjacentRouteEvidence(
                    from_name=HOTEL.name,
                    to_name="湖滨晚饭",
                    from_place_id="hotel-anchor",
                    to_place_id="fixture-湖滨晚饭",
                    distance_m=700,
                    duration_s=600,
                ),
                outbound=MealAdjacentRouteEvidence(
                    from_name="湖滨晚饭",
                    to_name=HOTEL.name,
                    from_place_id="fixture-湖滨晚饭",
                    to_place_id="hotel-anchor",
                    distance_m=800,
                    duration_s=720,
                ),
            ),
        }
    )
    return itinerary([meal])


def test_full_day_requires_lunch_and_dinner() -> None:
    summary = assess_meal_rhythm(itinerary([]))

    assert [slot.status for slot in summary.days[0].slots] == [
        MealCoverageStatus.UNRESOLVED,
        MealCoverageStatus.UNRESOLVED,
    ]


@pytest.mark.parametrize(
    ("effective_start", "effective_end", "role", "expected"),
    [
        (time(15, 0), time(21, 0), MealRole.LUNCH, MealCoverageStatus.NOT_APPLICABLE),
        (time(9, 0), time(16, 30), MealRole.DINNER, MealCoverageStatus.NOT_APPLICABLE),
    ],
)
def test_trip_boundaries_control_meal_applicability(
    effective_start: time,
    effective_end: time,
    role: MealRole,
    expected: MealCoverageStatus,
) -> None:
    response = itinerary([], effective_start=effective_start, effective_end=effective_end)

    assert status_for(response.model_copy(update={"meal_rhythm": assess_meal_rhythm(response)}), role) == expected


def test_tea_stop_does_not_satisfy_lunch() -> None:
    tea = stop(
        "龙井茶歇",
        start=time(12, 0),
        end=time(12, 45),
        poi_type=POIType.RESTAURANT,
        category="餐饮服务;茶艺馆",
    )

    assert not is_meal_capable_item(tea)
    assert status_for(
        itinerary([tea]).model_copy(update={"meal_rhythm": assess_meal_rhythm(itinerary([tea]))}),
        MealRole.LUNCH,
    ) == MealCoverageStatus.UNRESOLVED


def test_night_market_with_broad_food_category_does_not_satisfy_dinner() -> None:
    night_market = stop(
        "武林夜市",
        start=time(18, 0),
        end=time(19, 0),
        poi_type=POIType.RESTAURANT,
        category="餐饮服务",
    )

    assert not is_meal_capable_item(night_market)
    response = itinerary([night_market])
    assessed = response.model_copy(update={"meal_rhythm": assess_meal_rhythm(response)})
    assert status_for(assessed, MealRole.DINNER) == MealCoverageStatus.UNRESOLVED


def test_fixed_user_meal_covers_lunch_without_changing_ownership() -> None:
    lunch = stop(
        "湖滨餐厅预约",
        start=time(12, 30),
        end=time(13, 30),
        poi_type=POIType.RESTAURANT,
        fixed=True,
        source_type=ScheduledPOISourceType.USER_FIXED,
        category="餐饮服务;中餐厅",
        meal_role=MealRole.LUNCH,
    )
    response = itinerary([lunch])
    completed = complete_meal_rhythm(response, poi_discovery_provider=MealFixtureProvider([]))

    assert status_for(completed, MealRole.LUNCH) == MealCoverageStatus.COVERED
    scheduled = [item for block in completed.days[0].blocks for item in block.items]
    assert scheduled == [lunch]
    assert scheduled[0].is_fixed
    assert scheduled[0].source_type == ScheduledPOISourceType.USER_FIXED


def test_existing_verified_system_food_stop_covers_lunch_without_duplicate() -> None:
    lunch = stop(
        "湖畔杭帮菜",
        start=time(12, 15),
        end=time(13, 15),
        poi_type=POIType.RESTAURANT,
        source_type=ScheduledPOISourceType.AUTO_FILLED,
        category="餐饮服务;中餐厅",
    )
    provider = MealFixtureProvider([])

    completed = complete_meal_rhythm(itinerary([lunch]), poi_discovery_provider=provider)

    assert status_for(completed, MealRole.LUNCH) == MealCoverageStatus.COVERED
    assert [
        item.name
        for block in completed.days[0].blocks
        for item in block.items
        if is_meal_capable_item(item)
    ] == ["湖畔杭帮菜"]
    assert provider.search_calls == 1  # Dinner remains independently applicable.


def test_generic_restaurant_filler_does_not_consume_an_unresolved_meal_window() -> None:
    response = itinerary([])
    response = response.model_copy(update={"meal_rhythm": assess_meal_rhythm(response)})
    recommendation = ItineraryCompletionRecommendation(
        summary="test",
        options=[
            ItineraryCompletionOption(
                name="青芝坞餐厅",
                type=POIType.RESTAURANT,
                suggested_day=1,
                suggested_block=TimeBlockType.AFTERNOON,
                reasoning_summary="test",
                itinerary_relation_summary="test",
            )
        ],
    )

    legacy_autofill = apply_completion_recommendation_autofill(
        response.model_copy(update={"meal_rhythm": None}),
        recommendation,
    )
    autofilled = apply_completion_recommendation_autofill(response, recommendation)

    legacy_afternoon = next(
        block
        for block in legacy_autofill.days[0].blocks
        if block.block_type == TimeBlockType.AFTERNOON
    )
    afternoon = next(
        block
        for block in autofilled.days[0].blocks
        if block.block_type == TimeBlockType.AFTERNOON
    )
    assert [item.name for item in legacy_afternoon.items] == ["青芝坞餐厅"]
    assert afternoon.items == []
    assert status_for(autofilled, MealRole.LUNCH) == MealCoverageStatus.UNRESOLVED


def test_system_meal_identity_is_not_reused_on_another_day() -> None:
    first_day = itinerary([]).days[0]
    second_day = first_day.model_copy(update={"day": 2})
    response = itinerary([]).model_copy(
        update={"trip_days": 2, "days": [first_day, second_day]}
    )
    provider = MealFixtureProvider([
        PoiDiscoveryCandidate(
            name="唯一可用餐厅",
            address="杭州市西湖区",
            type="餐饮服务;中餐厅",
            typecode="050100",
            business_area="杭州",
            latitude=30.229,
            longitude=120.111,
            provider_place_id="fixture-only-meal",
        )
    ])

    with patch(
        "app.services.itinerary_completion_recommendation.get_walking_route",
        return_value={"distance_m": 600, "duration_s": 480, "source": "amap_fixture"},
    ):
        completed = complete_meal_rhythm(response, poi_discovery_provider=provider)

    inserted = [
        item
        for day in completed.days
        for block in day.blocks
        for item in block.items
        if item.canonical_place_id == "fixture-only-meal"
    ]
    assert len(inserted) == 1


def test_safe_verified_lunch_is_inserted_once_and_preserves_fixed_and_must() -> None:
    must = stop(
        "灵隐寺",
        start=time(9, 0),
        end=time(11, 0),
        source_label="必去",
        category="风景名胜",
    )
    fixed = stop(
        "中国茶叶博物馆",
        start=time(15, 0),
        end=time(17, 0),
        fixed=True,
        source_type=ScheduledPOISourceType.USER_FIXED,
        category="博物馆",
        latitude=30.218,
        longitude=120.104,
    )
    candidate = PoiDiscoveryCandidate(
        name="茶人村",
        address="杭州市西湖区龙井路",
        type="餐饮服务;中餐厅",
        typecode="050100",
        business_area="杭州",
        latitude=30.229,
        longitude=120.111,
        provider_place_id="fixture-tea-village",
    )
    provider = MealFixtureProvider([candidate])

    with patch(
        "app.services.itinerary_completion_recommendation.get_walking_route",
        return_value={"distance_m": 700, "duration_s": 600, "source": "amap_fixture"},
    ):
        completed = complete_meal_rhythm(itinerary([must, fixed]), poi_discovery_provider=provider)

    lunch_items = [
        item
        for block in completed.days[0].blocks
        for item in block.items
        if item.meal_role == MealRole.LUNCH
    ]
    assert len(lunch_items) == 1
    lunch = lunch_items[0]
    assert lunch.name == "茶人村"
    assert lunch.source_type == ScheduledPOISourceType.AUTO_SEEDED_MEAL
    assert lunch.verified_place.provider_place_id == "fixture-tea-village"
    assert lunch.travel_data_status == "confirmed"
    assert lunch.meal_route_evidence.inbound.duration_s == 600
    assert lunch.meal_route_evidence.outbound.duration_s == 600
    assert time(11, 30) <= lunch.start_time < lunch.end_time <= time(14, 0)
    lunch_block = next(
        block
        for block in completed.days[0].blocks
        if any(item.meal_role == MealRole.LUNCH for item in block.items)
    )
    assert lunch_block.start_time <= lunch.start_time < lunch.end_time <= lunch_block.end_time
    assert status_for(completed, MealRole.LUNCH) == MealCoverageStatus.AUTO_COMPLETED
    unchanged = {
        item.name: (item.start_time, item.end_time, item.is_fixed, item.source_label)
        for block in completed.days[0].blocks
        for item in block.items
        if item.name in {"灵隐寺", "中国茶叶博物馆"}
    }
    assert unchanged == {
        "灵隐寺": (time(9, 0), time(11, 0), False, "必去"),
        "中国茶叶博物馆": (time(15, 0), time(17, 0), True, None),
    }

    second_pass = complete_meal_rhythm(completed, poi_discovery_provider=provider)
    assert sum(
        item.meal_role == MealRole.LUNCH
        for block in second_pass.days[0].blocks
        for item in block.items
    ) == 1


def test_safe_verified_dinner_is_inserted_inside_dinner_window() -> None:
    evening_stop = stop(
        "西湖夜游",
        start=time(19, 30),
        end=time(20, 30),
        category="风景名胜",
    )
    provider = MealFixtureProvider([
        PoiDiscoveryCandidate(
            name="湖滨晚饭",
            address="杭州市上城区湖滨",
            type="餐饮服务;中餐厅",
            typecode="050100",
            business_area="杭州",
            latitude=30.251,
            longitude=120.159,
            provider_place_id="fixture-hubin-dinner",
        )
    ])

    with patch(
        "app.services.itinerary_completion_recommendation.get_walking_route",
        return_value={"distance_m": 600, "duration_s": 480, "source": "amap_fixture"},
    ):
        completed = complete_meal_rhythm(
            itinerary([evening_stop], effective_start=time(15, 0)),
            poi_discovery_provider=provider,
        )

    dinner = next(
        item
        for block in completed.days[0].blocks
        for item in block.items
        if item.meal_role == MealRole.DINNER
    )
    assert time(17, 30) <= dinner.start_time < dinner.end_time <= time(20, 30)
    assert status_for(completed, MealRole.DINNER) == MealCoverageStatus.AUTO_COMPLETED


def test_fixed_events_consuming_lunch_window_leave_gap_without_moving() -> None:
    fixed = stop(
        "午间讲座",
        start=time(11, 30),
        end=time(14, 0),
        fixed=True,
        source_type=ScheduledPOISourceType.USER_FIXED,
        category="文化场馆",
    )
    provider = MealFixtureProvider([
        PoiDiscoveryCandidate(
            name="讲座附近餐厅",
            address="杭州市西湖区",
            type="餐饮服务;中餐厅",
            typecode="050100",
            business_area="杭州",
            latitude=30.229,
            longitude=120.111,
            provider_place_id="fixture-near-talk",
        )
    ])

    completed = complete_meal_rhythm(itinerary([fixed]), poi_discovery_provider=provider)

    assert status_for(completed, MealRole.LUNCH) == MealCoverageStatus.UNRESOLVED
    assert [(fixed.start_time, fixed.end_time, fixed.is_fixed)] == [
        (time(11, 30), time(14, 0), True)
    ]
    assert all(
        item.meal_role != MealRole.LUNCH
        for block in completed.days[0].blocks
        for item in block.items
    )
    assert any("已经留好的安排" in note for note in completed.meal_rhythm.days[0].field_notes)


def test_route_failure_leaves_an_explicit_meal_gap_without_fake_stop() -> None:
    must = stop(
        "灵隐寺",
        start=time(9, 0),
        end=time(11, 0),
        source_label="必去",
        category="风景名胜",
    )
    fixed = stop(
        "中国茶叶博物馆",
        start=time(14, 0),
        end=time(16, 0),
        fixed=True,
        source_type=ScheduledPOISourceType.USER_FIXED,
        category="博物馆",
    )
    provider = MealFixtureProvider([
        PoiDiscoveryCandidate(
            name="路线未知餐厅",
            address=None,
            type="餐饮服务;中餐厅",
            typecode="050100",
            business_area="杭州",
            latitude=30.229,
            longitude=120.111,
            provider_place_id="fixture-route-unknown",
        )
    ])

    with patch(
        "app.services.itinerary_completion_recommendation.get_walking_route",
        side_effect=RoutePlanningError("fixture route unavailable"),
    ):
        completed = complete_meal_rhythm(itinerary([must, fixed]), poi_discovery_provider=provider)

    assert status_for(completed, MealRole.LUNCH) == MealCoverageStatus.UNRESOLVED
    assert all(
        item.name != "路线未知餐厅"
        for block in completed.days[0].blocks
        for item in block.items
    )
    assert any("午饭还没找到合适的位置" in note for note in completed.meal_rhythm.days[0].field_notes)


def test_one_unavailable_adjacent_leg_rejects_meal_candidate() -> None:
    must = stop(
        "灵隐寺",
        start=time(9, 0),
        end=time(11, 0),
        source_label="必去",
        category="风景名胜",
    )
    fixed = stop(
        "中国茶叶博物馆",
        start=time(14, 0),
        end=time(16, 0),
        fixed=True,
        source_type=ScheduledPOISourceType.USER_FIXED,
        category="博物馆",
    )
    provider = MealFixtureProvider([
        PoiDiscoveryCandidate(
            name="单侧路线餐厅",
            address="杭州市西湖区",
            type="餐饮服务;中餐厅",
            typecode="050100",
            business_area="杭州",
            latitude=30.229,
            longitude=120.111,
            provider_place_id="fixture-one-sided",
        )
    ])

    with patch(
        "app.services.itinerary_completion_recommendation.get_walking_route",
        side_effect=[
            {"distance_m": 500, "duration_s": 420, "source": "amap_fixture"},
            RoutePlanningError("outbound route unavailable"),
        ],
    ):
        completed = complete_meal_rhythm(
            itinerary([must, fixed], effective_end=time(16, 30)),
            poi_discovery_provider=provider,
        )

    assert status_for(completed, MealRole.LUNCH) == MealCoverageStatus.UNRESOLVED
    assert all(
        item.name != "单侧路线餐厅"
        for block in completed.days[0].blocks
        for item in block.items
    )
    assert completed.meal_rhythm.route_calls == 2


def test_candidate_retries_in_a_later_route_context_after_an_earlier_leg_failure() -> None:
    evening_stop = stop(
        "西湖短暂停留",
        start=time(18, 30),
        end=time(19, 0),
        category="风景名胜",
        latitude=30.251,
        longitude=120.159,
    )
    provider = MealFixtureProvider([
        PoiDiscoveryCandidate(
            name="湖畔晚饭",
            address="杭州市上城区湖滨",
            type="餐饮服务;中餐厅",
            typecode="050100",
            business_area="杭州",
            latitude=30.252,
            longitude=120.160,
            provider_place_id="fixture-contextual-dinner",
        )
    ])
    confirmed_route = {"distance_m": 500, "duration_s": 420, "source": "amap_fixture"}

    with patch(
        "app.services.itinerary_completion_recommendation.get_walking_route",
        side_effect=[
            confirmed_route,
            RoutePlanningError("first gap outbound unavailable"),
            confirmed_route,
            confirmed_route,
        ],
    ):
        completed = complete_meal_rhythm(
            itinerary([evening_stop], effective_start=time(15, 0)),
            poi_discovery_provider=provider,
        )

    dinner = next(
        item
        for block in completed.days[0].blocks
        for item in block.items
        if item.meal_role == MealRole.DINNER
    )
    assert dinner.name == "湖畔晚饭"
    assert dinner.start_time >= time(19, 0)
    assert completed.meal_rhythm.route_calls == 4


def test_candidate_metrics_include_terminal_meal_return_leg() -> None:
    response = terminal_meal_itinerary()
    intent = TravelIntent(destination="杭州", trip_days=1)

    metrics = _metrics(response, intent)

    assert metrics.activity_minutes == 60
    assert metrics.total_travel_minutes == 22
    assert metrics.daily_windows[0]["travel_minutes"] == 22


def test_planning_snapshot_freezes_meal_identity_and_both_adjacent_routes() -> None:
    response = terminal_meal_itinerary()
    intent = TravelIntent(destination="杭州", trip_days=1)
    graph = ConstraintGraph(intent_digest="intent-digest", nodes=[], edges=[])
    candidate = PlanCandidate(
        id="candidate-meal",
        candidate_hash="candidate-hash",
        strategy="balanced",
        title="含晚饭的路线",
        tradeoff_summary="保留晚饭节奏",
        itinerary=response,
        constraint_graph=graph,
        metrics=CandidateMetrics(
            fixed_coverage=0,
            must_coverage=0,
            optional_coverage=0,
            total_travel_minutes=22,
            activity_minutes=60,
            max_daily_activity_minutes=60,
            free_buffer_minutes=0,
            minimum_daily_slack_minutes=0,
            rushed_day_count=0,
            infeasible_day_count=0,
            risk_count=0,
            travel_data_completeness="complete",
        ),
    )

    _manifest, poi_snapshot, route_snapshot, _strategy_manifest = build_planning_snapshot_manifest(
        intent=intent,
        graph=graph,
        candidates=[candidate],
        strategy_inputs={candidate.id: {}},
    )

    assert any(
        poi["provider_place_id"] == "fixture-湖滨晚饭"
        and poi["coordinates"] == [30.24, 120.11]
        for poi in poi_snapshot
    )
    assert {
        (segment["from_poi"], segment["to_poi"], segment["duration_seconds"])
        for segment in route_snapshot
    } == {
        (HOTEL.name, "湖滨晚饭", 600),
        ("湖滨晚饭", HOTEL.name, 720),
    }


def test_planning_snapshot_marks_opening_hours_unverified_when_scheduler_only_places_poi() -> None:
    response = terminal_meal_itinerary()
    intent = TravelIntent(destination="杭州", trip_days=1)
    graph = ConstraintGraph(intent_digest="intent-digest", nodes=[], edges=[])
    candidate = PlanCandidate(
        id="candidate-opening-hours",
        candidate_hash="candidate-hash",
        strategy="balanced",
        title="含晚饭的路线",
        tradeoff_summary="保留晚饭节奏",
        itinerary=response,
        constraint_graph=graph,
        metrics=CandidateMetrics(
            fixed_coverage=0,
            must_coverage=0,
            optional_coverage=0,
            total_travel_minutes=22,
            activity_minutes=60,
            max_daily_activity_minutes=60,
            free_buffer_minutes=0,
            minimum_daily_slack_minutes=0,
            rushed_day_count=0,
            infeasible_day_count=0,
            risk_count=0,
            travel_data_completeness="complete",
        ),
    )

    _manifest, poi_snapshot, _route_snapshot, _strategy_manifest = build_planning_snapshot_manifest(
        intent=intent,
        graph=graph,
        candidates=[candidate],
        strategy_inputs={candidate.id: {}},
    )

    assert {poi["opening_hour_status"] for poi in poi_snapshot} == {"not_verified"}


def test_planning_snapshot_does_not_duplicate_non_terminal_meal_outbound_leg() -> None:
    meal = stop(
        "茶人村",
        start=time(12, 0),
        end=time(13, 0),
        poi_type=POIType.RESTAURANT,
        source_type=ScheduledPOISourceType.AUTO_SEEDED_MEAL,
        category="餐饮服务;中餐厅",
        meal_role=MealRole.LUNCH,
    ).model_copy(
        update={
            "travel_from_name": HOTEL.name,
            "travel_from_place_id": "hotel-anchor",
            "travel_to_place_id": "fixture-茶人村",
            "travel_distance_m": 700,
            "travel_duration_s": 600,
            "travel_provider": "amap",
            "travel_data_status": "confirmed",
            "meal_route_evidence": MealRouteEvidence(
                inbound=MealAdjacentRouteEvidence(
                    from_name=HOTEL.name,
                    to_name="茶人村",
                    from_place_id="hotel-anchor",
                    to_place_id="fixture-茶人村",
                    distance_m=700,
                    duration_s=600,
                ),
                outbound=MealAdjacentRouteEvidence(
                    from_name="茶人村",
                    to_name="中国茶叶博物馆",
                    from_place_id="fixture-茶人村",
                    to_place_id="fixture-museum",
                    distance_m=650,
                    duration_s=540,
                ),
            ),
        }
    )
    museum = stop(
        "中国茶叶博物馆",
        start=time(14, 0),
        end=time(16, 0),
        fixed=True,
        source_type=ScheduledPOISourceType.USER_FIXED,
        category="博物馆",
    ).model_copy(
        update={
            "canonical_place_id": "fixture-museum",
            "travel_from_name": "茶人村",
            "travel_from_place_id": "fixture-茶人村",
            "travel_to_place_id": "fixture-museum",
            "travel_distance_m": 650,
            "travel_duration_s": 540,
            "travel_provider": "amap",
            "travel_data_status": "confirmed",
        }
    )
    response = itinerary([meal, museum], effective_end=time(17, 0))
    intent = TravelIntent(destination="杭州", trip_days=1)
    graph = ConstraintGraph(intent_digest="intent-digest", nodes=[], edges=[])
    candidate = PlanCandidate(
        id="candidate-meal-followed-by-fixed",
        candidate_hash="candidate-hash",
        strategy="balanced",
        title="午饭后接固定安排",
        tradeoff_summary="保留真实餐食路段",
        itinerary=response,
        constraint_graph=graph,
        metrics=_metrics(response, intent),
    )

    _manifest, _poi_snapshot, route_snapshot, _strategy_manifest = build_planning_snapshot_manifest(
        intent=intent,
        graph=graph,
        candidates=[candidate],
        strategy_inputs={candidate.id: {}},
    )

    assert [
        (segment["from_poi"], segment["to_poi"], segment["duration_seconds"])
        for segment in route_snapshot
    ].count(("茶人村", "中国茶叶博物馆", 540)) == 1

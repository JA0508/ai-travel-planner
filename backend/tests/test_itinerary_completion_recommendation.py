from __future__ import annotations

import unittest
from datetime import time
from unittest.mock import patch

from app.core.scheduler import Scheduler
from app.api.routes.itinerary import (
    annotate_bootstrap_items,
    build_planning_assumption_summary,
    build_sparse_city_bootstrap_pois,
)
from app.schemas import (
    AvailabilityWindow,
    DayItinerary,
    DayTimeBlock,
    HotelStay,
    ItineraryCompletionOption,
    ItineraryCompletionRecommendation,
    ItineraryRequest,
    ItineraryResponse,
    NormalizedPOI,
    POIProfile,
    PlannerPreferencePolicy,
    POIType,
    POIVisitStyle,
    PlanningAnchorSource,
    ScheduledPOI,
    ScheduledPOISourceType,
    TimeBlockType,
)
from app.services.itinerary_completion_recommendation import (
    BlockFullnessSignal,
    CandidateSpec,
    apply_completion_task_action,
    apply_completion_recommendation_autofill,
    build_completion_decision_evidence,
    build_itinerary_completion_recommendation,
    build_reasoning_summary,
    choose_candidate,
    choose_meal_repair_candidate,
    gap_supports_duration,
    infer_dominant_style_preferences,
    prioritized_autofill_options,
    repair_missing_meal_slots,
)
from app.services.nl_parser import parse_trip_text_fallback
from app.services.preference_policy import (
    StylePreferenceSignal,
    build_style_preference_signal_from_sources,
    infer_request_style_preferences,
)


class ItineraryCompletionRecommendationTests(unittest.TestCase):
    def build_manual_itinerary(
        self,
        *,
        blocks: list[DayTimeBlock],
        hotel: HotelStay | None = None,
    ) -> ItineraryResponse:
        day_hotel = hotel or HotelStay(
            name="人民广场酒店",
            city="上海",
            latitude=31.2304,
            longitude=121.4737,
        )
        return ItineraryResponse(
            trip_days=1,
            hotel=day_hotel,
            planning_anchor_source=PlanningAnchorSource(
                source_type="provided_hotel",
                source_name=day_hotel.name,
            ),
            days=[
                DayItinerary(
                    day=1,
                    hotel=day_hotel,
                    blocks=blocks,
                )
            ],
        )

    def test_sparse_city_bootstrap_creates_seed_pois_and_meals_from_preferences(self) -> None:
        scenic, restaurants = build_sparse_city_bootstrap_pois(
            city="上海",
            preferences=["轻松", "美食", "夜景"],
            needs_scenic=True,
            needs_restaurants=True,
        )

        self.assertGreaterEqual(len(scenic), 1)
        self.assertEqual(len(restaurants), 2)
        self.assertTrue(all(poi.city == "上海" for poi in scenic + restaurants))
        self.assertTrue(all(poi.latitude and poi.longitude for poi in scenic + restaurants))
        self.assertTrue(all(poi.type == POIType.RESTAURANT for poi in restaurants))

    def test_sparse_city_bootstrap_scales_meal_anchors_with_trip_days(self) -> None:
        _scenic, restaurants = build_sparse_city_bootstrap_pois(
            city="上海",
            preferences=["周末", "美食"],
            needs_scenic=False,
            needs_restaurants=True,
            target_trip_days=2,
        )

        self.assertEqual(len(restaurants), 4)
        self.assertGreaterEqual(
            sum(1 for poi in restaurants if TimeBlockType.AFTERNOON in poi.profile.best_time_blocks),
            1,
        )
        self.assertGreaterEqual(
            sum(1 for poi in restaurants if TimeBlockType.EVENING in poi.profile.best_time_blocks),
            1,
        )

    def test_meal_slot_repair_inserts_lunch_and_dinner_into_missing_blocks(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[],
                ),
                DayTimeBlock(
                    block_type=TimeBlockType.EVENING,
                    start_time=time(17, 30),
                    end_time=time(21, 0),
                    items=[],
                ),
            ],
        )

        repaired = repair_missing_meal_slots(
            itinerary,
            preference_policy=PlannerPreferencePolicy(dining_priority="high"),
            request_style_preferences=StylePreferenceSignal(explicit=frozenset({"food_stop"})),
        )
        afternoon = next(
            block for block in repaired.days[0].blocks if block.block_type == TimeBlockType.AFTERNOON
        )
        evening = next(
            block for block in repaired.days[0].blocks if block.block_type == TimeBlockType.EVENING
        )

        self.assertEqual(afternoon.items[0].type, POIType.RESTAURANT)
        self.assertEqual(evening.items[0].type, POIType.RESTAURANT)
        self.assertEqual(afternoon.items[0].source_label, "系统餐食修复")
        self.assertIn("餐食空档修复", afternoon.items[0].placement_reason or "")

    def test_meal_slot_repair_places_meals_as_route_bridges_before_existing_activity(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.MORNING,
                    start_time=time(9, 0),
                    end_time=time(12, 0),
                    items=[
                        ScheduledPOI(
                            name="上海自然博物馆",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.23349,
                            longitude=121.45862,
                            duration_minutes=120,
                            day=1,
                            start_time=time(9, 30),
                            end_time=time(11, 30),
                            is_fixed=False,
                            placement_reason="User seed placed in the morning.",
                        )
                    ],
                ),
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[
                        ScheduledPOI(
                            name="上海博物馆",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.23041,
                            longitude=121.4737,
                            duration_minutes=90,
                            day=1,
                            start_time=time(14, 30),
                            end_time=time(16, 0),
                            is_fixed=False,
                            placement_reason="User seed placed in the afternoon.",
                        )
                    ],
                ),
                DayTimeBlock(
                    block_type=TimeBlockType.EVENING,
                    start_time=time(17, 30),
                    end_time=time(21, 0),
                    items=[
                        ScheduledPOI(
                            name="南京路步行街",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.23612,
                            longitude=121.48097,
                            duration_minutes=60,
                            day=1,
                            start_time=time(19, 0),
                            end_time=time(20, 0),
                            is_fixed=False,
                            placement_reason="Night activity already planned.",
                        )
                    ],
                ),
            ],
        )

        repaired = repair_missing_meal_slots(
            itinerary,
            preference_policy=PlannerPreferencePolicy(dining_priority="high"),
            request_style_preferences=StylePreferenceSignal(explicit=frozenset({"food_stop"})),
        )
        afternoon = next(
            block for block in repaired.days[0].blocks if block.block_type == TimeBlockType.AFTERNOON
        )
        evening = next(
            block for block in repaired.days[0].blocks if block.block_type == TimeBlockType.EVENING
        )
        lunch = next(item for item in afternoon.items if item.type == POIType.RESTAURANT)
        dinner = next(item for item in evening.items if item.type == POIType.RESTAURANT)
        afternoon_anchor = next(item for item in afternoon.items if item.name == "上海博物馆")
        evening_anchor = next(item for item in evening.items if item.name == "南京路步行街")

        self.assertLessEqual(lunch.end_time, afternoon_anchor.start_time)
        self.assertLessEqual(dinner.end_time, evening_anchor.start_time)
        self.assertEqual(lunch.travel_from_name, "上海自然博物馆")
        self.assertEqual(dinner.travel_from_name, "上海博物馆")
        self.assertIn("上海自然博物馆 和 上海博物馆", lunch.placement_reason or "")
        self.assertIn("上海博物馆 和 南京路步行街", dinner.placement_reason or "")
        self.assertIn("距上一站约", lunch.placement_reason or "")
        self.assertIn("去下一站约", dinner.placement_reason or "")
        self.assertIn("餐食停靠风格", lunch.placement_reason or "")

    def test_meal_repair_candidate_ranking_uses_explicit_food_related_style_when_route_is_close(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.EVENING,
                    start_time=time(17, 30),
                    end_time=time(21, 0),
                    items=[],
                )
            ],
        )
        target_block = itinerary.days[0].blocks[0]
        candidates = [
            CandidateSpec(
                name="普通晚餐",
                type=POIType.RESTAURANT,
                block_types=(TimeBlockType.EVENING,),
                areas=("people_square",),
                themes=("street_food",),
                duration_minutes=60,
                profile_intensity="medium",
                latitude=31.2304,
                longitude=121.4737,
            ),
            CandidateSpec(
                name="江边夜市晚餐",
                type=POIType.RESTAURANT,
                block_types=(TimeBlockType.EVENING,),
                areas=("people_square",),
                themes=("street_food", "night", "waterfront"),
                duration_minutes=60,
                profile_intensity="medium",
                latitude=31.2304,
                longitude=121.4737,
            ),
        ]

        selected = choose_meal_repair_candidate(
            candidates=candidates,
            day_details=itinerary.days[0],
            target_block=target_block,
            block_type=TimeBlockType.EVENING,
            existing_names=set(),
            used_names=set(),
            day_signal=(set(), set()),
            trip_signal=(set(), set()),
            day_centroid=None,
            trip_centroid=None,
            style_preferences=StylePreferenceSignal(explicit=frozenset({"night_view"})),
            preference_policy=PlannerPreferencePolicy(dining_priority="high"),
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "江边夜市晚餐")

    def test_completion_task_action_repairs_meal_anchor_only_for_target_block(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[],
                ),
                DayTimeBlock(
                    block_type=TimeBlockType.EVENING,
                    start_time=time(17, 30),
                    end_time=time(21, 0),
                    items=[],
                ),
            ],
        )

        result = apply_completion_task_action(
            itinerary=itinerary,
            task_id="repair_meal_anchor",
            day=1,
            block_type=TimeBlockType.AFTERNOON,
            preference_policy=PlannerPreferencePolicy(dining_priority="high"),
            request_style_preferences=StylePreferenceSignal(explicit=frozenset({"food_stop"})),
        )
        afternoon = next(
            block for block in result.itinerary.days[0].blocks if block.block_type == TimeBlockType.AFTERNOON
        )
        evening = next(
            block for block in result.itinerary.days[0].blocks if block.block_type == TimeBlockType.EVENING
        )

        self.assertTrue(result.applied)
        self.assertIsNotNone(result.inserted_item)
        self.assertEqual(afternoon.items[0].type, POIType.RESTAURANT)
        self.assertEqual(afternoon.items[0].source_label, "补全任务：餐食锚点")
        self.assertEqual(evening.items, [])

    def test_completion_task_action_repairs_evening_close_with_night_or_food_candidate(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[
                        ScheduledPOI(
                            name="上海博物馆",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.23041,
                            longitude=121.4737,
                            duration_minutes=90,
                            day=1,
                            start_time=time(14, 0),
                            end_time=time(15, 30),
                            is_fixed=False,
                        )
                    ],
                ),
                DayTimeBlock(
                    block_type=TimeBlockType.EVENING,
                    start_time=time(17, 30),
                    end_time=time(21, 0),
                    items=[],
                ),
            ],
        )

        result = apply_completion_task_action(
            itinerary=itinerary,
            task_id="repair_evening_close",
            day=1,
            preference_policy=PlannerPreferencePolicy(dining_priority="high"),
            request_style_preferences=StylePreferenceSignal(explicit=frozenset({"night_view"})),
        )
        evening = next(
            block for block in result.itinerary.days[0].blocks if block.block_type == TimeBlockType.EVENING
        )

        self.assertTrue(result.applied)
        self.assertGreaterEqual(len(evening.items), 1)
        self.assertEqual(evening.items[0].source_label, "补全任务：夜间收口")
        self.assertIn(evening.items[0].type, {POIType.RESTAURANT, POIType.SCENIC})

    def test_completion_task_action_repairs_sparse_block_with_route_aware_candidate(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.MORNING,
                    start_time=time(9, 0),
                    end_time=time(12, 0),
                    items=[],
                ),
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[],
                ),
            ],
        )

        result = apply_completion_task_action(
            itinerary=itinerary,
            task_id="repair_sparse_block",
            day=1,
            block_type=TimeBlockType.MORNING,
        )
        morning = next(
            block for block in result.itinerary.days[0].blocks if block.block_type == TimeBlockType.MORNING
        )

        self.assertTrue(result.applied)
        self.assertIsNotNone(result.inserted_item)
        self.assertEqual(morning.items[0].source_label, "补全任务：空档修复")

    def test_bootstrap_items_are_annotated_for_frontend_ownership_surface(self) -> None:
        scenic, restaurants = build_sparse_city_bootstrap_pois(
            city="上海",
            preferences=["美食", "夜景"],
            needs_scenic=True,
            needs_restaurants=True,
        )
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[
                        ScheduledPOI(
                            name=scenic[0].name,
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=scenic[0].latitude,
                            longitude=scenic[0].longitude,
                            duration_minutes=scenic[0].duration_minutes,
                            day=1,
                            start_time=time(13, 0),
                            end_time=time(14, 15),
                            is_fixed=False,
                            placement_reason="Placed by scheduler.",
                        ),
                        ScheduledPOI(
                            name=restaurants[0].name,
                            type=POIType.RESTAURANT,
                            city="上海",
                            latitude=restaurants[0].latitude,
                            longitude=restaurants[0].longitude,
                            duration_minutes=restaurants[0].duration_minutes,
                            day=1,
                            start_time=time(14, 30),
                            end_time=time(15, 30),
                            is_fixed=False,
                            placement_reason=None,
                        ),
                    ],
                )
            ],
        )

        annotate_bootstrap_items(
            itinerary=itinerary,
            bootstrap_scenic=scenic,
            bootstrap_restaurants=restaurants,
        )

        items = itinerary.days[0].blocks[0].items
        self.assertIn("补入这个地点", items[0].placement_reason or "")
        self.assertIn("Placed by scheduler", items[0].placement_reason or "")
        self.assertEqual(items[0].source_type, ScheduledPOISourceType.AUTO_SEEDED_POI)
        self.assertEqual(items[0].source_label, "系统补点")
        self.assertIn("餐食锚点", items[1].placement_reason or "")
        self.assertEqual(items[1].source_type, ScheduledPOISourceType.AUTO_SEEDED_MEAL)
        self.assertEqual(items[1].source_label, "系统餐食锚点")

    def test_planning_assumption_summary_tracks_source_counts(self) -> None:
        scenic, restaurants = build_sparse_city_bootstrap_pois(
            city="上海",
            preferences=["轻松", "美食"],
            needs_scenic=True,
            needs_restaurants=True,
        )
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[
                        ScheduledPOI(
                            name=scenic[0].name,
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=scenic[0].latitude,
                            longitude=scenic[0].longitude,
                            duration_minutes=scenic[0].duration_minutes,
                            day=1,
                            start_time=time(13, 0),
                            end_time=time(14, 15),
                            is_fixed=False,
                            source_type=ScheduledPOISourceType.AUTO_SEEDED_POI,
                        ),
                        ScheduledPOI(
                            name="系统补空档",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.23,
                            longitude=121.47,
                            duration_minutes=60,
                            day=1,
                            start_time=time(15, 0),
                            end_time=time(16, 0),
                            is_fixed=False,
                            source_type=ScheduledPOISourceType.AUTO_FILLED,
                        ),
                        ScheduledPOI(
                            name=restaurants[0].name,
                            type=POIType.RESTAURANT,
                            city="上海",
                            latitude=restaurants[0].latitude,
                            longitude=restaurants[0].longitude,
                            duration_minutes=restaurants[0].duration_minutes,
                            day=1,
                            start_time=time(16, 10),
                            end_time=time(17, 0),
                            is_fixed=False,
                            source_type=ScheduledPOISourceType.AUTO_SEEDED_MEAL,
                            source_reason="系统补入这个餐食锚点，让午餐或晚餐成为路线节奏的一部分。",
                        ),
                    ],
                )
            ],
        )

        summary = build_planning_assumption_summary(
            payload=ItineraryRequest(
                city="上海",
                scenic_spots=[{"name": "外滩"}],
                restaurants=[
                    {
                        "name": "晚餐预约",
                        "fixed_day": 1,
                        "fixed_time_start": "18:00",
                        "fixed_time_end": "19:30",
                    }
                ],
                availability_windows=[
                    AvailabilityWindow(day=1, label="晚到", available_start="13:00", available_end="21:00")
                ],
                preferences=["轻松", "美食"],
                trip_days=None,
            ),
            itinerary=itinerary,
            bootstrap_scenic=scenic,
            bootstrap_restaurants=restaurants,
        )

        self.assertEqual(summary.destination, "上海")
        self.assertEqual(summary.trip_days_basis, "scheduler_estimated")
        self.assertEqual(summary.user_seed_scenic_count, 1)
        self.assertEqual(summary.user_seed_restaurant_count, 0)
        self.assertEqual(summary.fixed_event_count, 1)
        self.assertEqual(summary.availability_window_count, 1)
        self.assertEqual(summary.auto_seeded_poi_count, len(scenic))
        self.assertEqual(summary.auto_seeded_meal_count, len(restaurants))
        self.assertEqual(summary.auto_filled_count, 1)
        self.assertTrue(summary.meal_structure_applied)
        self.assertEqual(len(summary.execution_trace), 3)
        self.assertEqual(
            [item.source_type for item in summary.execution_trace],
            [
                ScheduledPOISourceType.AUTO_SEEDED_POI,
                ScheduledPOISourceType.AUTO_FILLED,
                ScheduledPOISourceType.AUTO_SEEDED_MEAL,
            ],
        )
        meal_trace = next(
            item
            for item in summary.execution_trace
            if item.source_type == ScheduledPOISourceType.AUTO_SEEDED_MEAL
        )
        self.assertEqual(
            meal_trace.decision_type,
            "system_meal_completion",
        )
        self.assertEqual(meal_trace.decision_stage, "sparse_brief_bootstrap")
        self.assertEqual(meal_trace.ownership_type, "system_auto_seeded_meal")
        self.assertEqual(meal_trace.timing_role, "lunch_anchor")
        self.assertFalse(meal_trace.is_user_owned)
        self.assertFalse(meal_trace.is_hard_constraint)
        self.assertTrue(meal_trace.is_editable)
        self.assertIn("午餐或晚餐锚点", meal_trace.evidence.why_included)
        self.assertIn("午餐锚点", meal_trace.evidence.timing_decision)
        self.assertIn("餐食锚点", meal_trace.summary)
        self.assertIsNotNone(summary.trip_scope_estimate)
        self.assertEqual(summary.trip_scope_estimate.estimated_trip_days, 2)
        self.assertEqual(summary.trip_scope_estimate.estimation_mode.value, "estimated")
        self.assertEqual(summary.trip_scope_estimate.poi_load_level.value, "light")
        self.assertIsNotNone(summary.regeneration_intent)
        self.assertEqual(summary.regeneration_intent.flexible_scenic_spots, ["外滩"])
        self.assertEqual(summary.regeneration_intent.flexible_restaurants, [])
        self.assertEqual(summary.regeneration_intent.fixed_events[0].name, "晚餐预约")
        self.assertEqual(summary.regeneration_intent.fixed_events[0].category, "restaurant")
        self.assertEqual(summary.regeneration_intent.auto_seeded_scenic_spots, [poi.name for poi in scenic])
        self.assertEqual(summary.regeneration_intent.auto_seeded_restaurants, [poi.name for poi in restaurants])
        self.assertEqual(
            summary.regeneration_intent.carry_forward_scenic_spots,
            ["外滩", *[poi.name for poi in scenic]],
        )
        self.assertEqual(
            summary.regeneration_intent.carry_forward_restaurants,
            [poi.name for poi in restaurants],
        )
        self.assertGreaterEqual(len(summary.regeneration_intent.notes), 2)

    def test_planning_decision_trace_unifies_user_fixed_seed_and_system_completion(
        self,
    ) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.MORNING,
                    start_time=time(9, 0),
                    end_time=time(12, 0),
                    items=[
                        ScheduledPOI(
                            name="外滩",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.238235,
                            longitude=121.497253,
                            duration_minutes=90,
                            day=1,
                            start_time=time(9, 0),
                            end_time=time(10, 30),
                            is_fixed=False,
                            source_type=ScheduledPOISourceType.USER_SEED,
                        ),
                        ScheduledPOI(
                            name="展览预约",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.2304,
                            longitude=121.4737,
                            duration_minutes=60,
                            day=1,
                            start_time=time(10, 45),
                            end_time=time(11, 45),
                            is_fixed=True,
                            source_type=ScheduledPOISourceType.USER_FIXED,
                        ),
                    ],
                ),
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[
                        ScheduledPOI(
                            name="系统补点",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.23,
                            longitude=121.47,
                            duration_minutes=60,
                            day=1,
                            start_time=time(13, 0),
                            end_time=time(14, 0),
                            is_fixed=False,
                            source_type=ScheduledPOISourceType.AUTO_SEEDED_POI,
                        ),
                        ScheduledPOI(
                            name="系统补午餐",
                            type=POIType.RESTAURANT,
                            city="上海",
                            latitude=31.23,
                            longitude=121.47,
                            duration_minutes=60,
                            day=1,
                            start_time=time(14, 15),
                            end_time=time(15, 15),
                            is_fixed=False,
                            source_type=ScheduledPOISourceType.AUTO_SEEDED_MEAL,
                        ),
                        ScheduledPOI(
                            name="系统补空档",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.23,
                            longitude=121.47,
                            duration_minutes=60,
                            day=1,
                            start_time=time(15, 30),
                            end_time=time(16, 30),
                            is_fixed=False,
                            source_type=ScheduledPOISourceType.AUTO_FILLED,
                        ),
                    ],
                ),
            ],
        )

        summary = build_planning_assumption_summary(
            payload=ItineraryRequest(
                city="上海",
                scenic_spots=[
                    {"name": "外滩"},
                    {
                        "name": "展览预约",
                        "fixed_day": 1,
                        "fixed_time_start": "10:45",
                        "fixed_time_end": "11:45",
                    },
                ],
                restaurants=[],
            ),
            itinerary=itinerary,
            bootstrap_scenic=[],
            bootstrap_restaurants=[],
        )

        trace_by_source = {item.source_type: item for item in summary.execution_trace}
        self.assertEqual(len(summary.execution_trace), 5)
        for source_type in (
            ScheduledPOISourceType.USER_SEED,
            ScheduledPOISourceType.USER_FIXED,
            ScheduledPOISourceType.AUTO_SEEDED_POI,
            ScheduledPOISourceType.AUTO_SEEDED_MEAL,
            ScheduledPOISourceType.AUTO_FILLED,
        ):
            self.assertIn(source_type, trace_by_source)
            self.assertTrue(trace_by_source[source_type].evidence.why_included)
            self.assertTrue(trace_by_source[source_type].evidence.timing_decision)
            self.assertTrue(trace_by_source[source_type].evidence.ownership_signal)
            self.assertTrue(trace_by_source[source_type].evidence.flexibility)

        self.assertTrue(trace_by_source[ScheduledPOISourceType.USER_FIXED].is_hard_constraint)
        self.assertTrue(trace_by_source[ScheduledPOISourceType.USER_SEED].is_user_owned)
        self.assertFalse(trace_by_source[ScheduledPOISourceType.AUTO_FILLED].is_user_owned)
        self.assertEqual(
            trace_by_source[ScheduledPOISourceType.AUTO_SEEDED_MEAL].timing_role,
            "lunch_anchor",
        )

    def test_choose_candidate_prefers_lower_friction_fit_when_route_signal_ties(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(15, 0),
                    items=[],
                )
            ]
        )
        target_block = itinerary.days[0].blocks[0]
        candidates = [
            CandidateSpec(
                name="Long option",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("test_area",),
                themes=("test_theme",),
                duration_minutes=90,
                profile_intensity="medium",
                latitude=31.2200,
                longitude=121.4700,
            ),
            CandidateSpec(
                name="Short option",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("test_area",),
                themes=("test_theme",),
                duration_minutes=60,
                profile_intensity="medium",
                latitude=31.2200,
                longitude=121.4700,
            ),
        ]

        selected = choose_candidate(
            candidates=candidates,
            day_details=itinerary.days[0],
            target_block=target_block,
            block_type=TimeBlockType.AFTERNOON,
            existing_names=set(),
            used_names=set(),
            day_signal=(set(), set()),
            trip_signal=(set(), set()),
            day_centroid=None,
            trip_centroid=None,
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "Short option")

    def test_choose_candidate_prefers_preference_aligned_option_when_scores_are_close(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(16, 0),
                    items=[],
                )
            ]
        )
        target_block = itinerary.days[0].blocks[0]
        candidates = [
            CandidateSpec(
                name="City museum stop",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("test_area",),
                themes=("museum",),
                duration_minutes=90,
                profile_intensity="heavy",
                latitude=31.2200,
                longitude=121.4700,
            ),
            CandidateSpec(
                name="Generic plaza stop",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("test_area",),
                themes=(),
                duration_minutes=90,
                profile_intensity="medium",
                latitude=31.2200,
                longitude=121.4700,
            ),
        ]

        selected = choose_candidate(
            candidates=candidates,
            day_details=itinerary.days[0],
            target_block=target_block,
            block_type=TimeBlockType.AFTERNOON,
            existing_names=set(),
            used_names=set(),
            day_signal=(set(), set()),
            trip_signal=(set(), set()),
            day_centroid=None,
            trip_centroid=None,
            preference_policy=PlannerPreferencePolicy(scenic_priority="high"),
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "City museum stop")

    def test_choose_candidate_prefers_museum_aligned_option_from_museum_heavy_trip_context(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.MORNING,
                    start_time=time(9, 0),
                    end_time=time(12, 0),
                    items=[],
                )
            ]
        )
        target_block = itinerary.days[0].blocks[0]
        style_preferences = infer_dominant_style_preferences(
            [
                ScheduledPOI(
                    name="上海博物馆",
                    type=POIType.SCENIC,
                    city="上海",
                    latitude=31.23041,
                    longitude=121.4737,
                    duration_minutes=120,
                    day=1,
                    start_time=time(13, 0),
                    end_time=time(15, 0),
                    is_fixed=False,
                )
            ]
        )
        candidates = [
            CandidateSpec(
                name="上海自然博物馆",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.MORNING,),
                areas=("people_square",),
                themes=(),
                duration_minutes=90,
                profile_intensity="heavy",
                latitude=31.2200,
                longitude=121.4700,
            ),
            CandidateSpec(
                name="思南公馆",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.MORNING,),
                areas=("french_concession",),
                themes=(),
                duration_minutes=90,
                profile_intensity="medium",
                latitude=31.2200,
                longitude=121.4700,
            ),
        ]

        selected = choose_candidate(
            candidates=candidates,
            day_details=itinerary.days[0],
            target_block=target_block,
            block_type=TimeBlockType.MORNING,
            existing_names=set(),
            used_names=set(),
            day_signal=(set(), set()),
            trip_signal=(set(), set()),
            style_preferences=style_preferences,
            day_centroid=None,
            trip_centroid=None,
        )

        self.assertEqual(style_preferences, {"museum"})
        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "上海自然博物馆")

    def test_choose_candidate_prefers_request_style_aligned_option_when_explicit(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[],
                )
            ]
        )
        target_block = itinerary.days[0].blocks[0]
        style_preferences = infer_request_style_preferences(
            ["想多看博物馆和展览"],
            scenic_spots=[],
            restaurants=[],
        )
        candidates = [
            CandidateSpec(
                name="上海自然博物馆",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("people_square",),
                themes=(),
                duration_minutes=90,
                profile_intensity="heavy",
                latitude=31.2200,
                longitude=121.4700,
            ),
            CandidateSpec(
                name="思南公馆",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("french_concession",),
                themes=(),
                duration_minutes=75,
                profile_intensity="medium",
                latitude=31.2200,
                longitude=121.4700,
            ),
        ]

        selected = choose_candidate(
            candidates=candidates,
            day_details=itinerary.days[0],
            target_block=target_block,
            block_type=TimeBlockType.AFTERNOON,
            existing_names=set(),
            used_names=set(),
            day_signal=(set(), set()),
            trip_signal=(set(), set()),
            style_preferences=style_preferences,
            day_centroid=None,
            trip_centroid=None,
        )

        self.assertEqual(style_preferences, {"museum"})
        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "上海自然博物馆")

    def test_choose_candidate_consumes_parsed_request_style_preferences(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[],
                )
            ]
        )
        target_block = itinerary.days[0].blocks[0]
        parsed = parse_trip_text_fallback(
            """
            城市: 上海
            偏好: 博物馆, 展览
            景点: 上海博物馆
            """
        )
        candidates = [
            CandidateSpec(
                name="上海自然博物馆",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("people_square",),
                themes=(),
                duration_minutes=90,
                profile_intensity="heavy",
                latitude=31.2200,
                longitude=121.4700,
            ),
            CandidateSpec(
                name="思南公馆",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("french_concession",),
                themes=(),
                duration_minutes=75,
                profile_intensity="medium",
                latitude=31.2200,
                longitude=121.4700,
            ),
        ]

        parsed_style_signal = build_style_preference_signal_from_sources(
            parsed.style_preference_sources
        )

        selected = choose_candidate(
            candidates=candidates,
            day_details=itinerary.days[0],
            target_block=target_block,
            block_type=TimeBlockType.AFTERNOON,
            existing_names=set(),
            used_names=set(),
            day_signal=(set(), set()),
            trip_signal=(set(), set()),
            style_preferences=parsed_style_signal,
            day_centroid=None,
            trip_centroid=None,
        )

        self.assertEqual(parsed.style_preferences, ["museum"])
        self.assertEqual(parsed_style_signal.source_for("museum"), "explicit")
        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "上海自然博物馆")

    def test_choose_candidate_consumes_inferred_style_source_without_reconstruction(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[],
                )
            ]
        )
        target_block = itinerary.days[0].blocks[0]
        parsed = parse_trip_text_fallback(
            """
            城市: 上海
            景点: 上海博物馆, 上海自然博物馆
            """
        )
        candidates = [
            CandidateSpec(
                name="上海自然博物馆",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("people_square",),
                themes=(),
                duration_minutes=90,
                profile_intensity="heavy",
                latitude=31.2200,
                longitude=121.4700,
            ),
            CandidateSpec(
                name="思南公馆",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("french_concession",),
                themes=(),
                duration_minutes=75,
                profile_intensity="medium",
                latitude=31.2200,
                longitude=121.4700,
            ),
        ]

        selected = choose_candidate(
            candidates=candidates,
            day_details=itinerary.days[0],
            target_block=target_block,
            block_type=TimeBlockType.AFTERNOON,
            existing_names=set(),
            used_names=set(),
            day_signal=(set(), set()),
            trip_signal=(set(), set()),
            style_preferences=build_style_preference_signal_from_sources(
                parsed.style_preference_sources
            ),
            day_centroid=None,
            trip_centroid=None,
        )

        self.assertEqual(parsed.style_preference_sources, {"museum": "inferred"})
        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "上海自然博物馆")

    def test_choose_candidate_prefers_explicit_style_over_inferred_style_when_close(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[],
                )
            ]
        )
        target_block = itinerary.days[0].blocks[0]
        style_signal = StylePreferenceSignal(
            explicit=frozenset({"food_stop"}),
            inferred=frozenset({"museum"}),
        )
        candidates = [
            CandidateSpec(
                name="Museum aligned option",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=(),
                themes=("museum",),
                duration_minutes=60,
                profile_intensity="medium",
                latitude=31.2200,
                longitude=121.4700,
            ),
            CandidateSpec(
                name="Food aligned option",
                type=POIType.RESTAURANT,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=(),
                themes=("street_food",),
                duration_minutes=60,
                profile_intensity="medium",
                latitude=31.2200,
                longitude=121.4700,
            ),
        ]

        selected = choose_candidate(
            candidates=candidates,
            day_details=itinerary.days[0],
            target_block=target_block,
            block_type=TimeBlockType.AFTERNOON,
            existing_names=set(),
            used_names=set(),
            day_signal=(set(), set()),
            trip_signal=(set(), set()),
            style_preferences=style_signal,
            day_centroid=None,
            trip_centroid=None,
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "Food aligned option")

    def test_choose_candidate_prefers_wandering_aligned_option_from_wandering_trip_context(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[],
                )
            ]
        )
        target_block = itinerary.days[0].blocks[0]
        style_preferences = infer_dominant_style_preferences(
            [
                ScheduledPOI(
                    name="思南公馆",
                    type=POIType.SCENIC,
                    city="上海",
                    latitude=31.21992,
                    longitude=121.46753,
                    duration_minutes=75,
                    day=1,
                    start_time=time(14, 0),
                    end_time=time(15, 15),
                    is_fixed=False,
                )
            ]
        )
        candidates = [
            CandidateSpec(
                name="新天地",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("french_concession",),
                themes=(),
                duration_minutes=75,
                profile_intensity="medium",
                latitude=31.2200,
                longitude=121.4700,
            ),
            CandidateSpec(
                name="上海自然博物馆",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("people_square",),
                themes=(),
                duration_minutes=90,
                profile_intensity="heavy",
                latitude=31.2200,
                longitude=121.4700,
            ),
        ]

        selected = choose_candidate(
            candidates=candidates,
            day_details=itinerary.days[0],
            target_block=target_block,
            block_type=TimeBlockType.AFTERNOON,
            existing_names=set(),
            used_names=set(),
            day_signal=(set(), set()),
            trip_signal=(set(), set()),
            style_preferences=style_preferences,
            day_centroid=None,
            trip_centroid=None,
        )

        self.assertEqual(style_preferences, {"old_street"})
        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "新天地")

    def test_choose_candidate_keeps_strong_route_advantage_over_preference_alignment(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(16, 0),
                    items=[],
                )
            ]
        )
        target_block = itinerary.days[0].blocks[0]
        candidates = [
            CandidateSpec(
                name="Food aligned option",
                type=POIType.RESTAURANT,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=(),
                themes=("street_food",),
                duration_minutes=60,
                profile_intensity="medium",
                latitude=31.2100,
                longitude=121.4600,
            ),
            CandidateSpec(
                name="Route matched scenic",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("french_concession",),
                themes=("design",),
                duration_minutes=60,
                profile_intensity="medium",
                latitude=31.2200,
                longitude=121.4700,
            ),
        ]

        selected = choose_candidate(
            candidates=candidates,
            day_details=itinerary.days[0],
            target_block=target_block,
            block_type=TimeBlockType.AFTERNOON,
            existing_names=set(),
            used_names=set(),
            day_signal=({"french_concession"}, {"design"}),
            trip_signal=(set(), set()),
            day_centroid=None,
            trip_centroid=None,
            preference_policy=PlannerPreferencePolicy(dining_priority="high"),
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "Route matched scenic")

    def test_choose_candidate_keeps_strong_route_advantage_over_style_preference(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(16, 0),
                    items=[],
                )
            ]
        )
        target_block = itinerary.days[0].blocks[0]
        style_preferences = infer_dominant_style_preferences(
            [
                ScheduledPOI(
                    name="上海博物馆",
                    type=POIType.SCENIC,
                    city="上海",
                    latitude=31.23041,
                    longitude=121.4737,
                    duration_minutes=120,
                    day=1,
                    start_time=time(9, 0),
                    end_time=time(11, 0),
                    is_fixed=False,
                )
            ]
        )
        candidates = [
            CandidateSpec(
                name="上海自然博物馆",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=(),
                themes=(),
                duration_minutes=90,
                profile_intensity="heavy",
                latitude=31.2100,
                longitude=121.4600,
            ),
            CandidateSpec(
                name="Route matched scenic",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("french_concession",),
                themes=("design",),
                duration_minutes=90,
                profile_intensity="medium",
                latitude=31.2200,
                longitude=121.4700,
            ),
        ]

        selected = choose_candidate(
            candidates=candidates,
            day_details=itinerary.days[0],
            target_block=target_block,
            block_type=TimeBlockType.AFTERNOON,
            existing_names=set(),
            used_names=set(),
            day_signal=({"french_concession"}, {"design"}),
            trip_signal=(set(), set()),
            style_preferences=style_preferences,
            day_centroid=None,
            trip_centroid=None,
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "Route matched scenic")

    def test_reasoning_summary_mentions_museum_focused_day_rhythm(self) -> None:
        reasoning = build_reasoning_summary(
            day=1,
            block_type=TimeBlockType.MORNING,
            candidate=CandidateSpec(
                name="上海自然博物馆",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.MORNING,),
                areas=("people_square",),
                themes=("museum",),
                duration_minutes=90,
                profile_intensity="heavy",
            ),
            day_signal=(set(), {"museum"}),
            fullness_signal=BlockFullnessSignal(
                block_type=TimeBlockType.MORNING,
                occupied_minutes=0,
                meaningful=False,
                underfilled=False,
            ),
            sparse_day_rank=0,
            sparse_day_count=1,
            day_fullness_signals=[],
        )

        self.assertIn("上午时段仍然为空", reasoning)
        self.assertIn("文化路线", reasoning)
        self.assertNotIn("asked for", reasoning)

    def test_reasoning_summary_mentions_old_street_wandering_feel_when_aligned(self) -> None:
        reasoning = build_reasoning_summary(
            day=1,
            block_type=TimeBlockType.AFTERNOON,
            candidate=CandidateSpec(
                name="思南公馆",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("french_concession",),
                themes=("design", "old_street"),
                duration_minutes=75,
                profile_intensity="medium",
            ),
            day_signal=(set(), {"design", "old_street"}),
            fullness_signal=BlockFullnessSignal(
                block_type=TimeBlockType.AFTERNOON,
                occupied_minutes=0,
                meaningful=False,
                underfilled=False,
            ),
            sparse_day_rank=0,
            sparse_day_count=1,
            day_fullness_signals=[],
        )

        self.assertIn("下午时段仍然为空", reasoning)
        self.assertIn(
            "老街漫游感",
            reasoning,
        )

    def test_reasoning_summary_mentions_lighter_food_stop_rhythm_when_aligned(self) -> None:
        reasoning = build_reasoning_summary(
            day=1,
            block_type=TimeBlockType.EVENING,
            candidate=CandidateSpec(
                name="城隍庙小吃街",
                type=POIType.RESTAURANT,
                block_types=(TimeBlockType.EVENING,),
                areas=("old_town",),
                themes=("street_food", "night"),
                duration_minutes=60,
                profile_intensity="medium",
            ),
            day_signal=(set(), {"street_food", "night"}),
            fullness_signal=BlockFullnessSignal(
                block_type=TimeBlockType.EVENING,
                occupied_minutes=0,
                meaningful=False,
                underfilled=False,
            ),
            sparse_day_rank=0,
            sparse_day_count=1,
            day_fullness_signals=[],
        )

        self.assertIn("夜间时段仍然为空", reasoning)
        self.assertIn(
            "餐食停靠节奏",
            reasoning,
        )

    def test_reasoning_summary_explains_gap_fit_and_rejected_alternatives(self) -> None:
        candidate = CandidateSpec(
            name="人民广场本帮菜午餐",
            type=POIType.RESTAURANT,
            block_types=(TimeBlockType.AFTERNOON,),
            areas=("people_square",),
            themes=("street_food",),
            duration_minutes=60,
            profile_intensity="medium",
            latitude=31.2304,
            longitude=121.4737,
        )
        day_items = [
            ScheduledPOI(
                name="上海博物馆",
                type=POIType.SCENIC,
                city="上海",
                latitude=31.23041,
                longitude=121.4737,
                duration_minutes=120,
                day=1,
                start_time=time(9, 30),
                end_time=time(11, 30),
                is_fixed=False,
            )
        ]
        candidate_pool = [
            CandidateSpec(
                name="上海自然博物馆",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("jingan",),
                themes=("museum",),
                duration_minutes=90,
                profile_intensity="heavy",
            )
        ]
        fullness_signal = BlockFullnessSignal(
            block_type=TimeBlockType.AFTERNOON,
            occupied_minutes=0,
            meaningful=False,
            underfilled=True,
        )
        reasoning = build_reasoning_summary(
            day=1,
            block_type=TimeBlockType.AFTERNOON,
            candidate=candidate,
            day_items=day_items,
            candidate_pool=[candidate, *candidate_pool],
            day_signal=({"people_square"}, set()),
            fullness_signal=fullness_signal,
            sparse_day_rank=0,
            sparse_day_count=1,
            day_fullness_signals=[],
        )

        self.assertIn("下午时段仍然为空", reasoning)
        self.assertIn("约", reasoning)
        self.assertIn("午餐锚点", reasoning)
        self.assertIn("降低了景点填充项的优先级", reasoning)
        evidence = build_completion_decision_evidence(
            block_type=TimeBlockType.AFTERNOON,
            candidate=candidate,
            day_items=day_items,
            candidate_pool=[candidate, *candidate_pool],
            day_details=self.build_manual_itinerary(
                blocks=[
                    DayTimeBlock(
                        block_type=TimeBlockType.AFTERNOON,
                        start_time=time(13, 0),
                        end_time=time(17, 0),
                        items=[],
                    )
                ],
            ).days[0],
            target_block=DayTimeBlock(
                block_type=TimeBlockType.AFTERNOON,
                start_time=time(13, 0),
                end_time=time(17, 0),
                items=[],
            ),
            existing_names=set(),
            used_names=set(),
            day_signal=({"people_square"}, set()),
            trip_signal=({"people_square"}, set()),
            day_centroid=(31.23041, 121.4737),
            trip_centroid=(31.23041, 121.4737),
            style_preferences=None,
            fullness_signal=fullness_signal,
            request_style_preferences=None,
            preference_policy=None,
        )
        self.assertIn("下午时段仍然为空", evidence.why_gap_exists)
        self.assertIn("午餐锚点", evidence.why_this_poi_fits)
        self.assertIn("降低了景点填充项的优先级", evidence.alternatives_rejected)
        self.assertTrue(evidence.top_candidates)
        self.assertTrue(
            any(candidate.status == "selected" for candidate in evidence.top_candidates)
        )
        self.assertTrue(evidence.rejected_candidates)

    def test_reasoning_summary_mentions_explicit_museum_preference_when_supported(self) -> None:
        reasoning = build_reasoning_summary(
            day=1,
            block_type=TimeBlockType.MORNING,
            candidate=CandidateSpec(
                name="上海自然博物馆",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.MORNING,),
                areas=("people_square",),
                themes=("museum",),
                duration_minutes=90,
                profile_intensity="heavy",
            ),
            day_signal=(set(), {"museum"}),
            fullness_signal=BlockFullnessSignal(
                block_type=TimeBlockType.MORNING,
                occupied_minutes=0,
                meaningful=False,
                underfilled=False,
            ),
            sparse_day_rank=0,
            sparse_day_count=1,
            day_fullness_signals=[],
            request_style_preferences=infer_request_style_preferences(
                ["想多看博物馆和展览"],
                scenic_spots=[],
                restaurants=[],
            ),
        )

        self.assertIn("博物馆/文化风格", reasoning)

    def test_reasoning_summary_uses_cautious_phrase_for_inferred_museum_style(self) -> None:
        reasoning = build_reasoning_summary(
            day=1,
            block_type=TimeBlockType.MORNING,
            candidate=CandidateSpec(
                name="上海自然博物馆",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.MORNING,),
                areas=("people_square",),
                themes=("museum",),
                duration_minutes=90,
                profile_intensity="heavy",
            ),
            day_signal=(set(), {"museum"}),
            fullness_signal=BlockFullnessSignal(
                block_type=TimeBlockType.MORNING,
                occupied_minutes=0,
                meaningful=False,
                underfilled=False,
            ),
            sparse_day_rank=0,
            sparse_day_count=1,
            day_fullness_signals=[],
            request_style_preferences=StylePreferenceSignal(
                inferred=frozenset({"museum"})
            ),
        )

        self.assertIn(
            "博物馆/文化方向",
            reasoning,
        )
        self.assertNotIn("you asked for", reasoning)

    def test_reasoning_summary_mentions_explicit_strolling_preference_when_supported(self) -> None:
        reasoning = build_reasoning_summary(
            day=1,
            block_type=TimeBlockType.AFTERNOON,
            candidate=CandidateSpec(
                name="思南公馆",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("french_concession",),
                themes=("design", "old_street"),
                duration_minutes=75,
                profile_intensity="medium",
            ),
            day_signal=(set(), {"design", "old_street"}),
            fullness_signal=BlockFullnessSignal(
                block_type=TimeBlockType.AFTERNOON,
                occupied_minutes=0,
                meaningful=False,
                underfilled=False,
            ),
            sparse_day_rank=0,
            sparse_day_count=1,
            day_fullness_signals=[],
            preference_policy=PlannerPreferencePolicy(scenic_priority="high"),
        )

        self.assertIn("漫游感", reasoning)

    def test_reasoning_summary_mentions_explicit_food_stop_preference_when_supported(self) -> None:
        reasoning = build_reasoning_summary(
            day=1,
            block_type=TimeBlockType.EVENING,
            candidate=CandidateSpec(
                name="城隍庙小吃街",
                type=POIType.RESTAURANT,
                block_types=(TimeBlockType.EVENING,),
                areas=("old_town",),
                themes=("street_food", "night"),
                duration_minutes=60,
                profile_intensity="medium",
            ),
            day_signal=(set(), {"street_food", "night"}),
            fullness_signal=BlockFullnessSignal(
                block_type=TimeBlockType.EVENING,
                occupied_minutes=0,
                meaningful=False,
                underfilled=False,
            ),
            sparse_day_rank=0,
            sparse_day_count=1,
            day_fullness_signals=[],
            preference_policy=PlannerPreferencePolicy(dining_priority="high"),
        )

        self.assertIn("餐食停靠风格", reasoning)

    def test_reasoning_summary_mentions_evening_riverside_flow_when_aligned(self) -> None:
        reasoning = build_reasoning_summary(
            day=1,
            block_type=TimeBlockType.EVENING,
            candidate=CandidateSpec(
                name="陆家嘴滨江步道",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.EVENING,),
                areas=("lujiazui",),
                themes=("night", "waterfront"),
                duration_minutes=60,
                profile_intensity="light",
            ),
            day_signal=(set(), {"night", "waterfront"}),
            fullness_signal=BlockFullnessSignal(
                block_type=TimeBlockType.EVENING,
                occupied_minutes=0,
                meaningful=False,
                underfilled=False,
            ),
            sparse_day_rank=0,
            sparse_day_count=1,
            day_fullness_signals=[],
        )

        self.assertIn("夜间时段仍然为空", reasoning)
        self.assertIn(
            "夜间散步",
            reasoning,
        )

    def test_reasoning_summary_mentions_explicit_evening_viewing_preference_when_supported(self) -> None:
        reasoning = build_reasoning_summary(
            day=1,
            block_type=TimeBlockType.EVENING,
            candidate=CandidateSpec(
                name="陆家嘴滨江步道",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.EVENING,),
                areas=("lujiazui",),
                themes=("night", "waterfront"),
                duration_minutes=60,
                profile_intensity="light",
            ),
            day_signal=(set(), {"night", "waterfront"}),
            fullness_signal=BlockFullnessSignal(
                block_type=TimeBlockType.EVENING,
                occupied_minutes=0,
                meaningful=False,
                underfilled=False,
            ),
            sparse_day_rank=0,
            sparse_day_count=1,
            day_fullness_signals=[],
            preference_policy=PlannerPreferencePolicy(scenic_priority="high"),
        )

        self.assertIn("夜景风格", reasoning)

    def test_choose_candidate_keeps_route_signal_meaningful_over_lower_friction_fit(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(16, 0),
                    items=[],
                )
            ]
        )
        target_block = itinerary.days[0].blocks[0]
        candidates = [
            CandidateSpec(
                name="Low friction generic",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=(),
                themes=(),
                duration_minutes=60,
                profile_intensity="medium",
                latitude=31.2100,
                longitude=121.4600,
            ),
            CandidateSpec(
                name="Route matched option",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("french_concession",),
                themes=("design",),
                duration_minutes=90,
                profile_intensity="medium",
                latitude=31.2200,
                longitude=121.4700,
            ),
        ]

        selected = choose_candidate(
            candidates=candidates,
            day_details=itinerary.days[0],
            target_block=target_block,
            block_type=TimeBlockType.AFTERNOON,
            existing_names=set(),
            used_names=set(),
            day_signal=({"french_concession"}, {"design"}),
            trip_signal=(set(), set()),
            day_centroid=None,
            trip_centroid=None,
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "Route matched option")

    def test_choose_candidate_prefers_smaller_normalized_detour_ratio_when_scores_tie(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(18, 0),
                    items=[
                        ScheduledPOI(
                            name="人民广场",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.2304,
                            longitude=121.4737,
                            duration_minutes=60,
                            day=1,
                            start_time=time(13, 0),
                            end_time=time(14, 0),
                            is_fixed=False,
                        ),
                        ScheduledPOI(
                            name="陆家嘴",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.2304,
                            longitude=121.5137,
                            duration_minutes=60,
                            day=1,
                            start_time=time(16, 0),
                            end_time=time(17, 0),
                            is_fixed=False,
                        ),
                    ],
                )
            ],
            hotel=HotelStay(
                name="东岸酒店",
                city="上海",
                latitude=31.2304,
                longitude=121.6037,
            ),
        )
        target_block = itinerary.days[0].blocks[0]
        candidates = [
            CandidateSpec(
                name="Aligned extension option",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("test_area",),
                themes=("test_theme",),
                duration_minutes=35,
                profile_intensity="medium",
                latitude=31.2304,
                longitude=121.5587,
            ),
            CandidateSpec(
                name="Compact middle detour",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("test_area",),
                themes=("test_theme",),
                duration_minutes=35,
                profile_intensity="medium",
                latitude=31.2454,
                longitude=121.4937,
            ),
        ]

        selected = choose_candidate(
            candidates=candidates,
            day_details=itinerary.days[0],
            target_block=target_block,
            block_type=TimeBlockType.AFTERNOON,
            existing_names=set(),
            used_names=set(),
            day_signal=(set(), set()),
            trip_signal=(set(), set()),
            day_centroid=None,
            trip_centroid=None,
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "Aligned extension option")

    def test_choose_candidate_prefers_longer_baseline_with_slightly_larger_absolute_detour(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(18, 0),
                    items=[
                        ScheduledPOI(
                            name="人民广场",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.2304,
                            longitude=121.4737,
                            duration_minutes=60,
                            day=1,
                            start_time=time(13, 0),
                            end_time=time(14, 0),
                            is_fixed=False,
                        ),
                        ScheduledPOI(
                            name="陆家嘴",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.2304,
                            longitude=121.5137,
                            duration_minutes=60,
                            day=1,
                            start_time=time(16, 0),
                            end_time=time(17, 0),
                            is_fixed=False,
                        ),
                    ],
                )
            ],
            hotel=HotelStay(
                name="东岸酒店",
                city="上海",
                latitude=31.2304,
                longitude=121.6037,
            ),
        )
        target_block = itinerary.days[0].blocks[0]
        candidates = [
            CandidateSpec(
                name="Short-baseline bend",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("test_area",),
                themes=("test_theme",),
                duration_minutes=35,
                profile_intensity="medium",
                latitude=31.2340,
                longitude=121.4937,
            ),
            CandidateSpec(
                name="Long-baseline extension",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("test_area",),
                themes=("test_theme",),
                duration_minutes=35,
                profile_intensity="medium",
                latitude=31.2360,
                longitude=121.5587,
            ),
        ]

        selected = choose_candidate(
            candidates=candidates,
            day_details=itinerary.days[0],
            target_block=target_block,
            block_type=TimeBlockType.AFTERNOON,
            existing_names=set(),
            used_names=set(),
            day_signal=(set(), set()),
            trip_signal=(set(), set()),
            day_centroid=None,
            trip_centroid=None,
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "Long-baseline extension")

    def test_choose_candidate_uses_absolute_detour_delta_to_break_near_tied_ratio(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(18, 0),
                    items=[
                        ScheduledPOI(
                            name="人民广场",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.2304,
                            longitude=121.4737,
                            duration_minutes=60,
                            day=1,
                            start_time=time(13, 0),
                            end_time=time(14, 0),
                            is_fixed=False,
                        ),
                        ScheduledPOI(
                            name="陆家嘴",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.2304,
                            longitude=121.5137,
                            duration_minutes=60,
                            day=1,
                            start_time=time(16, 0),
                            end_time=time(17, 0),
                            is_fixed=False,
                        ),
                    ],
                )
            ],
            hotel=HotelStay(
                name="东岸酒店",
                city="上海",
                latitude=31.2304,
                longitude=121.6037,
            ),
        )
        target_block = itinerary.days[0].blocks[0]
        candidates = [
            CandidateSpec(
                name="Near-tie smaller absolute detour",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("test_area",),
                themes=("test_theme",),
                duration_minutes=35,
                profile_intensity="medium",
                latitude=31.2340,
                longitude=121.4937,
            ),
            CandidateSpec(
                name="Near-tie smaller ratio",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("test_area",),
                themes=("test_theme",),
                duration_minutes=35,
                profile_intensity="medium",
                latitude=31.2380,
                longitude=121.5587,
            ),
        ]

        selected = choose_candidate(
            candidates=candidates,
            day_details=itinerary.days[0],
            target_block=target_block,
            block_type=TimeBlockType.AFTERNOON,
            existing_names=set(),
            used_names=set(),
            day_signal=(set(), set()),
            trip_signal=(set(), set()),
            day_centroid=None,
            trip_centroid=None,
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "Near-tie smaller absolute detour")

    def test_choose_candidate_prefers_all_strong_route_evidence_over_mixed_when_metrics_are_close(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[],
                )
            ]
        )
        target_block = itinerary.days[0].blocks[0]
        candidates = [
            CandidateSpec(
                name="All strong route evidence",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("test_area",),
                themes=("test_theme",),
                duration_minutes=60,
                profile_intensity="medium",
                latitude=31.2200,
                longitude=121.4700,
            ),
            CandidateSpec(
                name="Mixed route evidence",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("test_area",),
                themes=("test_theme",),
                duration_minutes=60,
                profile_intensity="medium",
                latitude=31.2210,
                longitude=121.4710,
            ),
        ]

        fit_quality_by_name = {
            "All strong route evidence": (0.100, 100.0, 0, 0, 0, 0, 40, 1),
            "Mixed route evidence": (0.102, 95.0, 1, 1, 1, 0, 40, 1),
        }

        with patch(
            "app.services.itinerary_completion_recommendation.candidate_insertion_fit_quality",
            side_effect=lambda **kwargs: fit_quality_by_name[kwargs["candidate"].name],
        ):
            selected = choose_candidate(
                candidates=candidates,
                day_details=itinerary.days[0],
                target_block=target_block,
                block_type=TimeBlockType.AFTERNOON,
                existing_names=set(),
                used_names=set(),
                day_signal=(set(), set()),
                trip_signal=(set(), set()),
                day_centroid=None,
                trip_centroid=None,
            )

        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "All strong route evidence")

    def test_choose_candidate_prefers_mixed_route_evidence_over_all_fallback_when_metrics_are_close(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[],
                )
            ]
        )
        target_block = itinerary.days[0].blocks[0]
        candidates = [
            CandidateSpec(
                name="Mixed route evidence",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("test_area",),
                themes=("test_theme",),
                duration_minutes=60,
                profile_intensity="medium",
                latitude=31.2200,
                longitude=121.4700,
            ),
            CandidateSpec(
                name="All fallback route evidence",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("test_area",),
                themes=("test_theme",),
                duration_minutes=60,
                profile_intensity="medium",
                latitude=31.2210,
                longitude=121.4710,
            ),
        ]

        fit_quality_by_name = {
            "Mixed route evidence": (0.100, 100.0, 1, 1, 1, 0, 40, 1),
            "All fallback route evidence": (0.102, 95.0, 2, 0, 0, 0, 40, 1),
        }

        with patch(
            "app.services.itinerary_completion_recommendation.candidate_insertion_fit_quality",
            side_effect=lambda **kwargs: fit_quality_by_name[kwargs["candidate"].name],
        ):
            selected = choose_candidate(
                candidates=candidates,
                day_details=itinerary.days[0],
                target_block=target_block,
                block_type=TimeBlockType.AFTERNOON,
                existing_names=set(),
                used_names=set(),
                day_signal=(set(), set()),
                trip_signal=(set(), set()),
                day_centroid=None,
                trip_centroid=None,
            )

        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "Mixed route evidence")

    def test_choose_candidate_prefers_baseline_stronger_mixed_evidence_in_same_mixed_bucket(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[],
                )
            ]
        )
        target_block = itinerary.days[0].blocks[0]
        candidates = [
            CandidateSpec(
                name="Baseline stronger mixed evidence",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("test_area",),
                themes=("test_theme",),
                duration_minutes=60,
                profile_intensity="medium",
                latitude=31.2200,
                longitude=121.4700,
            ),
            CandidateSpec(
                name="Baseline weaker mixed evidence",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("test_area",),
                themes=("test_theme",),
                duration_minutes=60,
                profile_intensity="medium",
                latitude=31.2210,
                longitude=121.4710,
            ),
        ]

        fit_quality_by_name = {
            "Baseline stronger mixed evidence": (0.100, 100.0, 1, 0, 1, 0, 40, 1),
            "Baseline weaker mixed evidence": (0.100, 100.0, 1, 1, 1, 0, 40, 1),
        }

        with patch(
            "app.services.itinerary_completion_recommendation.candidate_insertion_fit_quality",
            side_effect=lambda **kwargs: fit_quality_by_name[kwargs["candidate"].name],
        ):
            selected = choose_candidate(
                candidates=candidates,
                day_details=itinerary.days[0],
                target_block=target_block,
                block_type=TimeBlockType.AFTERNOON,
                existing_names=set(),
                used_names=set(),
                day_signal=(set(), set()),
                trip_signal=(set(), set()),
                day_centroid=None,
                trip_centroid=None,
            )

        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "Baseline stronger mixed evidence")

    def test_choose_candidate_prefers_both_side_legs_strong_within_baseline_strong_mixed_bucket(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[],
                )
            ]
        )
        target_block = itinerary.days[0].blocks[0]
        candidates = [
            CandidateSpec(
                name="Both side legs strong",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("test_area",),
                themes=("test_theme",),
                duration_minutes=60,
                profile_intensity="medium",
                latitude=31.2200,
                longitude=121.4700,
            ),
            CandidateSpec(
                name="One side strong one fallback",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("test_area",),
                themes=("test_theme",),
                duration_minutes=60,
                profile_intensity="medium",
                latitude=31.2210,
                longitude=121.4710,
            ),
        ]

        fit_quality_by_name = {
            "Both side legs strong": (0.100, 100.0, 1, 0, 0, 0, 40, 1),
            "One side strong one fallback": (0.100, 100.0, 1, 0, 1, 0, 40, 1),
        }

        with patch(
            "app.services.itinerary_completion_recommendation.candidate_insertion_fit_quality",
            side_effect=lambda **kwargs: fit_quality_by_name[kwargs["candidate"].name],
        ):
            selected = choose_candidate(
                candidates=candidates,
                day_details=itinerary.days[0],
                target_block=target_block,
                block_type=TimeBlockType.AFTERNOON,
                existing_names=set(),
                used_names=set(),
                day_signal=(set(), set()),
                trip_signal=(set(), set()),
                day_centroid=None,
                trip_centroid=None,
            )

        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "Both side legs strong")

    def test_choose_candidate_prefers_inbound_strong_directionality_within_same_side_leg_bucket(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[],
                )
            ]
        )
        target_block = itinerary.days[0].blocks[0]
        candidates = [
            CandidateSpec(
                name="Inbound strong directionality",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("test_area",),
                themes=("test_theme",),
                duration_minutes=60,
                profile_intensity="medium",
                latitude=31.2200,
                longitude=121.4700,
            ),
            CandidateSpec(
                name="Outbound strong directionality",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("test_area",),
                themes=("test_theme",),
                duration_minutes=60,
                profile_intensity="medium",
                latitude=31.2210,
                longitude=121.4710,
            ),
        ]

        fit_quality_by_name = {
            "Inbound strong directionality": (0.100, 100.0, 1, 0, 1, 0, 40, 1),
            "Outbound strong directionality": (0.100, 100.0, 1, 0, 1, 1, 40, 1),
        }

        with patch(
            "app.services.itinerary_completion_recommendation.candidate_insertion_fit_quality",
            side_effect=lambda **kwargs: fit_quality_by_name[kwargs["candidate"].name],
        ):
            selected = choose_candidate(
                candidates=candidates,
                day_details=itinerary.days[0],
                target_block=target_block,
                block_type=TimeBlockType.AFTERNOON,
                existing_names=set(),
                used_names=set(),
                day_signal=(set(), set()),
                trip_signal=(set(), set()),
                day_centroid=None,
                trip_centroid=None,
            )

        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "Inbound strong directionality")

    def test_choose_candidate_keeps_primary_signal_score_over_lower_normalized_detour_ratio(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(18, 0),
                    items=[
                        ScheduledPOI(
                            name="人民广场",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.2304,
                            longitude=121.4737,
                            duration_minutes=60,
                            day=1,
                            start_time=time(13, 0),
                            end_time=time(14, 0),
                            is_fixed=False,
                        ),
                        ScheduledPOI(
                            name="陆家嘴",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.2304,
                            longitude=121.5137,
                            duration_minutes=60,
                            day=1,
                            start_time=time(16, 0),
                            end_time=time(17, 0),
                            is_fixed=False,
                        ),
                    ],
                )
            ],
            hotel=HotelStay(
                name="东岸酒店",
                city="上海",
                latitude=31.2304,
                longitude=121.6037,
            ),
        )
        target_block = itinerary.days[0].blocks[0]
        candidates = [
            CandidateSpec(
                name="Aligned generic option",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=(),
                themes=(),
                duration_minutes=35,
                profile_intensity="medium",
                latitude=31.2304,
                longitude=121.5587,
            ),
            CandidateSpec(
                name="Signal matched detour",
                type=POIType.SCENIC,
                block_types=(TimeBlockType.AFTERNOON,),
                areas=("french_concession",),
                themes=("design",),
                duration_minutes=35,
                profile_intensity="medium",
                latitude=31.2454,
                longitude=121.4937,
            ),
        ]

        selected = choose_candidate(
            candidates=candidates,
            day_details=itinerary.days[0],
            target_block=target_block,
            block_type=TimeBlockType.AFTERNOON,
            existing_names=set(),
            used_names=set(),
            day_signal=({"french_concession"}, {"design"}),
            trip_signal=(set(), set()),
            day_centroid=None,
            trip_centroid=None,
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "Signal matched detour")

    def test_infers_city_from_itinerary_and_uses_city_specific_candidates(self) -> None:
        scenic_spots = [
            NormalizedPOI(
                name="豫园",
                type=POIType.SCENIC,
                city="上海",
                latitude=31.225312,
                longitude=121.487633,
                duration_minutes=90,
                profile=POIProfile(
                    visit_style=POIVisitStyle.TEMPLE_PARK,
                    best_time_blocks=[TimeBlockType.MORNING, TimeBlockType.AFTERNOON],
                    typical_duration_minutes=90,
                    intensity="medium",
                ),
            ),
            NormalizedPOI(
                name="外滩",
                type=POIType.SCENIC,
                city="上海",
                latitude=31.238235,
                longitude=121.497253,
                duration_minutes=60,
                profile=POIProfile(
                    visit_style=POIVisitStyle.NIGHT_VIEW,
                    best_time_blocks=[TimeBlockType.EVENING],
                    typical_duration_minutes=60,
                    intensity="light",
                ),
            ),
        ]
        hotel = HotelStay(
            name="南京路步行街附近酒店",
            city="上海",
            latitude=31.236831,
            longitude=121.483088,
        )

        itinerary = Scheduler().build_schedule(
            scenic_spots=scenic_spots,
            restaurants=[],
            hotel=hotel,
            planning_anchor_source=PlanningAnchorSource(
                source_type="provided_hotel",
                source_name=hotel.name,
            ),
            trip_days=2,
        )

        recommendation = build_itinerary_completion_recommendation(itinerary)

        self.assertIsNotNone(recommendation)
        option_names = {option.name for option in recommendation.options}

        self.assertIn("BFC 外滩枫径", option_names)
        self.assertIn("陆家嘴滨江步道", option_names)
        self.assertNotIn("Food street dinner", option_names)
        self.assertNotIn("Riverfront evening walk", option_names)

    def test_autofill_inserts_top_completion_candidates_into_empty_blocks(self) -> None:
        scenic_spots = [
            NormalizedPOI(
                name="豫园",
                type=POIType.SCENIC,
                city="上海",
                latitude=31.225312,
                longitude=121.487633,
                duration_minutes=90,
                profile=POIProfile(
                    visit_style=POIVisitStyle.TEMPLE_PARK,
                    best_time_blocks=[TimeBlockType.MORNING, TimeBlockType.AFTERNOON],
                    typical_duration_minutes=90,
                    intensity="medium",
                ),
            ),
            NormalizedPOI(
                name="外滩",
                type=POIType.SCENIC,
                city="上海",
                latitude=31.238235,
                longitude=121.497253,
                duration_minutes=60,
                profile=POIProfile(
                    visit_style=POIVisitStyle.NIGHT_VIEW,
                    best_time_blocks=[TimeBlockType.EVENING],
                    typical_duration_minutes=60,
                    intensity="light",
                ),
            ),
        ]
        hotel = HotelStay(
            name="南京路步行街附近酒店",
            city="上海",
            latitude=31.236831,
            longitude=121.483088,
        )

        itinerary = Scheduler().build_schedule(
            scenic_spots=scenic_spots,
            restaurants=[],
            hotel=hotel,
            planning_anchor_source=PlanningAnchorSource(
                source_type="provided_hotel",
                source_name=hotel.name,
            ),
            trip_days=2,
        )
        recommendation = build_itinerary_completion_recommendation(itinerary)

        self.assertIsNotNone(recommendation)
        self.assertEqual(
            [
                (option.suggested_day, option.suggested_block, option.name)
                for option in prioritized_autofill_options(recommendation)[:3]
            ],
            [
                (2, TimeBlockType.MORNING, "静安寺"),
                (2, TimeBlockType.AFTERNOON, "人民广场本帮菜午餐"),
                (1, TimeBlockType.AFTERNOON, "陆家嘴滨江步道"),
            ],
        )

        autofilled = apply_completion_recommendation_autofill(itinerary, recommendation)

        day_one = next(day for day in autofilled.days if day.day == 1)
        day_two = next(day for day in autofilled.days if day.day == 2)
        day_one_afternoon = next(
            block for block in day_one.blocks if block.block_type == TimeBlockType.AFTERNOON
        )
        morning = next(
            block for block in day_two.blocks if block.block_type == TimeBlockType.MORNING
        )
        afternoon = next(
            block for block in day_two.blocks if block.block_type == TimeBlockType.AFTERNOON
        )
        evening = next(
            block for block in day_two.blocks if block.block_type == TimeBlockType.EVENING
        )

        self.assertEqual([item.name for item in day_one_afternoon.items], ["陆家嘴滨江步道"])
        self.assertEqual([item.name for item in morning.items], ["静安寺"])
        self.assertEqual([item.name for item in afternoon.items], ["人民广场本帮菜午餐"])
        self.assertEqual([item.name for item in evening.items], [])
        self.assertFalse(day_one_afternoon.items[0].is_fixed)
        self.assertEqual(day_one_afternoon.items[0].type, POIType.SCENIC)
        self.assertEqual(day_one_afternoon.items[0].source_type, ScheduledPOISourceType.AUTO_FILLED)
        self.assertEqual(day_one_afternoon.items[0].source_label, "系统空档补全")
        self.assertFalse(morning.items[0].is_fixed)
        self.assertEqual(morning.items[0].source_type, ScheduledPOISourceType.AUTO_FILLED)
        self.assertFalse(afternoon.items[0].is_fixed)
        self.assertEqual(afternoon.items[0].source_type, ScheduledPOISourceType.AUTO_FILLED)

        updated_recommendation = build_itinerary_completion_recommendation(autofilled)
        self.assertIsNotNone(updated_recommendation)
        updated_names = {option.name for option in updated_recommendation.options}
        self.assertNotIn("上海博物馆", updated_names)
        self.assertNotIn("静安寺", updated_names)
        self.assertNotIn("陆家嘴滨江步道", updated_names)
        self.assertIn("BFC 外滩枫径", updated_names)

    def test_sparse_two_day_autofill_produces_staggered_fill_and_shrinks_remaining_gaps(self) -> None:
        scenic_spots = [
            NormalizedPOI(
                name="豫园",
                type=POIType.SCENIC,
                city="上海",
                latitude=31.225312,
                longitude=121.487633,
                duration_minutes=90,
                profile=POIProfile(
                    visit_style=POIVisitStyle.TEMPLE_PARK,
                    best_time_blocks=[TimeBlockType.MORNING, TimeBlockType.AFTERNOON],
                    typical_duration_minutes=90,
                    intensity="medium",
                ),
            ),
            NormalizedPOI(
                name="外滩",
                type=POIType.SCENIC,
                city="上海",
                latitude=31.238235,
                longitude=121.497253,
                duration_minutes=60,
                profile=POIProfile(
                    visit_style=POIVisitStyle.NIGHT_VIEW,
                    best_time_blocks=[TimeBlockType.EVENING],
                    typical_duration_minutes=60,
                    intensity="light",
                ),
            ),
        ]
        hotel = HotelStay(
            name="南京路步行街附近酒店",
            city="上海",
            latitude=31.236831,
            longitude=121.483088,
        )

        itinerary = Scheduler().build_schedule(
            scenic_spots=scenic_spots,
            restaurants=[],
            hotel=hotel,
            planning_anchor_source=PlanningAnchorSource(
                source_type="provided_hotel",
                source_name=hotel.name,
            ),
            trip_days=2,
        )
        recommendation = build_itinerary_completion_recommendation(itinerary)

        self.assertIsNotNone(recommendation)
        self.assertIn("第 2 天是当前最薄的一天", recommendation.summary)
        self.assertIn("诚实的补全候选", recommendation.summary)
        self.assertEqual(
            [
                (option.suggested_day, option.suggested_block, option.name)
                for option in recommendation.options[:5]
            ],
            [
                (2, TimeBlockType.MORNING, "静安寺"),
                (2, TimeBlockType.AFTERNOON, "人民广场本帮菜午餐"),
                (2, TimeBlockType.EVENING, "BFC 外滩枫径"),
                (1, TimeBlockType.AFTERNOON, "陆家嘴滨江步道"),
                (1, TimeBlockType.EVENING, "城隍庙小吃街"),
            ],
        )

        autofilled = apply_completion_recommendation_autofill(itinerary, recommendation)

        day_one = next(day for day in autofilled.days if day.day == 1)
        day_two = next(day for day in autofilled.days if day.day == 2)
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.AFTERNOON).items],
            ["陆家嘴滨江步道"],
        )
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.EVENING).items],
            ["外滩"],
        )
        self.assertEqual(
            [item.name for item in next(block for block in day_two.blocks if block.block_type == TimeBlockType.MORNING).items],
            ["静安寺"],
        )
        self.assertEqual(
            [item.name for item in next(block for block in day_two.blocks if block.block_type == TimeBlockType.AFTERNOON).items],
            ["人民广场本帮菜午餐"],
        )
        self.assertEqual(
            [item.name for item in next(block for block in day_two.blocks if block.block_type == TimeBlockType.EVENING).items],
            [],
        )

        updated_recommendation = build_itinerary_completion_recommendation(autofilled)
        self.assertIsNotNone(updated_recommendation)
        self.assertIn(
            "第 2 天仍是当前骨架里最弱的一天",
            updated_recommendation.summary,
        )
        self.assertIn(
            "当天其他时段已经相对平衡",
            updated_recommendation.options[0].reasoning_summary,
        )
        self.assertEqual(
            [
                (option.suggested_day, option.suggested_block, option.name)
                for option in updated_recommendation.options
            ],
            [
                (2, TimeBlockType.EVENING, "BFC 外滩枫径"),
                (2, TimeBlockType.AFTERNOON, "上海自然博物馆"),
            ],
        )

    def test_balanced_sparse_days_keep_stable_day_order_when_cross_day_pressure_ties(self) -> None:
        hotel = HotelStay(
            name="人民广场酒店",
            city="上海",
            latitude=31.2304,
            longitude=121.4737,
        )
        itinerary = ItineraryResponse(
            trip_days=2,
            hotel=hotel,
            planning_anchor_source=PlanningAnchorSource(
                source_type="provided_hotel",
                source_name=hotel.name,
            ),
            days=[
                DayItinerary(
                    day=1,
                    hotel=hotel,
                    blocks=[
                        DayTimeBlock(
                            block_type=TimeBlockType.MORNING,
                            start_time=time(9, 0),
                            end_time=time(12, 0),
                            items=[],
                        ),
                        DayTimeBlock(
                            block_type=TimeBlockType.AFTERNOON,
                            start_time=time(13, 0),
                            end_time=time(17, 0),
                            items=[],
                        ),
                        DayTimeBlock(
                            block_type=TimeBlockType.EVENING,
                            start_time=time(17, 30),
                            end_time=time(21, 0),
                            items=[],
                        ),
                    ],
                ),
                DayItinerary(
                    day=2,
                    hotel=hotel,
                    blocks=[
                        DayTimeBlock(
                            block_type=TimeBlockType.MORNING,
                            start_time=time(9, 0),
                            end_time=time(12, 0),
                            items=[],
                        ),
                        DayTimeBlock(
                            block_type=TimeBlockType.AFTERNOON,
                            start_time=time(13, 0),
                            end_time=time(17, 0),
                            items=[],
                        ),
                        DayTimeBlock(
                            block_type=TimeBlockType.EVENING,
                            start_time=time(17, 30),
                            end_time=time(21, 0),
                            items=[],
                        ),
                    ],
                ),
            ],
        )

        recommendation = build_itinerary_completion_recommendation(itinerary)

        self.assertIsNotNone(recommendation)
        self.assertEqual([day.day for day in recommendation.sparse_days], [1, 2])

    def test_prioritized_day_uses_thinnest_block_first_before_mildly_underfilled_block(self) -> None:
        hotel = HotelStay(
            name="人民广场酒店",
            city="上海",
            latitude=31.2304,
            longitude=121.4737,
        )
        itinerary = ItineraryResponse(
            trip_days=2,
            hotel=hotel,
            planning_anchor_source=PlanningAnchorSource(
                source_type="provided_hotel",
                source_name=hotel.name,
            ),
            days=[
                DayItinerary(
                    day=1,
                    hotel=hotel,
                    blocks=[
                        DayTimeBlock(
                            block_type=TimeBlockType.MORNING,
                            start_time=time(9, 0),
                            end_time=time(12, 0),
                            items=[
                                ScheduledPOI(
                                    name="思南公馆",
                                    type=POIType.SCENIC,
                                    city="上海",
                                    latitude=31.21992,
                                    longitude=121.46753,
                                    duration_minutes=90,
                                    day=1,
                                    start_time=time(9, 0),
                                    end_time=time(10, 30),
                                    is_fixed=False,
                                )
                            ],
                        ),
                        DayTimeBlock(
                            block_type=TimeBlockType.AFTERNOON,
                            start_time=time(13, 0),
                            end_time=time(17, 0),
                            items=[
                                ScheduledPOI(
                                    name="外滩",
                                    type=POIType.SCENIC,
                                    city="上海",
                                    latitude=31.238235,
                                    longitude=121.497253,
                                    duration_minutes=60,
                                    day=1,
                                    start_time=time(18, 0),
                                    end_time=time(19, 0),
                                    is_fixed=False,
                                )
                            ],
                        ),
                        DayTimeBlock(
                            block_type=TimeBlockType.EVENING,
                            start_time=time(17, 30),
                            end_time=time(21, 0),
                            items=[],
                        ),
                    ],
                ),
                DayItinerary(
                    day=2,
                    hotel=hotel,
                    blocks=[
                        DayTimeBlock(
                            block_type=TimeBlockType.MORNING,
                            start_time=time(9, 0),
                            end_time=time(12, 0),
                            items=[
                                ScheduledPOI(
                                    name="人民广场",
                                    type=POIType.SCENIC,
                                    city="上海",
                                    latitude=31.2304,
                                    longitude=121.4737,
                                    duration_minutes=45,
                                    day=2,
                                    start_time=time(9, 0),
                                    end_time=time(9, 45),
                                    is_fixed=False,
                                )
                            ],
                        ),
                        DayTimeBlock(
                            block_type=TimeBlockType.AFTERNOON,
                            start_time=time(13, 0),
                            end_time=time(17, 0),
                            items=[],
                        ),
                        DayTimeBlock(
                            block_type=TimeBlockType.EVENING,
                            start_time=time(17, 30),
                            end_time=time(21, 0),
                            items=[
                                ScheduledPOI(
                                    name="BFC 外滩枫径",
                                    type=POIType.RESTAURANT,
                                    city="上海",
                                    latitude=31.23374,
                                    longitude=121.49759,
                                    duration_minutes=60,
                                    day=2,
                                    start_time=time(18, 0),
                                    end_time=time(19, 0),
                                    is_fixed=False,
                                )
                            ],
                        ),
                    ],
                ),
            ],
        )

        recommendation = build_itinerary_completion_recommendation(itinerary)

        self.assertIsNotNone(recommendation)
        self.assertEqual([day.day for day in recommendation.sparse_days[:2]], [2, 1])
        self.assertIn("第 2 天仍是最薄的一天", recommendation.options[0].reasoning_summary)
        self.assertIn("下午时段仍然为空", recommendation.options[0].reasoning_summary)
        self.assertIn("更适合修复这个空档", recommendation.options[0].reasoning_summary)
        self.assertIn("上午时段仍然偏空", recommendation.options[1].reasoning_summary)
        self.assertEqual(
            [
                (option.suggested_day, option.suggested_block)
                for option in prioritized_autofill_options(recommendation)[:2]
            ],
            [
                (2, TimeBlockType.AFTERNOON),
                (2, TimeBlockType.MORNING),
            ],
        )

    def test_balanced_empty_blocks_keep_stable_within_day_order(self) -> None:
        hotel = HotelStay(
            name="人民广场酒店",
            city="上海",
            latitude=31.2304,
            longitude=121.4737,
        )
        itinerary = ItineraryResponse(
            trip_days=1,
            hotel=hotel,
            planning_anchor_source=PlanningAnchorSource(
                source_type="provided_hotel",
                source_name=hotel.name,
            ),
            days=[
                DayItinerary(
                    day=1,
                    hotel=hotel,
                    blocks=[
                        DayTimeBlock(
                            block_type=TimeBlockType.MORNING,
                            start_time=time(9, 0),
                            end_time=time(12, 0),
                            items=[],
                        ),
                        DayTimeBlock(
                            block_type=TimeBlockType.AFTERNOON,
                            start_time=time(13, 0),
                            end_time=time(17, 0),
                            items=[],
                        ),
                        DayTimeBlock(
                            block_type=TimeBlockType.EVENING,
                            start_time=time(17, 30),
                            end_time=time(21, 0),
                            items=[],
                        ),
                    ],
                )
            ],
        )

        recommendation = build_itinerary_completion_recommendation(itinerary)

        self.assertIsNotNone(recommendation)
        self.assertEqual(
            [
                (option.suggested_day, option.suggested_block)
                for option in prioritized_autofill_options(recommendation)
            ],
            [
                (1, TimeBlockType.MORNING),
                (1, TimeBlockType.AFTERNOON),
                (1, TimeBlockType.EVENING),
            ],
        )

    def test_autofill_budget_gives_two_early_slots_to_thinnest_day_before_next_sparse_day(self) -> None:
        scenic_spots = [
            NormalizedPOI(
                name="豫园",
                type=POIType.SCENIC,
                city="上海",
                latitude=31.225312,
                longitude=121.487633,
                duration_minutes=90,
                profile=POIProfile(
                    visit_style=POIVisitStyle.TEMPLE_PARK,
                    best_time_blocks=[TimeBlockType.MORNING, TimeBlockType.AFTERNOON],
                    typical_duration_minutes=90,
                    intensity="medium",
                ),
            ),
            NormalizedPOI(
                name="外滩",
                type=POIType.SCENIC,
                city="上海",
                latitude=31.238235,
                longitude=121.497253,
                duration_minutes=60,
                profile=POIProfile(
                    visit_style=POIVisitStyle.NIGHT_VIEW,
                    best_time_blocks=[TimeBlockType.EVENING],
                    typical_duration_minutes=60,
                    intensity="light",
                ),
            ),
        ]
        hotel = HotelStay(
            name="南京路步行街附近酒店",
            city="上海",
            latitude=31.236831,
            longitude=121.483088,
        )

        itinerary = Scheduler().build_schedule(
            scenic_spots=scenic_spots,
            restaurants=[],
            hotel=hotel,
            planning_anchor_source=PlanningAnchorSource(
                source_type="provided_hotel",
                source_name=hotel.name,
            ),
            trip_days=3,
        )
        recommendation = build_itinerary_completion_recommendation(itinerary)

        self.assertIsNotNone(recommendation)
        self.assertEqual([day.day for day in recommendation.sparse_days[:2]], [2, 3])
        self.assertEqual(
            [
                (option.suggested_day, option.suggested_block, option.name)
                for option in prioritized_autofill_options(recommendation)[:3]
            ],
            [
                (2, TimeBlockType.MORNING, "静安寺"),
                (2, TimeBlockType.AFTERNOON, "人民广场本帮菜午餐"),
                (3, TimeBlockType.MORNING, "上海自然博物馆"),
            ],
        )

        autofilled = apply_completion_recommendation_autofill(itinerary, recommendation)
        day_two = next(day for day in autofilled.days if day.day == 2)
        day_three = next(day for day in autofilled.days if day.day == 3)
        self.assertEqual(
            [item.name for item in next(block for block in day_two.blocks if block.block_type == TimeBlockType.MORNING).items],
            ["静安寺"],
        )
        self.assertEqual(
            [item.name for item in next(block for block in day_two.blocks if block.block_type == TimeBlockType.AFTERNOON).items],
            ["人民广场本帮菜午餐"],
        )
        self.assertEqual(
            [item.name for item in next(block for block in day_three.blocks if block.block_type == TimeBlockType.MORNING).items],
            ["上海自然博物馆"],
        )

    def test_single_day_sparse_museum_itinerary_autofill_completes_day_naturally(self) -> None:
        scenic_spots = [
            NormalizedPOI(
                name="上海博物馆",
                type=POIType.SCENIC,
                city="上海",
                latitude=31.23041,
                longitude=121.4737,
                duration_minutes=120,
                profile=POIProfile(
                    visit_style=POIVisitStyle.MUSEUM,
                    best_time_blocks=[TimeBlockType.AFTERNOON],
                    typical_duration_minutes=120,
                    intensity="heavy",
                ),
            )
        ]
        hotel = HotelStay(
            name="南京路步行街附近酒店",
            city="上海",
            latitude=31.236831,
            longitude=121.483088,
        )

        itinerary = Scheduler().build_schedule(
            scenic_spots=scenic_spots,
            restaurants=[],
            hotel=hotel,
            planning_anchor_source=PlanningAnchorSource(
                source_type="provided_hotel",
                source_name=hotel.name,
            ),
            trip_days=1,
        )
        recommendation = build_itinerary_completion_recommendation(
            itinerary,
            preference_policy=PlannerPreferencePolicy(scenic_priority="high"),
        )

        self.assertIsNotNone(recommendation)
        self.assertEqual(
            [
                (option.suggested_day, option.suggested_block, option.name, option.type)
                for option in recommendation.options
            ],
            [
                (1, TimeBlockType.MORNING, "上海自然博物馆", POIType.SCENIC),
                (1, TimeBlockType.EVENING, "城隍庙小吃街", POIType.RESTAURANT),
            ],
        )
        self.assertIn(
            "博物馆/文化风格",
            recommendation.options[0].reasoning_summary,
        )

        autofilled = apply_completion_recommendation_autofill(itinerary, recommendation)

        day_one = autofilled.days[0]
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.MORNING).items],
            ["上海自然博物馆"],
        )
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.AFTERNOON).items],
            ["上海博物馆"],
        )
        self.assertEqual(
            [item.name for item in next(block for block in day_one.blocks if block.block_type == TimeBlockType.EVENING).items],
            ["城隍庙小吃街"],
        )
        self.assertIsNone(build_itinerary_completion_recommendation(autofilled))

    def test_well_shaped_morning_afternoon_day_avoids_unnecessary_completion_pressure(self) -> None:
        scenic_spots = [
            NormalizedPOI(
                name="人民广场",
                type=POIType.SCENIC,
                city="上海",
                latitude=31.2304,
                longitude=121.4737,
                duration_minutes=60,
                profile=POIProfile(
                    visit_style=POIVisitStyle.LANDMARK,
                    best_time_blocks=[TimeBlockType.MORNING, TimeBlockType.AFTERNOON],
                    typical_duration_minutes=60,
                    intensity="light",
                ),
            ),
            NormalizedPOI(
                name="静安寺",
                type=POIType.SCENIC,
                city="上海",
                latitude=31.22346,
                longitude=121.44531,
                duration_minutes=90,
                profile=POIProfile(
                    visit_style=POIVisitStyle.TEMPLE_PARK,
                    best_time_blocks=[TimeBlockType.MORNING, TimeBlockType.AFTERNOON],
                    typical_duration_minutes=90,
                    intensity="medium",
                ),
            ),
        ]
        hotel = HotelStay(
            name="人民广场酒店",
            city="上海",
            latitude=31.2304,
            longitude=121.4737,
        )

        itinerary = Scheduler().build_schedule(
            scenic_spots=scenic_spots,
            restaurants=[],
            hotel=hotel,
            planning_anchor_source=PlanningAnchorSource(
                source_type="provided_hotel",
                source_name=hotel.name,
            ),
            trip_days=1,
        )

        self.assertIsNone(build_itinerary_completion_recommendation(itinerary))

    def test_completion_recommendation_can_target_partially_filled_light_blocks(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.MORNING,
                    start_time=time(9, 0),
                    end_time=time(12, 0),
                    items=[
                        ScheduledPOI(
                            name="思南公馆",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.21992,
                            longitude=121.46753,
                            duration_minutes=60,
                            day=1,
                            start_time=time(9, 30),
                            end_time=time(10, 30),
                            is_fixed=False,
                        )
                    ],
                ),
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[
                        ScheduledPOI(
                            name="田子坊",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.21103,
                            longitude=121.47055,
                            duration_minutes=60,
                            day=1,
                            start_time=time(14, 0),
                            end_time=time(15, 0),
                            is_fixed=False,
                        )
                    ],
                ),
                DayTimeBlock(
                    block_type=TimeBlockType.EVENING,
                    start_time=time(17, 30),
                    end_time=time(21, 0),
                    items=[],
                ),
            ]
        )

        recommendation = build_itinerary_completion_recommendation(itinerary)

        self.assertIsNotNone(recommendation)
        suggested_blocks = {option.suggested_block for option in recommendation.options}
        self.assertIn(TimeBlockType.AFTERNOON, suggested_blocks)
        self.assertIn(TimeBlockType.EVENING, suggested_blocks)

    def test_autofill_can_insert_into_partially_filled_block_with_stable_route_side_choice(self) -> None:
        itinerary = self.build_manual_itinerary(
            hotel=HotelStay(
                name="人民广场酒店",
                city="上海",
                latitude=31.2304,
                longitude=121.4737,
            ),
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.MORNING,
                    start_time=time(9, 0),
                    end_time=time(12, 0),
                    items=[
                        ScheduledPOI(
                            name="思南公馆",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.21992,
                            longitude=121.46753,
                            duration_minutes=60,
                            day=1,
                            start_time=time(9, 30),
                            end_time=time(10, 30),
                            is_fixed=False,
                        )
                    ],
                ),
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[
                        ScheduledPOI(
                            name="田子坊",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.21103,
                            longitude=121.47055,
                            duration_minutes=60,
                            day=1,
                            start_time=time(14, 0),
                            end_time=time(15, 0),
                            is_fixed=False,
                        )
                    ],
                ),
                DayTimeBlock(
                    block_type=TimeBlockType.EVENING,
                    start_time=time(17, 30),
                    end_time=time(21, 0),
                    items=[],
                ),
            ],
        )
        recommendation = ItineraryCompletionRecommendation(
            summary="test",
            options=[
                ItineraryCompletionOption(
                    name="新天地",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.AFTERNOON,
                    reasoning_summary="test",
                    itinerary_relation_summary="test",
                )
            ],
        )

        autofilled = apply_completion_recommendation_autofill(itinerary, recommendation)

        afternoon = next(
            block
            for block in autofilled.days[0].blocks
            if block.block_type == TimeBlockType.AFTERNOON
        )
        self.assertEqual([item.name for item in afternoon.items], ["田子坊", "新天地"])
        self.assertEqual(afternoon.items[1].start_time, time(15, 15))
        self.assertEqual(afternoon.items[1].end_time, time(16, 30))
        self.assertIn("田子坊 之后", afternoon.items[1].placement_reason or "")

    def test_autofill_can_insert_into_middle_gap_inside_partially_filled_block(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(18, 0),
                    items=[
                        ScheduledPOI(
                            name="思南公馆",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.21992,
                            longitude=121.46753,
                            duration_minutes=60,
                            day=1,
                            start_time=time(13, 0),
                            end_time=time(14, 0),
                            is_fixed=False,
                        ),
                        ScheduledPOI(
                            name="田子坊",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.21103,
                            longitude=121.47055,
                            duration_minutes=105,
                            day=1,
                            start_time=time(16, 5),
                            end_time=time(17, 50),
                            is_fixed=False,
                        ),
                    ],
                )
            ]
        )
        recommendation = ItineraryCompletionRecommendation(
            summary="test",
            options=[
                ItineraryCompletionOption(
                    name="新天地",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.AFTERNOON,
                    reasoning_summary="test",
                    itinerary_relation_summary="test",
                )
            ],
        )

        autofilled = apply_completion_recommendation_autofill(itinerary, recommendation)

        afternoon = autofilled.days[0].blocks[0]
        self.assertEqual([item.name for item in afternoon.items], ["思南公馆", "新天地", "田子坊"])
        self.assertEqual(afternoon.items[1].start_time, time(14, 22))
        self.assertEqual(afternoon.items[1].end_time, time(15, 37))
        self.assertIn("思南公馆 和 田子坊 之间", afternoon.items[1].placement_reason or "")

    def test_middle_gap_in_moderately_saturated_block_is_now_more_conservative(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(18, 0),
                    items=[
                        ScheduledPOI(
                            name="武康路咖啡街区",
                            type=POIType.RESTAURANT,
                            city="上海",
                            latitude=31.20458,
                            longitude=121.44284,
                            duration_minutes=60,
                            day=1,
                            start_time=time(13, 0),
                            end_time=time(14, 0),
                            is_fixed=False,
                        ),
                        ScheduledPOI(
                            name="思南公馆",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.21992,
                            longitude=121.46753,
                            duration_minutes=90,
                            day=1,
                            start_time=time(15, 45),
                            end_time=time(17, 15),
                            is_fixed=False,
                        ),
                    ],
                )
            ]
        )

        recommendation = build_itinerary_completion_recommendation(itinerary)

        self.assertIsNone(recommendation)

        forced_recommendation = ItineraryCompletionRecommendation(
            summary="test",
            options=[
                ItineraryCompletionOption(
                    name="新天地",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.AFTERNOON,
                    reasoning_summary="test",
                    itinerary_relation_summary="test",
                )
            ],
        )

        autofilled = apply_completion_recommendation_autofill(itinerary, forced_recommendation)

        afternoon = autofilled.days[0].blocks[0]
        self.assertEqual([item.name for item in afternoon.items], ["武康路咖啡街区", "思南公馆"])

    def test_autofill_skips_too_small_middle_gap(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[
                        ScheduledPOI(
                            name="思南公馆",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.21992,
                            longitude=121.46753,
                            duration_minutes=60,
                            day=1,
                            start_time=time(13, 0),
                            end_time=time(14, 0),
                            is_fixed=False,
                        ),
                        ScheduledPOI(
                            name="田子坊",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.21103,
                            longitude=121.47055,
                            duration_minutes=150,
                            day=1,
                            start_time=time(14, 30),
                            end_time=time(17, 0),
                            is_fixed=False,
                        ),
                    ],
                )
            ]
        )
        recommendation = ItineraryCompletionRecommendation(
            summary="test",
            options=[
                ItineraryCompletionOption(
                    name="新天地",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.AFTERNOON,
                    reasoning_summary="test",
                    itinerary_relation_summary="test",
                )
            ],
        )

        autofilled = apply_completion_recommendation_autofill(itinerary, recommendation)

        afternoon = autofilled.days[0].blocks[0]
        self.assertEqual([item.name for item in afternoon.items], ["思南公馆", "田子坊"])

    def test_autofill_rejects_empty_block_that_only_barely_fits_without_buffer(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(14, 15),
                    items=[],
                )
            ]
        )
        recommendation = ItineraryCompletionRecommendation(
            summary="test",
            options=[
                ItineraryCompletionOption(
                    name="新天地",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.AFTERNOON,
                    reasoning_summary="test",
                    itinerary_relation_summary="test",
                )
            ],
        )

        autofilled = apply_completion_recommendation_autofill(itinerary, recommendation)

        self.assertEqual(autofilled.days[0].blocks[0].items, [])

    def test_completion_recommendation_prefers_restaurant_when_tight_evening_gap_rejects_scenic(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.EVENING,
                    start_time=time(17, 30),
                    end_time=time(18, 35),
                    items=[],
                )
            ]
        )

        recommendation = build_itinerary_completion_recommendation(itinerary)

        self.assertIsNotNone(recommendation)
        option_names = {option.name for option in recommendation.options}
        self.assertIn("武康路咖啡街区", option_names)
        self.assertNotIn("南京路步行街", option_names)

    def test_autofill_keeps_empty_block_insertion_when_buffered_gap_is_sufficient(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(14, 45),
                    items=[],
                )
            ]
        )
        recommendation = ItineraryCompletionRecommendation(
            summary="test",
            options=[
                ItineraryCompletionOption(
                    name="新天地",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.AFTERNOON,
                    reasoning_summary="test",
                    itinerary_relation_summary="test",
                )
            ],
        )

        autofilled = apply_completion_recommendation_autofill(itinerary, recommendation)

        afternoon = autofilled.days[0].blocks[0]
        self.assertEqual([item.name for item in afternoon.items], ["新天地"])
        self.assertEqual(afternoon.items[0].start_time, time(13, 0))
        self.assertEqual(afternoon.items[0].end_time, time(14, 15))

    def test_autofill_keeps_evening_insertion_when_context_aware_slack_is_sufficient(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.EVENING,
                    start_time=time(17, 30),
                    end_time=time(19, 10),
                    items=[],
                )
            ]
        )
        recommendation = ItineraryCompletionRecommendation(
            summary="test",
            options=[
                ItineraryCompletionOption(
                    name="南京路步行街",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.EVENING,
                    reasoning_summary="test",
                    itinerary_relation_summary="test",
                )
            ],
        )

        autofilled = apply_completion_recommendation_autofill(itinerary, recommendation)

        evening = autofilled.days[0].blocks[0]
        self.assertEqual([item.name for item in evening.items], ["南京路步行街"])
        self.assertEqual(evening.items[0].start_time, time(17, 30))
        self.assertEqual(evening.items[0].end_time, time(18, 45))

    def test_profile_aware_gap_fit_allows_light_scenic_but_rejects_heavy_scenic(self) -> None:
        self.assertTrue(
            gap_supports_duration(
                gap_minutes=70,
                duration_minutes=60,
                insertion_kind="empty",
                block_type=TimeBlockType.AFTERNOON,
                poi_type=POIType.SCENIC,
                profile_intensity="light",
            )
        )
        self.assertFalse(
            gap_supports_duration(
                gap_minutes=70,
                duration_minutes=60,
                insertion_kind="empty",
                block_type=TimeBlockType.AFTERNOON,
                poi_type=POIType.SCENIC,
                profile_intensity="heavy",
            )
        )

    def test_recommendation_and_autofill_align_for_light_scenic_profile_candidate(self) -> None:
        itinerary = self.build_manual_itinerary(
            hotel=HotelStay(
                name="人民广场酒店",
                city="上海",
                latitude=31.2304,
                longitude=121.4737,
            ),
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.MORNING,
                    start_time=time(9, 0),
                    end_time=time(12, 0),
                    items=[
                        ScheduledPOI(
                            name="外滩",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.238235,
                            longitude=121.497253,
                            duration_minutes=60,
                            day=1,
                            start_time=time(10, 0),
                            end_time=time(11, 0),
                            is_fixed=False,
                        )
                    ],
                ),
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(14, 10),
                    items=[],
                )
            ],
        )

        recommendation = build_itinerary_completion_recommendation(itinerary)

        self.assertIsNotNone(recommendation)
        self.assertEqual(
            [
                (option.name, option.suggested_block)
                for option in recommendation.options
            ],
            [("人民广场本帮菜午餐", TimeBlockType.AFTERNOON)],
        )

        autofilled = apply_completion_recommendation_autofill(itinerary, recommendation)

        afternoon = next(
            block
            for block in autofilled.days[0].blocks
            if block.block_type == TimeBlockType.AFTERNOON
        )
        self.assertEqual([item.name for item in afternoon.items], ["人民广场本帮菜午餐"])
        self.assertEqual(afternoon.items[0].start_time, time(13, 0))
        self.assertEqual(afternoon.items[0].end_time, time(14, 0))

    def test_autofill_keeps_light_scenic_insertable_when_block_only_has_light_content(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(15, 10),
                    items=[
                        ScheduledPOI(
                            name="外滩",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.238235,
                            longitude=121.497253,
                            duration_minutes=60,
                            day=1,
                            start_time=time(13, 0),
                            end_time=time(14, 0),
                            is_fixed=False,
                        )
                    ],
                )
            ]
        )
        recommendation = ItineraryCompletionRecommendation(
            summary="test",
            options=[
                ItineraryCompletionOption(
                    name="陆家嘴滨江步道",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.AFTERNOON,
                    reasoning_summary="test",
                    itinerary_relation_summary="test",
                )
            ],
        )

        autofilled = apply_completion_recommendation_autofill(itinerary, recommendation)

        afternoon = autofilled.days[0].blocks[0]
        self.assertEqual([item.name for item in afternoon.items], ["外滩", "陆家嘴滨江步道"])
        self.assertEqual(afternoon.items[1].start_time, time(14, 10))
        self.assertEqual(afternoon.items[1].end_time, time(15, 10))

    def test_heavy_existing_block_rejects_second_heavy_scenic_and_recommendation_stays_aligned(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[
                        ScheduledPOI(
                            name="上海博物馆",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.23041,
                            longitude=121.4737,
                            duration_minutes=150,
                            day=1,
                            start_time=time(13, 0),
                            end_time=time(15, 30),
                            is_fixed=False,
                        )
                    ],
                )
            ]
        )

        recommendation = build_itinerary_completion_recommendation(itinerary)

        self.assertIsNotNone(recommendation)
        option_names = {option.name for option in recommendation.options}
        self.assertNotIn("上海自然博物馆", option_names)

        forced_heavy_recommendation = ItineraryCompletionRecommendation(
            summary="test",
            options=[
                ItineraryCompletionOption(
                    name="上海自然博物馆",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.AFTERNOON,
                    reasoning_summary="test",
                    itinerary_relation_summary="test",
                )
            ],
        )

        autofilled = apply_completion_recommendation_autofill(
            itinerary,
            forced_heavy_recommendation,
        )

        afternoon = autofilled.days[0].blocks[0]
        self.assertEqual([item.name for item in afternoon.items], ["上海博物馆"])

    def test_high_scenic_count_block_rejects_third_scenic_candidate(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[
                        ScheduledPOI(
                            name="思南公馆",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.21992,
                            longitude=121.46753,
                            duration_minutes=60,
                            day=1,
                            start_time=time(13, 0),
                            end_time=time(14, 0),
                            is_fixed=False,
                        ),
                        ScheduledPOI(
                            name="田子坊",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.21103,
                            longitude=121.47055,
                            duration_minutes=75,
                            day=1,
                            start_time=time(14, 10),
                            end_time=time(15, 25),
                            is_fixed=False,
                        ),
                    ],
                )
            ]
        )

        recommendation = build_itinerary_completion_recommendation(itinerary)

        self.assertIsNotNone(recommendation)
        option_names = {option.name for option in recommendation.options}
        self.assertNotIn("新天地", option_names)

        forced_recommendation = ItineraryCompletionRecommendation(
            summary="test",
            options=[
                ItineraryCompletionOption(
                    name="新天地",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.AFTERNOON,
                    reasoning_summary="test",
                    itinerary_relation_summary="test",
                )
            ],
        )

        autofilled = apply_completion_recommendation_autofill(itinerary, forced_recommendation)

        afternoon = autofilled.days[0].blocks[0]
        self.assertEqual([item.name for item in afternoon.items], ["思南公馆", "田子坊"])

    def test_light_load_block_still_accepts_second_scenic_candidate(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(16, 35),
                    items=[
                        ScheduledPOI(
                            name="思南公馆",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.21992,
                            longitude=121.46753,
                            duration_minutes=60,
                            day=1,
                            start_time=time(13, 0),
                            end_time=time(14, 0),
                            is_fixed=False,
                        )
                    ],
                )
            ]
        )
        recommendation = ItineraryCompletionRecommendation(
            summary="test",
            options=[
                ItineraryCompletionOption(
                    name="新天地",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.AFTERNOON,
                    reasoning_summary="test",
                    itinerary_relation_summary="test",
                )
            ],
        )

        autofilled = apply_completion_recommendation_autofill(itinerary, recommendation)

        afternoon = autofilled.days[0].blocks[0]
        self.assertEqual([item.name for item in afternoon.items], ["思南公馆", "新天地"])
        self.assertEqual(afternoon.items[1].start_time, time(14, 15))
        self.assertEqual(afternoon.items[1].end_time, time(15, 30))

    def test_high_duration_saturation_block_rejects_additional_scenic_candidate(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[
                        ScheduledPOI(
                            name="新天地",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.21943,
                            longitude=121.47529,
                            duration_minutes=150,
                            day=1,
                            start_time=time(13, 0),
                            end_time=time(15, 30),
                            is_fixed=False,
                        )
                    ],
                )
            ]
        )

        recommendation = build_itinerary_completion_recommendation(itinerary)

        self.assertIsNotNone(recommendation)
        option_names = {option.name for option in recommendation.options}
        self.assertNotIn("思南公馆", option_names)

        forced_recommendation = ItineraryCompletionRecommendation(
            summary="test",
            options=[
                ItineraryCompletionOption(
                    name="思南公馆",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.AFTERNOON,
                    reasoning_summary="test",
                    itinerary_relation_summary="test",
                )
            ],
        )

        autofilled = apply_completion_recommendation_autofill(itinerary, forced_recommendation)

        afternoon = autofilled.days[0].blocks[0]
        self.assertEqual([item.name for item in afternoon.items], ["新天地"])

    def test_saturated_block_rejects_long_scenic_candidate_but_allows_shorter_one(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(19, 40),
                    items=[
                        ScheduledPOI(
                            name="新天地",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.21943,
                            longitude=121.47529,
                            duration_minutes=210,
                            day=1,
                            start_time=time(13, 0),
                            end_time=time(16, 30),
                            is_fixed=False,
                        )
                    ],
                )
            ]
        )

        recommendation = build_itinerary_completion_recommendation(itinerary)

        self.assertIsNotNone(recommendation)
        option_names = {option.name for option in recommendation.options}
        self.assertNotIn("上海自然博物馆", option_names)

        long_recommendation = ItineraryCompletionRecommendation(
            summary="test",
            options=[
                ItineraryCompletionOption(
                    name="上海自然博物馆",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.AFTERNOON,
                    reasoning_summary="test",
                    itinerary_relation_summary="test",
                )
            ],
        )
        short_recommendation = ItineraryCompletionRecommendation(
            summary="test",
            options=[
                ItineraryCompletionOption(
                    name="思南公馆",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.AFTERNOON,
                    reasoning_summary="test",
                    itinerary_relation_summary="test",
                )
            ],
        )

        long_autofilled = apply_completion_recommendation_autofill(itinerary, long_recommendation)
        short_autofilled = apply_completion_recommendation_autofill(itinerary, short_recommendation)

        self.assertEqual(
            [item.name for item in long_autofilled.days[0].blocks[0].items],
            ["新天地"],
        )
        self.assertEqual(
            [item.name for item in short_autofilled.days[0].blocks[0].items],
            ["新天地", "思南公馆"],
        )
        self.assertEqual(short_autofilled.days[0].blocks[0].items[1].start_time, time(16, 55))
        self.assertEqual(short_autofilled.days[0].blocks[0].items[1].end_time, time(18, 10))

    def test_evening_block_enters_saturation_penalty_earlier_than_afternoon(self) -> None:
        evening_itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.EVENING,
                    start_time=time(17, 30),
                    end_time=time(19, 55),
                    items=[
                        ScheduledPOI(
                            name="BFC 外滩枫径",
                            type=POIType.RESTAURANT,
                            city="上海",
                            latitude=31.23374,
                            longitude=121.49759,
                            duration_minutes=60,
                            day=1,
                            start_time=time(17, 30),
                            end_time=time(18, 30),
                            is_fixed=False,
                        )
                    ],
                )
            ]
        )

        recommendation = build_itinerary_completion_recommendation(evening_itinerary)

        self.assertIsNone(recommendation)

        forced_recommendation = ItineraryCompletionRecommendation(
            summary="test",
            options=[
                ItineraryCompletionOption(
                    name="陆家嘴滨江步道",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.EVENING,
                    reasoning_summary="test",
                    itinerary_relation_summary="test",
                )
            ],
        )

        autofilled = apply_completion_recommendation_autofill(
            evening_itinerary,
            forced_recommendation,
        )

        evening = evening_itinerary.days[0].blocks[0]
        self.assertEqual([item.name for item in autofilled.days[0].blocks[0].items], [item.name for item in evening.items])

    def test_afternoon_block_keeps_current_saturation_threshold_behavior(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(15, 25),
                    items=[
                        ScheduledPOI(
                            name="思南公馆",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.21992,
                            longitude=121.46753,
                            duration_minutes=60,
                            day=1,
                            start_time=time(13, 0),
                            end_time=time(14, 0),
                            is_fixed=False,
                        )
                    ],
                )
            ]
        )
        recommendation = ItineraryCompletionRecommendation(
            summary="test",
            options=[
                ItineraryCompletionOption(
                    name="陆家嘴滨江步道",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.AFTERNOON,
                    reasoning_summary="test",
                    itinerary_relation_summary="test",
                )
            ],
        )

        autofilled = apply_completion_recommendation_autofill(itinerary, recommendation)

        afternoon = autofilled.days[0].blocks[0]
        self.assertEqual([item.name for item in afternoon.items], ["思南公馆", "陆家嘴滨江步道"])
        self.assertEqual(afternoon.items[1].start_time, time(14, 10))
        self.assertEqual(afternoon.items[1].end_time, time(15, 10))

    def test_boundary_insertion_keeps_current_saturation_strength(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(16, 45),
                    items=[
                        ScheduledPOI(
                            name="思南公馆",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.21992,
                            longitude=121.46753,
                            duration_minutes=115,
                            day=1,
                            start_time=time(13, 0),
                            end_time=time(14, 55),
                            is_fixed=False,
                        )
                    ],
                )
            ]
        )
        recommendation = ItineraryCompletionRecommendation(
            summary="test",
            options=[
                ItineraryCompletionOption(
                    name="新天地",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.AFTERNOON,
                    reasoning_summary="test",
                    itinerary_relation_summary="test",
                )
            ],
        )

        autofilled = apply_completion_recommendation_autofill(itinerary, recommendation)

        afternoon = autofilled.days[0].blocks[0]
        self.assertEqual([item.name for item in afternoon.items], ["思南公馆", "新天地"])
        self.assertEqual(afternoon.items[1].start_time, time(15, 20))
        self.assertEqual(afternoon.items[1].end_time, time(16, 35))

    def test_autofill_allows_restaurant_but_rejects_scenic_in_same_tight_evening_gap(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.EVENING,
                    start_time=time(17, 30),
                    end_time=time(18, 35),
                    items=[],
                )
            ]
        )
        restaurant_recommendation = ItineraryCompletionRecommendation(
            summary="test",
            options=[
                ItineraryCompletionOption(
                    name="武康路咖啡街区",
                    type=POIType.RESTAURANT,
                    suggested_day=1,
                    suggested_block=TimeBlockType.EVENING,
                    reasoning_summary="test",
                    itinerary_relation_summary="test",
                )
            ],
        )
        scenic_recommendation = ItineraryCompletionRecommendation(
            summary="test",
            options=[
                ItineraryCompletionOption(
                    name="南京路步行街",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.EVENING,
                    reasoning_summary="test",
                    itinerary_relation_summary="test",
                )
            ],
        )

        restaurant_autofilled = apply_completion_recommendation_autofill(
            itinerary,
            restaurant_recommendation,
        )
        scenic_autofilled = apply_completion_recommendation_autofill(
            itinerary,
            scenic_recommendation,
        )

        self.assertEqual(
            [item.name for item in restaurant_autofilled.days[0].blocks[0].items],
            ["武康路咖啡街区"],
        )
        self.assertEqual(
            [item.name for item in scenic_autofilled.days[0].blocks[0].items],
            [],
        )

    def test_autofill_rejects_boundary_gap_that_only_barely_fits_without_buffer(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(16, 30),
                    items=[
                        ScheduledPOI(
                            name="田子坊",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.21103,
                            longitude=121.47055,
                            duration_minutes=60,
                            day=1,
                            start_time=time(14, 15),
                            end_time=time(15, 15),
                            is_fixed=False,
                        )
                    ],
                )
            ]
        )
        recommendation = ItineraryCompletionRecommendation(
            summary="test",
            options=[
                ItineraryCompletionOption(
                    name="新天地",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.AFTERNOON,
                    reasoning_summary="test",
                    itinerary_relation_summary="test",
                )
            ],
        )

        autofilled = apply_completion_recommendation_autofill(itinerary, recommendation)

        afternoon = autofilled.days[0].blocks[0]
        self.assertEqual([item.name for item in afternoon.items], ["田子坊"])

    def test_autofill_rejects_middle_gap_that_only_barely_fits_without_buffer(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 30),
                    items=[
                        ScheduledPOI(
                            name="思南公馆",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.21992,
                            longitude=121.46753,
                            duration_minutes=60,
                            day=1,
                            start_time=time(13, 0),
                            end_time=time(14, 0),
                            is_fixed=False,
                        ),
                        ScheduledPOI(
                            name="田子坊",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.21103,
                            longitude=121.47055,
                            duration_minutes=120,
                            day=1,
                            start_time=time(15, 15),
                            end_time=time(17, 15),
                            is_fixed=False,
                        ),
                    ],
                )
            ]
        )
        recommendation = ItineraryCompletionRecommendation(
            summary="test",
            options=[
                ItineraryCompletionOption(
                    name="新天地",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.AFTERNOON,
                    reasoning_summary="test",
                    itinerary_relation_summary="test",
                )
            ],
        )

        autofilled = apply_completion_recommendation_autofill(itinerary, recommendation)

        afternoon = autofilled.days[0].blocks[0]
        self.assertEqual([item.name for item in afternoon.items], ["思南公馆", "田子坊"])

    def test_autofill_skips_partially_filled_block_when_it_cannot_fit(self) -> None:
        itinerary = self.build_manual_itinerary(
            blocks=[
                DayTimeBlock(
                    block_type=TimeBlockType.MORNING,
                    start_time=time(9, 0),
                    end_time=time(12, 0),
                    items=[],
                ),
                DayTimeBlock(
                    block_type=TimeBlockType.AFTERNOON,
                    start_time=time(13, 0),
                    end_time=time(17, 0),
                    items=[
                        ScheduledPOI(
                            name="上海博物馆",
                            type=POIType.SCENIC,
                            city="上海",
                            latitude=31.23041,
                            longitude=121.4737,
                            duration_minutes=180,
                            day=1,
                            start_time=time(13, 15),
                            end_time=time(16, 45),
                            is_fixed=False,
                        )
                    ],
                ),
                DayTimeBlock(
                    block_type=TimeBlockType.EVENING,
                    start_time=time(17, 30),
                    end_time=time(21, 0),
                    items=[],
                ),
            ]
        )
        recommendation = ItineraryCompletionRecommendation(
            summary="test",
            options=[
                ItineraryCompletionOption(
                    name="新天地",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.AFTERNOON,
                    reasoning_summary="test",
                    itinerary_relation_summary="test",
                )
            ],
        )

        autofilled = apply_completion_recommendation_autofill(itinerary, recommendation)

        afternoon = next(
            block
            for block in autofilled.days[0].blocks
            if block.block_type == TimeBlockType.AFTERNOON
        )
        self.assertEqual([item.name for item in afternoon.items], ["上海博物馆"])


if __name__ == "__main__":
    unittest.main()

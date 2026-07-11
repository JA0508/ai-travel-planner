from __future__ import annotations

import unittest
from datetime import time
from unittest.mock import patch

from app.api.routes.itinerary import (
    apply_trip_intent_patch,
    build_itinerary_response,
    build_itinerary_request_from_regeneration_intent,
    build_itinerary_request_from_parsed_intent,
    build_planning_assumption_summary,
    build_completion_intelligence_summary,
    build_replan_request,
    build_trip_intent_compile_summary,
    build_trip_intent_envelope,
    infer_travel_mode_from_text,
    normalize_optional_pois,
)
from app.core.scheduler import SchedulingError
from app.schemas import (
    AvailabilityWindow,
    DayItinerary,
    DayTimeBlock,
    HotelStay,
    ItineraryCompletionRecommendation,
    ItineraryRequest,
    ItineraryResponse,
    DepartureRecommendation,
    DepartureOption,
    ParsedFixedEvent,
    RawPOIInput,
    PlanningAssumptionSummary,
    PlanningAnchorSource,
    POIType,
    RegenerationIntentSummary,
    ScheduledPOI,
    ScheduledPOISourceType,
    TimeBlockType,
    SparseDaySummary,
    StayOption,
    StayRecommendation,
    TripDaysInputSource,
    TripIntentEnvelopeSource,
    TripIntentPatch,
    TravelMode,
    UserConfirmedReplacement,
)
from app.services.amap_client import GeocodingError
from app.services.mock_normalizer import normalize_poi
from app.services.nl_parser import parse_trip_text_fallback
from app.services.planning_state_transformer import build_planning_input_state


class ConversationalReplanningTests(unittest.TestCase):
    def test_infer_travel_mode_from_text_extracts_explicit_transport_intent(self) -> None:
        self.assertEqual(
            infer_travel_mode_from_text("最后一天火车离开"),
            TravelMode.RAIL,
        )
        self.assertEqual(
            infer_travel_mode_from_text("周日晚高铁回去"),
            TravelMode.HIGH_SPEED_RAIL,
        )
        self.assertEqual(
            infer_travel_mode_from_text("第一天飞机到，最后一天航班回去"),
            TravelMode.AIRPLANE,
        )
        self.assertEqual(
            infer_travel_mode_from_text("这次自驾去西安"),
            TravelMode.CAR,
        )
        self.assertIsNone(infer_travel_mode_from_text("想去西安玩三天"))

    def test_natural_language_request_keeps_estimated_scope_flexible_for_regeneration(
        self,
    ) -> None:
        parsed_intent = parse_trip_text_fallback(
            "想去上海，外滩和武康路，周六下午到，周日晚回去，想轻松一点。"
        )
        planning_state = build_planning_input_state(parsed_intent)

        payload = build_itinerary_request_from_parsed_intent(
            parsed_intent=parsed_intent,
            planning_state=planning_state,
            travel_mode=None,
            auto_fill_sparse_days=True,
        )

        self.assertEqual(payload.trip_days, planning_state.trip_scope_estimate.estimated_trip_days)
        self.assertEqual(payload.trip_days_source, TripDaysInputSource.INTERACTION_ESTIMATED)

        assumptions = build_planning_assumption_summary(
            payload=payload,
            itinerary=ItineraryResponse(
                trip_days=payload.trip_days or 1,
                hotel=HotelStay(
                    name="上海规划锚点",
                    latitude=31.2304,
                    longitude=121.4737,
                ),
                planning_anchor_source=PlanningAnchorSource(
                    source_type="fallback_poi",
                    source_name="上海规划锚点",
                ),
                days=[
                    DayItinerary(
                        day=1,
                        hotel=HotelStay(
                            name="上海规划锚点",
                            latitude=31.2304,
                            longitude=121.4737,
                        ),
                        blocks=[],
                    )
                ],
            ),
            bootstrap_scenic=[],
            bootstrap_restaurants=[],
            request_style_signal=None,
        )

        self.assertEqual(assumptions.trip_days_basis, "interaction_estimated")
        self.assertIsNotNone(assumptions.regeneration_intent)
        self.assertIsNone(assumptions.regeneration_intent.trip_days)
        self.assertEqual(
            assumptions.regeneration_intent.suggested_trip_days,
            payload.trip_days,
        )
        envelope = build_trip_intent_envelope(
            source=TripIntentEnvelopeSource.INITIAL_TEXT,
            assumptions=assumptions,
            raw_text="想去上海，外滩和武康路，周六下午到，周日晚回去，想轻松一点。",
            parsed_intent=parsed_intent,
            planning_state=planning_state,
        )

        self.assertIsNotNone(envelope)
        self.assertEqual(envelope.source, TripIntentEnvelopeSource.INITIAL_TEXT)
        self.assertEqual(envelope.current_intent, assumptions.regeneration_intent)
        self.assertEqual(envelope.parsed_intent, parsed_intent)
        self.assertEqual(envelope.planning_state, planning_state)
        self.assertIsNotNone(envelope.compile_summary)
        self.assertEqual(envelope.compile_summary.trip_days_mode, "interaction_estimated")
        self.assertEqual(
            envelope.compile_summary.scenic_seed_count,
            len(envelope.current_intent.carry_forward_scenic_spots),
        )
        self.assertEqual(envelope.compile_summary.restaurant_seed_count, 0)
        self.assertTrue(envelope.compile_summary.needs_auto_completion)
        self.assertTrue(envelope.summary_lines)

    def test_natural_language_request_pins_explicit_trip_days(self) -> None:
        parsed_intent = parse_trip_text_fallback("去杭州玩两天，想轻松一点。")
        planning_state = build_planning_input_state(parsed_intent)

        payload = build_itinerary_request_from_parsed_intent(
            parsed_intent=parsed_intent,
            planning_state=planning_state,
            travel_mode=None,
            auto_fill_sparse_days=True,
        )

        self.assertEqual(payload.trip_days, 2)
        self.assertEqual(payload.trip_days_source, TripDaysInputSource.EXPLICIT)

    def test_completion_intelligence_summary_rolls_up_skeleton_completion(self) -> None:
        hotel = HotelStay(name="人民广场", latitude=31.2304, longitude=121.4737)
        itinerary = ItineraryResponse(
            trip_days=2,
            hotel=hotel,
            planning_anchor_source=PlanningAnchorSource(
                source_type="fallback_poi",
                source_name="人民广场",
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
                                    name="外滩",
                                    type=POIType.SCENIC,
                                    latitude=31.24,
                                    longitude=121.49,
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
                            start_time=time(12, 0),
                            end_time=time(17, 0),
                            items=[
                                ScheduledPOI(
                                    name="人民广场本帮菜午餐",
                                    type=POIType.RESTAURANT,
                                    latitude=31.23,
                                    longitude=121.47,
                                    duration_minutes=60,
                                    day=1,
                                    start_time=time(12, 30),
                                    end_time=time(13, 30),
                                    is_fixed=False,
                                    source_type=ScheduledPOISourceType.AUTO_SEEDED_MEAL,
                                )
                            ],
                        ),
                        DayTimeBlock(
                            block_type=TimeBlockType.EVENING,
                            start_time=time(18, 0),
                            end_time=time(21, 0),
                            items=[
                                ScheduledPOI(
                                    name="陆家嘴滨江步道",
                                    type=POIType.SCENIC,
                                    latitude=31.24,
                                    longitude=121.5,
                                    duration_minutes=60,
                                    day=1,
                                    start_time=time(19, 0),
                                    end_time=time(20, 0),
                                    is_fixed=False,
                                    source_type=ScheduledPOISourceType.AUTO_FILLED,
                                )
                            ],
                        ),
                    ],
                )
            ],
        )
        planning_assumptions = PlanningAssumptionSummary(
            destination="上海",
            trip_days_basis="interaction_estimated",
            user_seed_scenic_count=1,
            user_seed_restaurant_count=0,
            fixed_event_count=0,
            availability_window_count=0,
            auto_seeded_poi_count=0,
            auto_seeded_meal_count=1,
            auto_filled_count=1,
        )
        completion_recommendation = ItineraryCompletionRecommendation(
            summary="One block is still light.",
            sparse_days=[
                SparseDaySummary(
                    day=2,
                    item_count=1,
                    missing_blocks=[TimeBlockType.AFTERNOON],
                )
            ],
        )
        stay_recommendation = StayRecommendation(
            options=[
                StayOption(
                    option_title="Central base",
                    suggested_area_label="人民广场 / 南京东路",
                    fit_label="Best fit",
                    reasoning_summary="Central to the route.",
                    itinerary_relation_summary="Close to most scheduled stops.",
                )
            ]
        )
        departure_recommendation = DepartureRecommendation(
            options=[
                DepartureOption(
                    option_title="Leave by rail",
                    fit_label="Most convenient",
                    suggested_departure_label="上海虹桥站",
                    reasoning_summary="Closer to the last route cluster.",
                    itinerary_relation_summary="Reduces final-day crossing.",
                )
            ]
        )

        summary = build_completion_intelligence_summary(
            itinerary=itinerary,
            planning_assumptions=planning_assumptions,
            completion_recommendation=completion_recommendation,
            stay_recommendation=stay_recommendation,
            departure_recommendation=departure_recommendation,
        )

        self.assertEqual(summary.trip_completeness, 48)
        self.assertEqual(summary.sparse_blocks_detected, ["Day 2 afternoon"])
        self.assertEqual(summary.auto_filled_scenic_count, 1)
        self.assertEqual(summary.auto_filled_meal_count, 1)
        self.assertEqual(summary.auto_filled_evening_count, 1)
        self.assertEqual(summary.stay_area_recommendation, "人民广场 / 南京东路 · Best fit")
        self.assertEqual(summary.departure_hub_recommendation, "上海虹桥站 · Most convenient")
        self.assertTrue(summary.why_this_plan_works)

    def test_completion_intelligence_score_rewards_density_meals_evening_and_boundaries(self) -> None:
        hotel = HotelStay(name="人民广场", latitude=31.2304, longitude=121.4737)
        day_blocks = [
            DayTimeBlock(
                block_type=TimeBlockType.MORNING,
                start_time=time(9, 0),
                end_time=time(12, 0),
                items=[
                    ScheduledPOI(
                        name="上海博物馆",
                        type=POIType.SCENIC,
                        latitude=31.23,
                        longitude=121.47,
                        duration_minutes=90,
                        day=1,
                        start_time=time(9, 30),
                        end_time=time(11, 0),
                        is_fixed=False,
                    )
                ],
            ),
            DayTimeBlock(
                block_type=TimeBlockType.AFTERNOON,
                start_time=time(12, 0),
                end_time=time(17, 0),
                items=[
                    ScheduledPOI(
                        name="人民广场本帮菜午餐",
                        type=POIType.RESTAURANT,
                        latitude=31.23,
                        longitude=121.47,
                        duration_minutes=60,
                        day=1,
                        start_time=time(12, 30),
                        end_time=time(13, 30),
                        is_fixed=False,
                    )
                ],
            ),
            DayTimeBlock(
                block_type=TimeBlockType.EVENING,
                start_time=time(18, 0),
                end_time=time(21, 0),
                items=[
                    ScheduledPOI(
                        name="城隍庙小吃街",
                        type=POIType.RESTAURANT,
                        latitude=31.22,
                        longitude=121.49,
                        duration_minutes=75,
                        day=1,
                        start_time=time(18, 30),
                        end_time=time(19, 45),
                        is_fixed=False,
                    )
                ],
            ),
        ]
        itinerary = ItineraryResponse(
            trip_days=1,
            hotel=hotel,
            planning_anchor_source=PlanningAnchorSource(
                source_type="fallback_poi",
                source_name="人民广场",
            ),
            days=[DayItinerary(day=1, hotel=hotel, blocks=day_blocks)],
        )
        planning_assumptions = PlanningAssumptionSummary(
            destination="上海",
            trip_days_basis="explicit",
            user_seed_scenic_count=1,
            user_seed_restaurant_count=1,
            fixed_event_count=1,
            availability_window_count=1,
            auto_seeded_poi_count=0,
            auto_seeded_meal_count=0,
            auto_filled_count=0,
        )
        stay_recommendation = StayRecommendation(
            options=[
                StayOption(
                    option_title="Central base",
                    suggested_area_label="人民广场 / 南京东路",
                    fit_label="Best fit",
                    reasoning_summary="Central to the route.",
                    itinerary_relation_summary="Close to most scheduled stops.",
                )
            ]
        )
        departure_recommendation = DepartureRecommendation(
            options=[
                DepartureOption(
                    option_title="Leave by rail",
                    fit_label="Most convenient",
                    suggested_departure_label="上海站",
                    reasoning_summary="Close to the day route.",
                    itinerary_relation_summary="Keeps final transfer simple.",
                )
            ]
        )

        summary = build_completion_intelligence_summary(
            itinerary=itinerary,
            planning_assumptions=planning_assumptions,
            completion_recommendation=ItineraryCompletionRecommendation(summary="No sparse blocks."),
            stay_recommendation=stay_recommendation,
            departure_recommendation=departure_recommendation,
        )

        self.assertGreaterEqual(summary.trip_completeness, 95)
        self.assertEqual(summary.sparse_blocks_detected, [])

    def test_day_relative_availability_sets_minimum_estimated_scope(self) -> None:
        parsed_intent = parse_trip_text_fallback("第一天到得晚，第二天可以早起，第三天中午就走")
        planning_state = build_planning_input_state(parsed_intent)

        self.assertEqual(planning_state.trip_scope_estimate.estimated_trip_days, 3)
        self.assertEqual(planning_state.trip_scope_estimate.confidence.value, "medium")
        self.assertIn("至少需要 3 天", planning_state.trip_scope_estimate.reasoning_summary)

    def test_weekend_arrival_departure_bounds_estimated_scope(self) -> None:
        parsed_intent = parse_trip_text_fallback("周六下午到上海，周日下午三点有个预约，周日晚回去")
        planning_state = build_planning_input_state(parsed_intent)

        self.assertEqual(planning_state.trip_scope_estimate.estimated_trip_days, 2)
        self.assertEqual(planning_state.trip_scope_estimate.confidence.value, "medium")

    def test_generic_fixed_event_does_not_become_route_poi(self) -> None:
        parsed_intent = parse_trip_text_fallback("周六下午到上海，周日下午三点有个预约，周日晚回去")
        planning_state = build_planning_input_state(parsed_intent)

        payload = build_itinerary_request_from_parsed_intent(
            parsed_intent=parsed_intent,
            planning_state=planning_state,
            travel_mode=None,
            auto_fill_sparse_days=True,
        )

        scheduled_seed_names = [
            *(poi.name for poi in payload.scenic_spots),
            *(poi.name for poi in payload.restaurants),
        ]
        self.assertNotIn("预约", scheduled_seed_names)

    def test_replan_request_merges_follow_up_into_current_regenerate_brief(self) -> None:
        base_intent = RegenerationIntentSummary(
            city="上海",
            hotel="人民广场酒店",
            arrival_anchor="上海虹桥",
            departure_anchor="浦东机场",
            availability_windows=[
                AvailabilityWindow(day=1, label="第1天", available_start="14:00"),
            ],
            trip_days=None,
            suggested_trip_days=2,
            trip_days_basis="scheduler_estimated",
            flexible_scenic_spots=["外滩", "豫园"],
            flexible_restaurants=["佳家汤包"],
            fixed_events=[
                ParsedFixedEvent(
                    name="老朋友晚餐",
                    fixed_day=1,
                    fixed_time_start="19:00",
                    fixed_time_end="20:30",
                    category="restaurant",
                )
            ],
            preferences=["轻松"],
            rejected_scenic_spots=["南京路步行街"],
            confirmed_replacements=[
                UserConfirmedReplacement(
                    original_name="南京路步行街",
                    original_type=POIType.SCENIC,
                    replacement_name="豫园",
                    replacement_type=POIType.SCENIC,
                    reasoning_summary="用户想要更有历史感的点",
                )
            ],
            carry_forward_scenic_spots=["外滩", "豫园"],
            carry_forward_restaurants=["佳家汤包"],
        )
        follow_up_intent = parse_trip_text_fallback(
            "第二天下午 3 点到 5 点要去见朋友，想加上武康路，第三天中午前走，不要外滩。"
        )

        payload, notes, interpretation = build_replan_request(
            base_intent=base_intent,
            follow_up_text="第二天下午 3 点到 5 点要去见朋友，想加上武康路，第三天中午前走，不要外滩。",
            follow_up_intent=follow_up_intent,
            auto_fill_sparse_days=True,
        )

        scenic_names = [
            poi.name
            for poi in payload.scenic_spots
            if poi.fixed_day is None and poi.fixed_time_start is None
        ]
        restaurant_names = [
            poi.name
            for poi in payload.restaurants
            if poi.fixed_day is None and poi.fixed_time_start is None
        ]
        fixed_event_names = [
            poi.name
            for poi in payload.scenic_spots + payload.restaurants
            if poi.fixed_day is not None or poi.fixed_time_start is not None
        ]

        self.assertEqual(scenic_names, ["豫园", "武康路"])
        self.assertEqual(restaurant_names, ["佳家汤包"])
        self.assertEqual(payload.rejected_scenic_spots, ["南京路步行街", "外滩"])
        self.assertEqual(len(payload.confirmed_replacements), 1)
        self.assertEqual(payload.confirmed_replacements[0].replacement_name, "豫园")
        self.assertIn("老朋友晚餐", fixed_event_names)
        self.assertIn("见朋友", fixed_event_names)
        self.assertEqual(
            [window.model_dump() for window in payload.availability_windows],
            [
                {
                    "day": 1,
                    "label": "第1天",
                    "available_start": "14:00",
                    "available_end": None,
                },
                {
                    "day": 3,
                    "label": "第3天",
                    "available_start": None,
                    "available_end": "13:00",
                },
            ],
        )
        self.assertTrue(any("外滩" in note for note in notes))
        self.assertEqual(interpretation.added_scenic_spots, ["武康路"])
        self.assertEqual(interpretation.removed_scenic_spots, ["外滩"])
        self.assertEqual(len(interpretation.added_fixed_events), 1)
        self.assertEqual(interpretation.added_fixed_events[0].name, "见朋友")
        self.assertEqual(len(interpretation.added_availability_windows), 1)
        self.assertEqual(interpretation.added_availability_windows[0].available_end, "13:00")
        self.assertTrue(any("Added scenic seeds" in line for line in interpretation.summary_lines))

    def test_replan_request_resets_city_bound_brief_when_destination_changes(self) -> None:
        base_intent = RegenerationIntentSummary(
            city="上海",
            hotel="人民广场酒店",
            arrival_anchor="上海虹桥",
            departure_anchor="浦东机场",
            availability_windows=[
                AvailabilityWindow(day=1, label="第1天", available_start="14:00"),
            ],
            trip_days=2,
            suggested_trip_days=2,
            trip_days_basis="explicit",
            flexible_scenic_spots=["外滩", "豫园"],
            flexible_restaurants=["佳家汤包"],
            fixed_events=[
                ParsedFixedEvent(
                    name="上海演出",
                    fixed_day=1,
                    fixed_time_start="20:00",
                    fixed_time_end="22:00",
                    category="other",
                )
            ],
            preferences=["轻松", "夜景"],
            carry_forward_scenic_spots=["外滩", "豫园"],
            carry_forward_restaurants=["佳家汤包"],
        )
        follow_up_intent = parse_trip_text_fallback("去杭州玩两天，想轻松一点。")

        payload, notes, interpretation = build_replan_request(
            base_intent=base_intent,
            follow_up_text="去杭州玩两天，想轻松一点。",
            follow_up_intent=follow_up_intent,
            auto_fill_sparse_days=True,
        )

        self.assertEqual(payload.city, "杭州")
        self.assertEqual(payload.trip_days, 2)
        self.assertEqual(payload.hotel, None)
        self.assertIsNone(payload.arrival_anchor)
        self.assertIsNone(payload.departure_anchor)
        self.assertEqual(payload.scenic_spots, [])
        self.assertEqual(payload.restaurants, [])
        self.assertEqual(payload.availability_windows, [])
        self.assertEqual(payload.preferences, ["轻松", "夜景", "想轻松一点"])
        self.assertTrue(any("Destination changed from 上海 to 杭州" in note for note in notes))
        self.assertEqual(interpretation.destination_changed_to, "杭州")
        self.assertEqual(interpretation.pinned_trip_days, 2)
        self.assertEqual(interpretation.added_preferences, ["想轻松一点"])
        self.assertTrue(any("Destination changed to 杭州" in line for line in interpretation.summary_lines))

    def test_regeneration_intent_compiles_owned_and_rejected_feedback(self) -> None:
        intent = RegenerationIntentSummary(
            city="上海",
            travel_mode=None,
            hotel=None,
            arrival_anchor="上海虹桥",
            departure_anchor=None,
            availability_windows=[],
            trip_days=None,
            suggested_trip_days=2,
            trip_days_basis="interaction_estimated",
            flexible_scenic_spots=["外滩", "豫园"],
            flexible_restaurants=[],
            fixed_events=[],
            preferences=["轻松"],
            carry_forward_scenic_spots=["外滩", "豫园", "武康路"],
            carry_forward_restaurants=["佳家汤包"],
            rejected_scenic_spots=["外滩"],
            confirmed_replacements=[
                UserConfirmedReplacement(
                    original_name="外滩",
                    original_type=POIType.SCENIC,
                    replacement_name="武康路",
                    replacement_type=POIType.SCENIC,
                )
            ],
        )

        payload = build_itinerary_request_from_regeneration_intent(
            intent,
            auto_fill_sparse_days=True,
        )

        self.assertEqual([poi.name for poi in payload.scenic_spots], ["豫园", "武康路"])
        self.assertEqual([poi.name for poi in payload.restaurants], ["佳家汤包"])
        self.assertEqual(payload.rejected_scenic_spots, ["外滩"])
        self.assertEqual(payload.confirmed_replacements[0].replacement_name, "武康路")
        self.assertIsNone(payload.trip_days)
        compile_summary = build_trip_intent_compile_summary(intent)
        self.assertEqual(compile_summary.rejected_poi_count, 1)
        self.assertEqual(compile_summary.confirmed_replacement_count, 1)
        self.assertFalse(compile_summary.needs_auto_completion)

    def test_trip_intent_patch_updates_manual_seed_and_timing_edits(self) -> None:
        intent = RegenerationIntentSummary(
            city="上海",
            travel_mode=None,
            hotel="人民广场酒店",
            arrival_anchor="上海虹桥",
            departure_anchor=None,
            availability_windows=[],
            trip_days=None,
            suggested_trip_days=2,
            trip_days_basis="interaction_estimated",
            flexible_scenic_spots=["外滩"],
            flexible_restaurants=["佳家汤包"],
            fixed_events=[],
            preferences=["轻松"],
            carry_forward_scenic_spots=["外滩"],
            carry_forward_restaurants=["佳家汤包"],
            rejected_scenic_spots=[],
            rejected_restaurants=[],
        )

        patched = apply_trip_intent_patch(
            intent,
            TripIntentPatch(
                flexible_scenic_spots=["武康路", "豫园"],
                rejected_scenic_spots=["外滩"],
                preferences=["轻松", "夜景"],
                trip_days=3,
            ),
        )

        self.assertEqual(patched.flexible_scenic_spots, ["武康路", "豫园"])
        self.assertEqual(patched.carry_forward_scenic_spots, ["武康路", "豫园"])
        self.assertEqual(patched.rejected_scenic_spots, ["外滩"])
        self.assertEqual(patched.preferences, ["轻松", "夜景"])
        self.assertEqual(patched.trip_days, 3)
        self.assertEqual(patched.trip_days_basis, "explicit")

    def test_regenerate_envelope_planning_state_tracks_current_intent_not_original_parse(
        self,
    ) -> None:
        original_parsed = parse_trip_text_fallback("上海两天，想去外滩。")
        original_planning_state = build_planning_input_state(original_parsed)
        current_intent = RegenerationIntentSummary(
            city="上海",
            travel_mode=None,
            hotel=None,
            arrival_anchor=None,
            departure_anchor=None,
            availability_windows=[],
            trip_days=None,
            suggested_trip_days=2,
            trip_days_basis="interaction_estimated",
            flexible_scenic_spots=["武康路"],
            flexible_restaurants=[],
            fixed_events=[],
            preferences=["轻松"],
            carry_forward_scenic_spots=["武康路"],
            carry_forward_restaurants=[],
            rejected_scenic_spots=["外滩"],
            rejected_restaurants=[],
        )
        assumptions = PlanningAssumptionSummary(
            destination="上海",
            trip_days_basis="interaction_estimated",
            user_seed_scenic_count=1,
            user_seed_restaurant_count=0,
            fixed_event_count=0,
            availability_window_count=0,
            auto_seeded_poi_count=0,
            auto_seeded_meal_count=0,
            auto_filled_count=0,
            regeneration_intent=current_intent,
        )

        envelope = build_trip_intent_envelope(
            source=TripIntentEnvelopeSource.REGENERATE,
            assumptions=assumptions,
            raw_text="上海两天，想去外滩。",
            parsed_intent=original_parsed,
            planning_state=original_planning_state,
        )

        self.assertIsNotNone(envelope)
        self.assertEqual(envelope.parsed_intent.scenic_spots, ["武康路"])
        self.assertEqual(envelope.planning_state.scenic_spots, ["武康路"])
        self.assertNotIn("外滩", envelope.planning_state.scenic_spots)
        self.assertEqual(envelope.planning_state.readiness.level.value, "needs_assumption")

    def test_optional_poi_normalization_uses_request_city_scope(self) -> None:
        raw_poi = RawPOIInput(name="博物馆")

        with patch("app.api.routes.itinerary.normalize_poi") as normalize_poi:
            normalize_poi.return_value = object()
            normalized = normalize_optional_pois(
                raw_pois=[raw_poi],
                poi_type=POIType.SCENIC,
                city="上海",
            )

        self.assertEqual(len(normalized), 1)
        normalize_poi.assert_called_once_with(
            raw_poi=raw_poi,
            poi_type=POIType.SCENIC,
            city="上海",
        )

    def test_optional_poi_normalization_falls_back_to_local_catalog_without_amap(self) -> None:
        raw_poi = RawPOIInput(name="上海博物馆")

        with patch(
            "app.api.routes.itinerary.normalize_poi",
            side_effect=Exception("wrong exception"),
        ):
            with self.assertRaises(Exception):
                normalize_optional_pois(
                    raw_pois=[raw_poi],
                    poi_type=POIType.SCENIC,
                    city="上海",
                )

        with patch(
            "app.api.routes.itinerary.normalize_poi",
            side_effect=GeocodingError("AMAP_API_KEY is not configured."),
        ):
            normalized = normalize_optional_pois(
                raw_pois=[raw_poi],
                poi_type=POIType.SCENIC,
                city="上海",
            )

        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0].name, "上海博物馆")
        self.assertEqual(normalized[0].city, "上海")
        self.assertGreater(normalized[0].latitude, 0)
        self.assertEqual(normalized[0].profile.signal_source, "local_catalog_fallback")
        self.assertIn("live geocoding was unavailable", normalized[0].profile.signal_summary)

    def test_local_catalog_fallback_preserves_fixed_constraints(self) -> None:
        raw_poi = RawPOIInput(
            name="上海博物馆",
            fixed_day=1,
            fixed_time_start="10:00",
            fixed_time_end="11:30",
        )

        with patch(
            "app.api.routes.itinerary.normalize_poi",
            side_effect=GeocodingError("AMAP_API_KEY is not configured."),
        ):
            normalized = normalize_optional_pois(
                raw_pois=[raw_poi],
                poi_type=POIType.SCENIC,
                city="上海",
            )

        self.assertEqual(normalized[0].fixed_day, 1)
        self.assertEqual(normalized[0].fixed_time_start.strftime("%H:%M"), "10:00")
        self.assertEqual(normalized[0].fixed_time_end.strftime("%H:%M"), "11:30")

    def test_local_catalog_fallback_supports_hangzhou_seed_execution(self) -> None:
        raw_poi = RawPOIInput(name="西湖")

        with patch(
            "app.api.routes.itinerary.normalize_poi",
            side_effect=GeocodingError("AMAP_API_KEY is not configured."),
        ):
            normalized = normalize_optional_pois(
                raw_pois=[raw_poi],
                poi_type=POIType.SCENIC,
                city="杭州",
            )

        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0].name, "西湖风景名胜区")
        self.assertEqual(normalized[0].city, "杭州")

    def test_poi_normalization_prefers_live_place_search_for_named_poi(self) -> None:
        with patch(
            "app.services.mock_normalizer.search_place_candidates",
            return_value=[
                {
                    "name": "怪小妹的魔法商店",
                    "type": "购物服务;专卖店",
                    "business_area": "和平区",
                    "latitude": 39.12,
                    "longitude": 117.2,
                }
            ],
        ):
            normalized = normalize_poi(
                RawPOIInput(name="怪小妹的魔法商店"),
                poi_type=POIType.SCENIC,
                city="天津",
            )

        self.assertEqual(normalized.name, "怪小妹的魔法商店")
        self.assertEqual(normalized.city, "天津")
        self.assertEqual(normalized.latitude, 39.12)
        self.assertEqual(normalized.longitude, 117.2)

    def test_unresolved_user_seeds_report_resolution_failure_not_missing_input(self) -> None:
        payload = ItineraryRequest(
            city="天津",
            scenic_spots=[{"name": "天津之眼"}],
            trip_days=2,
            auto_fill_sparse_days=True,
        )

        with patch(
            "app.api.routes.itinerary.normalize_poi",
            side_effect=GeocodingError("AMAP_API_KEY is not configured."),
        ):
            with self.assertRaises(SchedulingError) as error:
                build_itinerary_response(payload)

        self.assertIn("I found trip seeds", str(error.exception))
        self.assertIn("天津之眼", str(error.exception))


if __name__ == "__main__":
    unittest.main()

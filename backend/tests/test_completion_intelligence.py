from __future__ import annotations

import unittest
from datetime import time
from unittest.mock import patch

from app.schemas import (
    BoundaryInfluenceExplanation,
    DayItinerary,
    DayTimeBlock,
    DepartureOption,
    DepartureRecommendation,
    HotelStay,
    ItineraryCompletionOption,
    ItineraryCompletionRecommendation,
    ItineraryResponse,
    PlanningAnchorSource,
    PlanningAssumptionSummary,
    POIType,
    ScheduledPOI,
    ScheduledPOISourceType,
    SparseDaySummary,
    StayOption,
    StayRecommendation,
    TimeBlockType,
    TripIntentEnvelope,
    TripIntentEnvelopeSource,
    RegenerationIntentSummary,
)
from app.api.routes.itinerary import (
    merge_completion_candidate_history,
    refresh_completion_task_itinerary_surfaces,
)
from app.services.completion_intelligence import build_completion_intelligence_summary
from app.services.amap_client import GeocodingError
from app.services.itinerary_completion_recommendation import (
    apply_completion_task_action,
    preview_completion_task_candidates,
)
from app.services.planner_realism_analyzer import analyze_planner_realism
from app.services.preference_policy import build_preference_policy
from app.services.poi_discovery_provider import (
    PoiDiscoveryConfigurationError,
    PoiDiscoveryCandidate,
    PoiDiscoveryCapability,
    PoiDiscoveryUnavailable,
    enforce_poi_discovery_configuration,
    get_poi_discovery_capability,
)
from app.services.stay_recommendation import build_stay_recommendation


class FakePoiDiscoveryProvider:
    def __init__(
        self,
        *,
        around_results: dict[str, list[PoiDiscoveryCandidate]] | None = None,
        text_results: dict[str, list[PoiDiscoveryCandidate]] | None = None,
        enabled: bool = True,
        fail: bool = False,
        required: bool = False,
    ) -> None:
        self.around_results = around_results or {}
        self.text_results = text_results or {}
        self.enabled = enabled
        self.fail = fail
        self.required = required

    def capability(self) -> PoiDiscoveryCapability:
        return PoiDiscoveryCapability(
            provider="fake",
            app_env="test",
            mode="required" if self.required else "fallback",
            required=self.required,
            poi_discovery_enabled=self.enabled,
            text_search_enabled=self.enabled,
            around_search_enabled=self.enabled,
            catalog_fallback_enabled=not self.required,
            missing_config=() if self.enabled else ("AMAP_API_KEY",),
            production_ready=self.enabled or not self.required,
            failure_reason="Missing required config: AMAP_API_KEY"
            if self.required and not self.enabled
            else None,
        )

    def search_text(self, *, keyword: str, city: str, offset: int) -> list[PoiDiscoveryCandidate]:
        if self.fail:
            raise PoiDiscoveryUnavailable("AMAP_API_KEY is not configured.")
        return self.text_results.get(keyword, [])

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
        if self.fail:
            raise PoiDiscoveryUnavailable("AMAP_API_KEY is not configured.")
        return self.around_results.get(keyword, [])


class CompletionIntelligenceTests(unittest.TestCase):
    def test_sparse_blocks_generate_density_penalty_factor(self) -> None:
        summary = build_completion_intelligence_summary(
            itinerary=self.build_itinerary(
                blocks=[
                    self.block(
                        TimeBlockType.MORNING,
                        items=[self.poi("上海博物馆", POIType.SCENIC)],
                    ),
                    self.block(TimeBlockType.AFTERNOON),
                    self.block(TimeBlockType.EVENING),
                ],
            ),
            planning_assumptions=self.assumptions(),
            completion_recommendation=ItineraryCompletionRecommendation(
                summary="Day still has sparse blocks",
                sparse_days=[
                    SparseDaySummary(
                        day=1,
                        item_count=1,
                        missing_blocks=[TimeBlockType.AFTERNOON, TimeBlockType.EVENING],
                    )
                ],
            ),
            stay_recommendation=None,
            departure_recommendation=None,
        )

        factor = self.factor_by_code(
            summary.score_breakdown.density_penalties,
            "sparse_blocks_detected",
        )
        self.assertEqual(factor.value, 2)
        self.assertEqual(factor.impact, -16)
        sparse_task = next(
            task for task in summary.action_tasks if task.task_id == "fill_sparse_block"
        )
        self.assertEqual(sparse_task.task_instance_key, "fill_sparse_block:day-1-afternoon")

    def test_missing_meals_generate_meal_penalty_factor(self) -> None:
        summary = build_completion_intelligence_summary(
            itinerary=self.build_itinerary(
                blocks=[
                    self.block(TimeBlockType.MORNING, items=[self.poi("豫园", POIType.SCENIC)]),
                    self.block(TimeBlockType.AFTERNOON),
                    self.block(TimeBlockType.EVENING),
                ],
            ),
            planning_assumptions=self.assumptions(),
            completion_recommendation=None,
            stay_recommendation=None,
            departure_recommendation=None,
        )

        factor = self.factor_by_code(
            summary.score_breakdown.meals_penalties,
            "missing_meal_slots",
        )
        self.assertEqual(factor.value, 2)
        self.assertEqual(summary.score_breakdown.meals, 0)
        self.assertTrue(
            any(task.task_id == "add_meal_anchor" for task in summary.action_tasks)
        )
        self.assertTrue(all(task.task_instance_key for task in summary.action_tasks))
        meal_tasks = [
            task for task in summary.action_tasks if task.task_id == "add_meal_anchor"
        ]
        self.assertEqual(
            [task.task_instance_key for task in meal_tasks],
            [
                "add_meal_anchor:day-1-afternoon",
                "add_meal_anchor:day-1-evening",
            ],
        )

    def test_missing_evening_generates_evening_penalty_factor(self) -> None:
        summary = build_completion_intelligence_summary(
            itinerary=self.build_itinerary(
                blocks=[
                    self.block(TimeBlockType.MORNING, items=[self.poi("武康路", POIType.SCENIC)]),
                    self.block(
                        TimeBlockType.AFTERNOON,
                        items=[self.poi("咖啡馆", POIType.RESTAURANT)],
                    ),
                    self.block(TimeBlockType.EVENING),
                ],
            ),
            planning_assumptions=self.assumptions(),
            completion_recommendation=None,
            stay_recommendation=None,
            departure_recommendation=None,
        )

        factor = self.factor_by_code(
            summary.score_breakdown.evening_penalties,
            "missing_evening_blocks",
        )
        self.assertEqual(factor.value, 1)
        self.assertEqual(summary.score_breakdown.evening, 0)
        self.assertTrue(
            any(task.task_id == "add_evening_close" for task in summary.action_tasks)
        )
        evening_task = next(
            task for task in summary.action_tasks if task.task_id == "add_evening_close"
        )
        self.assertEqual(evening_task.task_instance_key, "add_evening_close:day-1-evening")

    def test_stay_and_departure_advice_generate_transport_boundary_signals(self) -> None:
        summary = build_completion_intelligence_summary(
            itinerary=self.build_itinerary(
                boundary_explanation=BoundaryInfluenceExplanation(
                    arrival_anchor_influenced=True,
                    departure_anchor_influenced=True,
                ),
                blocks=[
                    self.block(TimeBlockType.MORNING, items=[self.poi("外滩", POIType.SCENIC)]),
                    self.block(
                        TimeBlockType.AFTERNOON,
                        items=[self.poi("本帮菜", POIType.RESTAURANT)],
                    ),
                    self.block(
                        TimeBlockType.EVENING,
                        items=[self.poi("陆家嘴夜景", POIType.SCENIC)],
                    ),
                ],
            ),
            planning_assumptions=self.assumptions(
                fixed_event_count=1,
                availability_window_count=1,
            ),
            completion_recommendation=None,
            stay_recommendation=StayRecommendation(
                options=[
                    StayOption(
                        option_title="Balanced stay option",
                        suggested_area_label="人民广场 / 南京东路",
                        fit_label="Balanced for the whole trip",
                        anchor_pois=["外滩", "上海博物馆"],
                        reasoning_summary="Close to most scheduled stops.",
                        itinerary_relation_summary="Works as a practical base.",
                    )
                ],
            ),
            departure_recommendation=DepartureRecommendation(
                options=[
                    DepartureOption(
                        option_title="Rail-friendly departure option",
                        fit_label="Simpler for a station-style exit",
                        suggested_departure_label="上海站",
                        anchor_pois=["人民广场"],
                        reasoning_summary="Central route exit.",
                        itinerary_relation_summary="Matches final route context.",
                    )
                ],
            ),
        )

        signal_codes = {factor.code for factor in summary.score_breakdown.transport_boundary_signals}
        self.assertIn("stay_area_advice", signal_codes)
        self.assertIn("departure_hub_advice", signal_codes)
        self.assertIn("availability_windows", signal_codes)
        self.assertIn("fixed_events", signal_codes)
        self.assertIn("arrival_boundary", signal_codes)
        self.assertIn("departure_boundary", signal_codes)
        self.assertEqual(
            self.factor_by_code(
                summary.score_breakdown.transport_boundary_signals,
                "departure_hub_advice",
            ).impact,
            20,
        )

    def test_refresh_surfaces_recomputes_completion_without_changing_items(self) -> None:
        itinerary = self.build_itinerary(
            blocks=[
                self.block(TimeBlockType.MORNING, items=[self.poi("豫园", POIType.SCENIC)]),
                self.block(TimeBlockType.AFTERNOON),
                self.block(TimeBlockType.EVENING),
            ],
        )
        stale_summary = build_completion_intelligence_summary(
            itinerary=self.build_itinerary(
                blocks=[
                    self.block(TimeBlockType.MORNING, items=[self.poi("豫园", POIType.SCENIC)]),
                    self.block(
                        TimeBlockType.AFTERNOON,
                        items=[self.poi("午餐", POIType.RESTAURANT)],
                    ),
                    self.block(
                        TimeBlockType.EVENING,
                        items=[self.poi("晚餐", POIType.RESTAURANT)],
                    ),
                ],
            ),
            planning_assumptions=self.assumptions(),
            completion_recommendation=None,
            stay_recommendation=None,
            departure_recommendation=None,
        )
        itinerary = itinerary.model_copy(
            update={
                "planning_assumptions": self.assumptions(),
                "completion_intelligence": stale_summary,
                "trip_intent": self.trip_intent(
                    completion_candidate_history=[
                        ItineraryCompletionOption(
                            name="历史咖啡",
                            type=POIType.RESTAURANT,
                            suggested_day=1,
                            suggested_block=TimeBlockType.AFTERNOON,
                            reasoning_summary="之前出现过的候选。",
                            itinerary_relation_summary="应随 envelope 继续滚动。",
                        )
                    ]
                ),
            }
        )

        refreshed = refresh_completion_task_itinerary_surfaces(
            itinerary,
            preference_policy=build_preference_policy([]),
            request_style_signal=None,
            preferred_mode=None,
            restored_completion_candidates=[
                ItineraryCompletionOption(
                    name="午餐",
                    type=POIType.RESTAURANT,
                    suggested_day=1,
                    suggested_block=TimeBlockType.AFTERNOON,
                    reasoning_summary="刚刚撤销的午餐候选，可重新选择。",
                    itinerary_relation_summary="撤销后只恢复为候选，不自动插回 itinerary。",
                ),
            ],
            completion_candidate_history=[
                ItineraryCompletionOption(
                    name="豫园",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.MORNING,
                    reasoning_summary="已经排入行程的候选不应重复恢复。",
                    itinerary_relation_summary="这个点已经在 itinerary 里。",
                ),
                ItineraryCompletionOption(
                    name="夜景散步",
                    type=POIType.SCENIC,
                    suggested_day=1,
                    suggested_block=TimeBlockType.EVENING,
                    reasoning_summary="刚刚撤销的夜间候选，可重新选择。",
                    itinerary_relation_summary="撤销后只恢复为候选，不自动插回 itinerary。",
                ),
            ],
        )

        self.assertEqual(
            [
                item.name
                for day in refreshed.days
                for block in day.blocks
                for item in block.items
            ],
            ["豫园"],
        )
        self.assertLess(
            refreshed.completion_intelligence.score_breakdown.meals,
            stale_summary.score_breakdown.meals,
        )
        self.assertTrue(
            any(
                task.task_id == "add_meal_anchor"
                for task in refreshed.completion_intelligence.action_tasks
            )
        )
        self.assertIsNotNone(refreshed.completion_recommendation)
        self.assertTrue(
            any(
                option.name == "午餐"
                and option.type == POIType.RESTAURANT
                and option.suggested_day == 1
                and option.suggested_block == TimeBlockType.AFTERNOON
                for option in refreshed.completion_recommendation.options
            )
        )
        self.assertTrue(
            any(
                option.name == "夜景散步"
                and option.type == POIType.SCENIC
                and option.suggested_day == 1
                and option.suggested_block == TimeBlockType.EVENING
                for option in refreshed.completion_recommendation.options
            )
        )
        self.assertFalse(
            any(
                option.name == "豫园"
                and option.type == POIType.SCENIC
                for option in refreshed.completion_recommendation.options
            )
        )
        self.assertIsNotNone(refreshed.trip_intent)
        envelope_history = refreshed.trip_intent.completion_candidate_history
        self.assertTrue(any(option.name == "午餐" for option in envelope_history))
        self.assertTrue(any(option.name == "夜景散步" for option in envelope_history))
        self.assertTrue(any(option.name == "历史咖啡" for option in envelope_history))
        self.assertFalse(any(option.name == "豫园" for option in envelope_history))

    def test_completion_candidate_history_is_bucketed_and_trimmed(self) -> None:
        itinerary = self.build_itinerary(
            blocks=[
                self.block(TimeBlockType.MORNING, items=[self.poi("豫园", POIType.SCENIC)]),
                self.block(TimeBlockType.AFTERNOON),
                self.block(TimeBlockType.EVENING),
            ],
        )
        same_bucket_candidates = [
            ItineraryCompletionOption(
                name=f"下午餐厅 {index}",
                type=POIType.RESTAURANT,
                suggested_day=1,
                suggested_block=TimeBlockType.AFTERNOON,
                reasoning_summary="同一时间段候选。",
                itinerary_relation_summary="用于测试每桶裁剪。",
            )
            for index in range(6)
        ]
        many_bucket_candidates = [
            ItineraryCompletionOption(
                name=f"夜间点 {index}",
                type=POIType.SCENIC,
                suggested_day=(index // 2) + 1,
                suggested_block=TimeBlockType.EVENING,
                reasoning_summary="跨天候选。",
                itinerary_relation_summary="用于测试总量裁剪。",
            )
            for index in range(50)
        ]

        history = merge_completion_candidate_history(
            itinerary,
            same_bucket_candidates,
            many_bucket_candidates,
        )

        self.assertLessEqual(len(history), 40)
        self.assertEqual(
            len(
                [
                    option
                    for option in history
                    if option.suggested_day == 1
                    and option.suggested_block == TimeBlockType.AFTERNOON
                    and option.type == POIType.RESTAURANT
                ]
            ),
            4,
        )

    def test_completion_task_preview_returns_route_compatible_meal_candidates(self) -> None:
        itinerary = self.build_itinerary(
            blocks=[
                self.block(TimeBlockType.MORNING, items=[self.poi("豫园", POIType.SCENIC)]),
                self.block(TimeBlockType.AFTERNOON),
                self.block(TimeBlockType.EVENING),
            ],
        )

        target_day, target_block, _summary, options, source_summary, discovery_status = preview_completion_task_candidates(
            itinerary=itinerary,
            task_id="repair_meal_anchor",
            day=1,
            block_type=TimeBlockType.AFTERNOON,
            preference_policy=build_preference_policy([]),
            request_style_preferences=None,
        )

        self.assertEqual(target_day, 1)
        self.assertEqual(target_block, TimeBlockType.AFTERNOON)
        self.assertGreaterEqual(len(options), 2)
        self.assertLessEqual(len(options), 4)
        self.assertTrue(all(option.type == POIType.RESTAURANT for option in options))
        self.assertIn("本地候选", source_summary or "")
        self.assertEqual(discovery_status, "local_only")

    def test_apply_completion_task_uses_selected_candidate_when_valid(self) -> None:
        itinerary = self.build_itinerary(
            blocks=[
                self.block(TimeBlockType.MORNING, items=[self.poi("豫园", POIType.SCENIC)]),
                self.block(TimeBlockType.AFTERNOON),
                self.block(TimeBlockType.EVENING),
            ],
        )
        _target_day, _target_block, _summary, options, _source_summary, _discovery_status = preview_completion_task_candidates(
            itinerary=itinerary,
            task_id="repair_meal_anchor",
            day=1,
            block_type=TimeBlockType.AFTERNOON,
            preference_policy=build_preference_policy([]),
            request_style_preferences=None,
        )
        selected = options[-1]

        result = apply_completion_task_action(
            itinerary=itinerary,
            task_id="repair_meal_anchor",
            day=1,
            block_type=TimeBlockType.AFTERNOON,
            selected_candidate=selected,
            preference_policy=build_preference_policy([]),
            request_style_preferences=None,
        )

        self.assertTrue(result.applied)
        self.assertIsNotNone(result.inserted_item)
        self.assertEqual(result.inserted_item.name, selected.name)

    def test_apply_completion_task_rejects_stale_selected_candidate(self) -> None:
        itinerary = self.build_itinerary(
            blocks=[
                self.block(TimeBlockType.MORNING, items=[self.poi("豫园", POIType.SCENIC)]),
                self.block(TimeBlockType.AFTERNOON),
                self.block(TimeBlockType.EVENING),
            ],
        )
        stale_candidate = ItineraryCompletionOption(
            name="不存在的候选",
            type=POIType.RESTAURANT,
            suggested_day=1,
            suggested_block=TimeBlockType.AFTERNOON,
            reasoning_summary="Stale option.",
            itinerary_relation_summary="Should not be trusted without backend validation.",
        )

        result = apply_completion_task_action(
            itinerary=itinerary,
            task_id="repair_meal_anchor",
            day=1,
            block_type=TimeBlockType.AFTERNOON,
            selected_candidate=stale_candidate,
            preference_policy=build_preference_policy([]),
            request_style_preferences=None,
        )

        self.assertFalse(result.applied)
        self.assertIsNone(result.inserted_item)

    def test_completion_task_preview_uses_route_context_amap_fallback_when_pool_is_thin(self) -> None:
        itinerary = self.build_itinerary(
            blocks=[
                self.block(TimeBlockType.MORNING, items=[self.poi("豫园", POIType.SCENIC)]),
                self.block(TimeBlockType.AFTERNOON),
                self.block(TimeBlockType.EVENING),
            ],
        )

        fake_provider = FakePoiDiscoveryProvider(
            around_results={
                "午餐": [
                    PoiDiscoveryCandidate(
                        name="顺路小馆",
                        type="餐饮服务;中餐厅",
                        business_area="人民广场",
                        latitude=31.229,
                        longitude=121.476,
                        address=None,
                        typecode=None,
                    ),
                    PoiDiscoveryCandidate(
                        name="午间面馆",
                        type="餐饮服务;快餐厅",
                        business_area="人民广场",
                        latitude=31.231,
                        longitude=121.477,
                        address=None,
                        typecode=None,
                    ),
                ]
            }
        )

        _target_day, _target_block, _summary, options, source_summary, discovery_status = (
            preview_completion_task_candidates(
                itinerary=itinerary,
                task_id="repair_meal_anchor",
                day=1,
                block_type=TimeBlockType.AFTERNOON,
                preference_policy=build_preference_policy([]),
                request_style_preferences=None,
                limit=4,
                poi_discovery_provider=fake_provider,
                minimum_options_before_search=99,
            )
        )

        self.assertGreaterEqual(len(options), 2)
        self.assertIn("路线附近搜索补充", source_summary or "")
        self.assertEqual(discovery_status, "route_context")

        selected = next(option for option in options if option.name == "顺路小馆")
        result = apply_completion_task_action(
            itinerary=itinerary,
            task_id="repair_meal_anchor",
            day=1,
            block_type=TimeBlockType.AFTERNOON,
            selected_candidate=selected,
            completion_candidate_history=options,
            preference_policy=build_preference_policy([]),
            request_style_preferences=None,
        )

        self.assertTrue(result.applied)
        self.assertIsNotNone(result.inserted_item)
        self.assertEqual(result.inserted_item.name, selected.name)

    def test_completion_task_preview_falls_back_to_city_text_search(self) -> None:
        itinerary = self.build_itinerary(
            blocks=[
                self.block(TimeBlockType.MORNING, items=[self.poi("豫园", POIType.SCENIC)]),
                self.block(TimeBlockType.AFTERNOON),
                self.block(TimeBlockType.EVENING),
            ],
        )

        fake_provider = FakePoiDiscoveryProvider(
            text_results={
                "午餐": [
                    PoiDiscoveryCandidate(
                        name="城市搜索午餐",
                        type="餐饮服务;中餐厅",
                        business_area="人民广场",
                        latitude=31.232,
                        longitude=121.476,
                        address=None,
                        typecode=None,
                    )
                ]
            }
        )

        _target_day, _target_block, _summary, options, source_summary, discovery_status = (
            preview_completion_task_candidates(
                itinerary=itinerary,
                task_id="repair_meal_anchor",
                day=1,
                block_type=TimeBlockType.AFTERNOON,
                preference_policy=build_preference_policy([]),
                request_style_preferences=None,
                limit=4,
                poi_discovery_provider=fake_provider,
                minimum_options_before_search=99,
            )
        )

        self.assertTrue(any(option.name == "城市搜索午餐" for option in options))
        self.assertIn("城市搜索补充", source_summary or "")
        self.assertEqual(discovery_status, "city_text")

    def test_completion_task_preview_handles_amap_fallback_failure(self) -> None:
        itinerary = self.build_itinerary(
            blocks=[
                self.block(TimeBlockType.MORNING, items=[self.poi("豫园", POIType.SCENIC)]),
                self.block(TimeBlockType.AFTERNOON),
                self.block(TimeBlockType.EVENING),
            ],
        )

        _target_day, _target_block, _summary, options, source_summary, discovery_status = (
            preview_completion_task_candidates(
                itinerary=itinerary,
                task_id="repair_meal_anchor",
                day=1,
                block_type=TimeBlockType.AFTERNOON,
                preference_policy=build_preference_policy([]),
                request_style_preferences=None,
                limit=4,
                poi_discovery_provider=FakePoiDiscoveryProvider(fail=True),
                minimum_options_before_search=99,
            )
        )

        self.assertGreaterEqual(len(options), 1)
        self.assertIn("Amap", source_summary or "")
        self.assertEqual(discovery_status, "local_only")

    def test_completion_task_preview_reports_unavailable_provider_as_local_only(self) -> None:
        itinerary = self.build_itinerary(
            blocks=[
                self.block(TimeBlockType.MORNING, items=[self.poi("豫园", POIType.SCENIC)]),
                self.block(TimeBlockType.AFTERNOON),
                self.block(TimeBlockType.EVENING),
            ],
        )

        _target_day, _target_block, _summary, options, source_summary, discovery_status = (
            preview_completion_task_candidates(
                itinerary=itinerary,
                task_id="repair_meal_anchor",
                day=1,
                block_type=TimeBlockType.AFTERNOON,
                preference_policy=build_preference_policy([]),
                request_style_preferences=None,
                limit=4,
                poi_discovery_provider=FakePoiDiscoveryProvider(enabled=False),
                minimum_options_before_search=99,
            )
        )

        self.assertGreaterEqual(len(options), 1)
        self.assertIn("未启用实时地点发现", source_summary or "")
        self.assertEqual(discovery_status, "local_only")

    def test_completion_task_preview_required_missing_provider_does_not_use_catalog_as_discovery(self) -> None:
        itinerary = self.build_itinerary(
            blocks=[
                self.block(TimeBlockType.MORNING, items=[self.poi("豫园", POIType.SCENIC)]),
                self.block(TimeBlockType.AFTERNOON),
                self.block(TimeBlockType.EVENING),
            ],
        )

        _target_day, _target_block, _summary, options, source_summary, discovery_status = (
            preview_completion_task_candidates(
                itinerary=itinerary,
                task_id="repair_meal_anchor",
                day=1,
                block_type=TimeBlockType.AFTERNOON,
                preference_policy=build_preference_policy([]),
                request_style_preferences=None,
                limit=4,
                poi_discovery_provider=FakePoiDiscoveryProvider(enabled=False, required=True),
                minimum_options_before_search=99,
            )
        )

        self.assertEqual(len(options), 0)
        self.assertIn("不会展示占位候选", source_summary or "")
        self.assertEqual(discovery_status, "empty")

    def test_poi_discovery_capability_marks_production_missing_key_not_ready(self) -> None:
        with patch.dict("os.environ", {"APP_ENV": "production"}, clear=True):
            capability = get_poi_discovery_capability()

        self.assertFalse(capability.poi_discovery_enabled)
        self.assertFalse(capability.production_ready)
        self.assertEqual(capability.mode, "required")
        self.assertTrue(capability.required)
        self.assertFalse(capability.catalog_fallback_enabled)
        self.assertIn("AMAP_API_KEY", capability.missing_config)
        self.assertIsNotNone(capability.failure_reason)

    def test_poi_discovery_capability_allows_explicit_production_fallback(self) -> None:
        with patch.dict(
            "os.environ",
            {"APP_ENV": "production", "POI_DISCOVERY_MODE": "fallback"},
            clear=True,
        ):
            capability = get_poi_discovery_capability()

        self.assertFalse(capability.poi_discovery_enabled)
        self.assertTrue(capability.production_ready)
        self.assertEqual(capability.mode, "fallback")
        self.assertFalse(capability.required)
        self.assertTrue(capability.catalog_fallback_enabled)

    def test_poi_discovery_capability_validates_invalid_amap_key(self) -> None:
        with patch.dict("os.environ", {"AMAP_API_KEY": "invalid-key"}, clear=True):
            with patch(
                "app.services.poi_discovery_provider.search_place_candidates",
                side_effect=GeocodingError("Amap place search failed: INVALID_USER_KEY"),
            ):
                capability = get_poi_discovery_capability(validate_provider=True)

        self.assertFalse(capability.poi_discovery_enabled)
        self.assertFalse(capability.text_search_enabled)
        self.assertTrue(capability.catalog_fallback_enabled)
        self.assertEqual(capability.missing_config, ())
        self.assertIn("INVALID_USER_KEY", capability.failure_reason or "")

    def test_poi_discovery_startup_guard_blocks_required_invalid_provider(self) -> None:
        with patch.dict(
            "os.environ",
            {"APP_ENV": "production", "AMAP_API_KEY": "invalid-key"},
            clear=True,
        ):
            with patch(
                "app.services.poi_discovery_provider.search_place_candidates",
                side_effect=GeocodingError("Amap place search failed: INVALID_USER_KEY"),
            ):
                with self.assertRaises(PoiDiscoveryConfigurationError):
                    enforce_poi_discovery_configuration()

    def test_poi_discovery_startup_guard_blocks_required_missing_provider(self) -> None:
        with patch.dict("os.environ", {"APP_ENV": "production"}, clear=True):
            with self.assertRaises(PoiDiscoveryConfigurationError):
                enforce_poi_discovery_configuration()

    def test_planner_realism_flags_far_outlier_as_unstable(self) -> None:
        city_stop = self.poi("天津意大利风情旅游区", POIType.SCENIC).model_copy(
            update={
                "city": "天津",
                "latitude": 39.133,
                "longitude": 117.205,
                "duration_minutes": 75,
                "start_time": time(13, 0),
                "end_time": time(14, 15),
            }
        )
        restaurant = self.poi("聚福缘菜馆", POIType.RESTAURANT).model_copy(
            update={
                "city": "天津",
                "latitude": 39.136,
                "longitude": 117.202,
                "duration_minutes": 90,
                "start_time": time(14, 30),
                "end_time": time(16, 0),
            }
        )
        far_museum = self.poi("国家海洋博物馆", POIType.SCENIC).model_copy(
            update={
                "city": "天津",
                "latitude": 39.006,
                "longitude": 117.781,
                "duration_minutes": 150,
                "start_time": time(9, 0),
                "end_time": time(11, 30),
            }
        )
        itinerary = self.build_itinerary(
            blocks=[
                self.block(TimeBlockType.MORNING, items=[far_museum]),
                self.block(TimeBlockType.AFTERNOON, items=[city_stop, restaurant]),
                self.block(TimeBlockType.EVENING),
            ],
        )

        realism = analyze_planner_realism(itinerary)

        self.assertEqual(realism.status, "unstable")
        self.assertTrue(any(issue.code == "distance_outlier" for issue in realism.issues))
        self.assertTrue(any("单独成半日线" in action.label for action in realism.suggested_actions))

    def test_stay_recommendation_uses_region_label_instead_of_poi_chain(self) -> None:
        itinerary = self.build_itinerary(
            blocks=[
                self.block(
                    TimeBlockType.MORNING,
                    items=[
                        self.poi("天津意大利风情旅游区", POIType.SCENIC),
                        self.poi("天津之眼", POIType.SCENIC),
                        self.poi("聚福缘菜馆", POIType.RESTAURANT),
                    ],
                ),
            ],
        )

        recommendation = build_stay_recommendation(itinerary, hotel_was_provided=False)

        self.assertIsNotNone(recommendation)
        assert recommendation is not None
        self.assertTrue(recommendation.options)
        self.assertEqual(recommendation.options[0].suggested_area_label, "天津站 / 意风区一带")
        self.assertEqual(recommendation.options[0].area_source, "keyword_region")

    def build_itinerary(
        self,
        *,
        blocks: list[DayTimeBlock],
        boundary_explanation: BoundaryInfluenceExplanation | None = None,
    ) -> ItineraryResponse:
        hotel = HotelStay(
            name="人民广场酒店",
            city="上海",
            latitude=31.2304,
            longitude=121.4737,
        )
        return ItineraryResponse(
            trip_days=1,
            hotel=hotel,
            planning_anchor_source=PlanningAnchorSource(
                source_type="provided_hotel",
                source_name=hotel.name,
            ),
            boundary_explanation=boundary_explanation or BoundaryInfluenceExplanation(),
            days=[
                DayItinerary(
                    day=1,
                    hotel=hotel,
                    blocks=blocks,
                )
            ],
        )

    def assumptions(
        self,
        *,
        fixed_event_count: int = 0,
        availability_window_count: int = 0,
    ) -> PlanningAssumptionSummary:
        return PlanningAssumptionSummary(
            destination="上海",
            trip_days_basis="explicit",
            trip_scope_estimate=None,
            user_seed_scenic_count=1,
            user_seed_restaurant_count=0,
            fixed_event_count=fixed_event_count,
            availability_window_count=availability_window_count,
            auto_seeded_poi_count=0,
            auto_seeded_meal_count=0,
            auto_filled_count=0,
            meal_structure_applied=True,
            summary_lines=[],
        )

    def trip_intent(
        self,
        *,
        completion_candidate_history: list[ItineraryCompletionOption] | None = None,
    ) -> TripIntentEnvelope:
        return TripIntentEnvelope(
            source=TripIntentEnvelopeSource.DIRECT_GENERATE,
            current_intent=RegenerationIntentSummary(
                city="上海",
                suggested_trip_days=1,
                trip_days_basis="explicit",
            ),
            completion_candidate_history=completion_candidate_history or [],
        )

    def block(
        self,
        block_type: TimeBlockType,
        *,
        items: list[ScheduledPOI] | None = None,
    ) -> DayTimeBlock:
        start, end = {
            TimeBlockType.MORNING: (time(9, 0), time(12, 0)),
            TimeBlockType.AFTERNOON: (time(12, 0), time(17, 30)),
            TimeBlockType.EVENING: (time(18, 0), time(21, 30)),
        }[block_type]
        return DayTimeBlock(
            block_type=block_type,
            start_time=start,
            end_time=end,
            items=items or [],
        )

    def poi(
        self,
        name: str,
        poi_type: POIType,
        *,
        source_type: ScheduledPOISourceType = ScheduledPOISourceType.USER_SEED,
    ) -> ScheduledPOI:
        return ScheduledPOI(
            name=name,
            type=poi_type,
            city="上海",
            latitude=31.2304,
            longitude=121.4737,
            duration_minutes=90,
            day=1,
            start_time=time(9, 30),
            end_time=time(11, 0),
            is_fixed=False,
            source_type=source_type,
        )

    def factor_by_code(self, factors, code: str):
        for factor in factors:
            if factor.code == code:
                return factor
        self.fail(f"Expected score factor code {code!r}, got {[factor.code for factor in factors]}")


if __name__ == "__main__":
    unittest.main()

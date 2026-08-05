from __future__ import annotations

import unittest
from unittest.mock import patch

from app.schemas.intent import ParsedFixedEvent, ParsedTripIntentResponse
from app.services.amap_client import GeocodingError
from app.services.nl_parser import (
    build_parsed_style_attribution_debug_snapshot,
    inspect_parsed_style_attribution_samples,
    normalize_parsed_trip_intent,
    parse_trip_text,
    parse_trip_text_fallback,
)
from app.services.intent_disambiguation import disambiguate_trip_intent
from app.services.preference_policy import (
    StylePreferenceAttribution,
    StylePreferenceSignal,
    summarize_style_preference_attribution,
)
from app.services.planning_state_transformer import build_planning_input_state


class NLParserStyleExtractionTests(unittest.TestCase):
    def test_parse_trip_text_fallback_keeps_chinese_numeral_reservation_range(self) -> None:
        parsed = parse_trip_text_fallback(
            "去杭州玩两天，第二天下午两点到四点预约了中国茶叶博物馆。"
        )

        self.assertEqual(
            [event.model_dump() for event in parsed.fixed_events],
            [{
                "name": "预约",
                "fixed_day": 2,
                "fixed_time_start": "14:00",
                "fixed_time_end": "16:00",
                "category": "other",
            }],
        )

    def test_parse_trip_text_fallback_extracts_city_from_single_sentence_brief(self) -> None:
        parsed = parse_trip_text_fallback("上海，想轻松一点，喜欢夜景和小吃")

        self.assertEqual(parsed.city, "上海")
        self.assertEqual(parsed.preferences, ["想轻松一点", "夜景", "小吃"])

    def test_parse_trip_text_fallback_does_not_treat_generic_desire_as_city(self) -> None:
        parsed = parse_trip_text_fallback("想出去玩")

        self.assertIsNone(parsed.city)

    def test_parse_trip_text_fallback_keeps_city_clean_before_chinese_day_count(self) -> None:
        parsed = parse_trip_text_fallback("上海两天，想去外滩")

        self.assertEqual(parsed.city, "上海")
        self.assertEqual(parsed.trip_days, 2)

    def test_parse_trip_text_fallback_extracts_museum_style_preference(self) -> None:
        parsed = parse_trip_text_fallback(
            """
            城市: 上海
            偏好: 博物馆, 展览
            景点: 上海博物馆
            """
        )

        self.assertEqual(parsed.style_preferences, ["museum"])
        self.assertEqual(parsed.style_preference_sources, {"museum": "explicit"})
        self.assertEqual(parsed._style_preference_evidence, {"museum": "request_wording"})

    def test_parse_trip_text_fallback_extracts_old_street_style_preference(self) -> None:
        parsed = parse_trip_text_fallback(
            """
            城市: 上海
            偏好: citywalk, 老街, 慢慢逛
            景点: 思南公馆
            """
        )

        self.assertEqual(parsed.style_preferences, ["old_street"])
        self.assertEqual(parsed.style_preference_sources, {"old_street": "explicit"})

    def test_parse_trip_text_fallback_extracts_food_stop_and_night_view_styles(self) -> None:
        parsed = parse_trip_text_fallback(
            """
            城市: 上海
            偏好: 咖啡, 小吃, 夜景, 滨江散步
            餐厅: 城隍庙小吃街
            """
        )

        self.assertEqual(parsed.style_preferences, ["food_stop", "night_view"])
        self.assertEqual(
            parsed.style_preference_sources,
            {"food_stop": "explicit", "night_view": "explicit"},
        )
        self.assertEqual(
            parsed._style_preference_evidence,
            {"food_stop": "request_wording", "night_view": "request_wording"},
        )

    def test_parse_trip_text_fallback_stays_conservative_for_weak_signal(self) -> None:
        parsed = parse_trip_text_fallback(
            """
            城市: 上海
            偏好: 轻松一点
            景点: 上海博物馆
            """
        )

        self.assertEqual(parsed.style_preferences, [])
        self.assertEqual(parsed.style_preference_sources, {})

    def test_planning_input_state_carries_parsed_style_preferences(self) -> None:
        parsed = parse_trip_text_fallback(
            """
            城市: 上海
            偏好: 夜景, 江边散步
            景点: 外滩
            """
        )
        planning_state = build_planning_input_state(parsed)

        self.assertEqual(planning_state.style_preferences, ["night_view"])
        self.assertEqual(
            planning_state.style_preference_sources,
            {"night_view": "explicit"},
        )

    def test_normalize_parsed_trip_intent_preserves_inferred_style_sources(self) -> None:
        parsed = parse_trip_text_fallback(
            """
            城市: 上海
            景点: 上海博物馆, 上海自然博物馆
            """
        )

        self.assertEqual(parsed.style_preferences, ["museum"])
        self.assertEqual(parsed.style_preference_sources, {"museum": "inferred"})
        self.assertEqual(parsed._style_preference_evidence, {"museum": "poi_mix"})

    def test_normalize_parsed_trip_intent_upgrades_explicit_wording_over_inferred_source(self) -> None:
        reparsed = ParsedTripIntentResponse(
            city="上海",
            trip_days=None,
            hotel=None,
            arrival_anchor=None,
            departure_anchor=None,
            availability_windows=[],
            scenic_spots=[],
            restaurants=[],
            fixed_events=[],
            preferences=["博物馆", "展览"],
            style_preferences=["museum"],
            style_preference_sources={"museum": "inferred"},
        )
        normalized = normalize_parsed_trip_intent(reparsed)
        planning_state = build_planning_input_state(normalized)

        self.assertEqual(normalized.style_preferences, ["museum"])
        self.assertEqual(
            normalized.style_preference_sources,
            {"museum": "explicit"},
        )
        self.assertEqual(
            planning_state.style_preference_sources,
            {"museum": "explicit"},
        )
        self.assertEqual(
            planning_state._style_preference_evidence,
            {"museum": "request_wording"},
        )

    def test_normalize_parsed_trip_intent_preserves_parser_explicit_evidence_trace(self) -> None:
        reparsed = ParsedTripIntentResponse(
            city="上海",
            trip_days=None,
            hotel=None,
            arrival_anchor=None,
            departure_anchor=None,
            availability_windows=[],
            scenic_spots=[],
            restaurants=[],
            fixed_events=[],
            preferences=[],
            style_preferences=["night_view"],
            style_preference_sources={"night_view": "explicit"},
        )
        normalized = normalize_parsed_trip_intent(reparsed)

        self.assertEqual(normalized.style_preferences, ["night_view"])
        self.assertEqual(
            normalized.style_preference_sources,
            {"night_view": "explicit"},
        )
        self.assertEqual(
            normalized._style_preference_evidence,
            {"night_view": "parser_explicit"},
        )

    def test_normalize_parsed_trip_intent_preserves_parser_inferred_evidence_trace(self) -> None:
        reparsed = ParsedTripIntentResponse(
            city="上海",
            trip_days=None,
            hotel=None,
            arrival_anchor=None,
            departure_anchor=None,
            availability_windows=[],
            scenic_spots=[],
            restaurants=[],
            fixed_events=[],
            preferences=[],
            style_preferences=["museum"],
            style_preference_sources={"museum": "inferred"},
        )
        normalized = normalize_parsed_trip_intent(reparsed)

        self.assertEqual(normalized.style_preferences, ["museum"])
        self.assertEqual(
            normalized.style_preference_sources,
            {"museum": "inferred"},
        )
        self.assertEqual(
            normalized._style_preference_evidence,
            {"museum": "parser_inferred"},
        )

    def test_parser_qa_summary_distinguishes_wording_parser_and_poi_mix_sources(self) -> None:
        explicit_parsed = parse_trip_text_fallback(
            """
            城市: 上海
            偏好: 博物馆, 展览
            """
        )
        inferred_parsed = parse_trip_text_fallback(
            """
            城市: 上海
            景点: 上海博物馆, 上海自然博物馆
            """
        )
        parser_explicit = normalize_parsed_trip_intent(
            ParsedTripIntentResponse(
                city="上海",
                trip_days=None,
                hotel=None,
                arrival_anchor=None,
                departure_anchor=None,
                availability_windows=[],
                scenic_spots=[],
                restaurants=[],
                fixed_events=[],
                preferences=[],
                style_preferences=["night_view"],
                style_preference_sources={"night_view": "explicit"},
            )
        )

        wording_summary = summarize_style_preference_attribution(
            StylePreferenceAttribution(
                signal=StylePreferenceSignal(
                    explicit=frozenset(explicit_parsed.style_preferences)
                ),
                evidence=explicit_parsed._style_preference_evidence,
            )
        )
        poi_summary = summarize_style_preference_attribution(
            StylePreferenceAttribution(
                signal=StylePreferenceSignal(
                    inferred=frozenset(inferred_parsed.style_preferences)
                ),
                evidence=inferred_parsed._style_preference_evidence,
            )
        )
        parser_summary = summarize_style_preference_attribution(
            StylePreferenceAttribution(
                signal=StylePreferenceSignal(
                    explicit=frozenset(parser_explicit.style_preferences)
                ),
                evidence=parser_explicit._style_preference_evidence,
            )
        )

        self.assertEqual(wording_summary.evidence_counts["request_wording"], 1)
        self.assertEqual(poi_summary.evidence_counts["poi_mix"], 1)
        self.assertEqual(parser_summary.evidence_counts["parser_explicit"], 1)

    def test_build_parsed_style_attribution_debug_snapshot_for_parser_inferred(self) -> None:
        normalized = normalize_parsed_trip_intent(
            ParsedTripIntentResponse(
                city="上海",
                trip_days=None,
                hotel=None,
                arrival_anchor=None,
                departure_anchor=None,
                availability_windows=[],
                scenic_spots=[],
                restaurants=[],
                fixed_events=[],
                preferences=[],
                style_preferences=["museum"],
                style_preference_sources={"museum": "inferred"},
            )
        )

        self.assertEqual(
            build_parsed_style_attribution_debug_snapshot(normalized),
            ("museum|inferred|parser_inferred",),
        )

    def test_build_parsed_style_attribution_debug_snapshot_for_explicit_wording(self) -> None:
        parsed = parse_trip_text_fallback(
            """
            城市: 上海
            偏好: 博物馆, 展览
            """
        )

        self.assertEqual(
            build_parsed_style_attribution_debug_snapshot(parsed),
            ("museum|explicit|request_wording",),
        )

    def test_build_parsed_style_attribution_debug_snapshot_for_poi_mix_and_planning_state(self) -> None:
        parsed = parse_trip_text_fallback(
            """
            城市: 上海
            景点: 上海博物馆, 上海自然博物馆
            """
        )
        planning_state = build_planning_input_state(parsed)

        self.assertEqual(
            build_parsed_style_attribution_debug_snapshot(parsed),
            ("museum|inferred|poi_mix",),
        )
        self.assertEqual(
            build_parsed_style_attribution_debug_snapshot(planning_state),
            ("museum|inferred|poi_mix",),
        )

    def test_planning_input_state_marks_too_little_input_as_clarification_needed(self) -> None:
        parsed = parse_trip_text_fallback("想出去玩")
        planning_state = build_planning_input_state(parsed)

        self.assertEqual(planning_state.readiness.level.value, "needs_clarification")
        self.assertFalse(planning_state.readiness.can_generate)
        self.assertIn(
            "too_little_input",
            [issue.code for issue in planning_state.readiness.issues],
        )
        self.assertTrue(planning_state.readiness.clarification_questions)

    def test_planning_input_state_surfaces_auto_assumptions_for_preference_only_input(self) -> None:
        parsed = parse_trip_text_fallback("上海，想轻松一点，喜欢夜景和小吃")
        planning_state = build_planning_input_state(parsed)

        self.assertEqual(planning_state.readiness.level.value, "needs_assumption")
        self.assertTrue(planning_state.readiness.can_generate)
        self.assertIn(
            "preference_only_seed",
            [issue.code for issue in planning_state.readiness.issues],
        )
        self.assertTrue(
            any("seed POIs" in assumption for assumption in planning_state.readiness.auto_assumptions)
        )

    def test_planning_input_state_keeps_seed_poi_generation_non_blocking(self) -> None:
        parsed = parse_trip_text_fallback(
            """
            城市: 上海
            景点: 外滩
            """
        )
        planning_state = build_planning_input_state(parsed)

        self.assertEqual(planning_state.readiness.level.value, "needs_assumption")
        self.assertTrue(planning_state.readiness.can_generate)
        self.assertIn(
            "sparse_seed_pois",
            [issue.code for issue in planning_state.readiness.issues],
        )
        self.assertNotIn(
            "too_little_input",
            [issue.code for issue in planning_state.readiness.issues],
        )

    def test_disambiguation_resolves_generic_poi_with_amap_candidates(self) -> None:
        parsed = ParsedTripIntentResponse(
            city="上海",
            scenic_spots=["博物馆"],
            preferences=["展览"],
        )

        def fake_provider(keyword: str, city: str, offset: int) -> list[dict]:
            self.assertEqual(keyword, "博物馆")
            self.assertEqual(city, "上海")
            return [
                {
                    "name": "上海博物馆",
                    "address": "人民大道201号",
                    "type": "科教文化服务;博物馆",
                    "business_area": "人民广场",
                    "_candidate_source": "amap_place_search",
                },
                {
                    "name": "上海电影博物馆",
                    "address": "漕溪北路",
                    "type": "科教文化服务;博物馆",
                    "business_area": "徐家汇",
                    "_candidate_source": "amap_place_search",
                },
            ]

        disambiguated = disambiguate_trip_intent(
            parsed,
            raw_text="上海想看博物馆和展览",
            candidate_provider=fake_provider,
            llm_selector=lambda *_args: None,
        )

        self.assertEqual(disambiguated.scenic_spots, ["上海博物馆"])
        self.assertIsNotNone(disambiguated.disambiguation_summary)
        self.assertEqual(
            disambiguated.disambiguation_summary.place_resolutions[0].source,
            "amap_place_search",
        )
        planning_state = build_planning_input_state(disambiguated)
        self.assertEqual(
            planning_state.disambiguation_summary.place_resolutions[0].resolved_name,
            "上海博物馆",
        )

    def test_disambiguation_can_use_base_city_hint_for_follow_up(self) -> None:
        parsed = ParsedTripIntentResponse(
            city=None,
            scenic_spots=["武康路"],
        )

        def fake_provider(keyword: str, city: str, offset: int) -> list[dict]:
            self.assertEqual(city, "上海")
            return [
                {
                    "name": "武康路历史文化名街",
                    "address": "徐汇区",
                    "type": "风景名胜;风景名胜相关",
                    "business_area": "衡山路",
                    "_candidate_source": "amap_place_search",
                }
            ]

        disambiguated = disambiguate_trip_intent(
            parsed,
            raw_text="再加个武康路",
            city_hint="上海",
            candidate_provider=fake_provider,
            llm_selector=lambda *_args: None,
        )

        self.assertEqual(disambiguated.city, "上海")
        self.assertEqual(disambiguated.scenic_spots, ["武康路历史文化名街"])
        self.assertEqual(disambiguated.disambiguation_summary.city_source, "hint")

    def test_disambiguation_lets_llm_choose_from_ambiguous_candidates_only(self) -> None:
        parsed = ParsedTripIntentResponse(
            city="上海",
            scenic_spots=["自然"],
        )

        def fake_provider(keyword: str, city: str, offset: int) -> list[dict]:
            return [
                {
                    "name": "上海自然博物馆",
                    "address": "静安区",
                    "type": "科教文化服务;博物馆",
                    "business_area": "静安寺",
                    "_candidate_source": "amap_place_search",
                },
                {
                    "name": "上海自然艺术中心",
                    "address": "黄浦区",
                    "type": "科教文化服务;展览馆",
                    "business_area": "外滩",
                    "_candidate_source": "amap_place_search",
                },
            ]

        disambiguated = disambiguate_trip_intent(
            parsed,
            raw_text="上海想看自然类展览",
            candidate_provider=fake_provider,
            llm_selector=lambda *_args: "上海自然博物馆",
        )

        self.assertEqual(disambiguated.scenic_spots, ["上海自然博物馆"])
        self.assertIsNotNone(disambiguated.disambiguation_summary)
        self.assertIn(
            "上海自然博物馆",
            disambiguated.disambiguation_summary.place_resolutions[0].candidate_names,
        )
        self.assertEqual(
            disambiguated.disambiguation_summary.place_resolutions[0].source,
            "llm_candidate_choice",
        )

    def test_disambiguation_falls_back_to_local_catalog_without_amap(self) -> None:
        parsed = ParsedTripIntentResponse(
            city="上海",
            scenic_spots=["博物馆"],
        )

        with patch(
            "app.services.intent_disambiguation.search_place_candidates",
            side_effect=GeocodingError("AMAP_API_KEY is not configured."),
        ):
            disambiguated = disambiguate_trip_intent(
                parsed,
                raw_text="上海想看博物馆",
                llm_selector=lambda *_args: None,
            )

        self.assertEqual(disambiguated.scenic_spots, ["上海自然博物馆"])
        self.assertEqual(
            disambiguated.disambiguation_summary.place_resolutions[0].source,
            "local_candidate_catalog",
        )

    def test_disambiguation_detects_cross_city_follow_up_before_inheriting_hint(self) -> None:
        parsed = ParsedTripIntentResponse(
            city=None,
            scenic_spots=["西湖"],
        )

        def fake_provider(keyword: str, city: str, offset: int) -> list[dict]:
            self.assertEqual(city, "杭州")
            return [
                {
                    "name": "西湖风景名胜区",
                    "address": "杭州市西湖区",
                    "type": "风景名胜;国家级景点",
                    "business_area": "西湖",
                    "_candidate_source": "amap_place_search",
                }
            ]

        disambiguated = disambiguate_trip_intent(
            parsed,
            raw_text="改去杭州，想去西湖",
            city_hint="上海",
            candidate_provider=fake_provider,
            llm_selector=lambda *_args: None,
        )

        self.assertEqual(disambiguated.city, "杭州")
        self.assertEqual(disambiguated.disambiguation_summary.city_source, "text_disambiguation")
        self.assertEqual(disambiguated.scenic_spots, ["西湖风景名胜区"])

    def test_cross_city_follow_up_uses_local_catalog_when_amap_is_unavailable(self) -> None:
        parsed = ParsedTripIntentResponse(
            city=None,
            scenic_spots=["西湖"],
        )

        with patch(
            "app.services.intent_disambiguation.search_place_candidates",
            side_effect=GeocodingError("AMAP_API_KEY is not configured."),
        ):
            disambiguated = disambiguate_trip_intent(
                parsed,
                raw_text="改去杭州，想去西湖",
                city_hint="上海",
                llm_selector=lambda *_args: None,
            )

        self.assertEqual(disambiguated.city, "杭州")
        self.assertEqual(disambiguated.scenic_spots, ["西湖风景名胜区"])
        self.assertEqual(
            disambiguated.disambiguation_summary.place_resolutions[0].source,
            "local_candidate_catalog",
        )

    def test_build_parsed_style_attribution_debug_snapshot_stays_empty_for_weak_signal(self) -> None:
        parsed = parse_trip_text_fallback(
            """
            城市: 上海
            偏好: 轻松一点
            """
        )

        self.assertEqual(build_parsed_style_attribution_debug_snapshot(parsed), ())

    def test_inspect_parsed_style_attribution_samples_surfaces_compact_per_sample_snapshots(self) -> None:
        report = inspect_parsed_style_attribution_samples(
            [
                (
                    "museum_explicit",
                    """
                    城市: 上海
                    偏好: 博物馆, 展览
                    """,
                ),
                (
                    "museum_poi_mix",
                    """
                    城市: 上海
                    景点: 上海博物馆, 上海自然博物馆
                    """,
                ),
                (
                    "weak_signal",
                    """
                    城市: 上海
                    偏好: 轻松一点
                    """,
                ),
            ],
            parser=parse_trip_text_fallback,
        )

        self.assertEqual(
            tuple(row.label for row in report.rows),
            ("museum_explicit", "museum_poi_mix", "weak_signal"),
        )
        self.assertEqual(report.rows[0].label, "museum_explicit")
        self.assertEqual(
            report.rows[0].debug_snapshot,
            ("museum|explicit|request_wording",),
        )
        self.assertEqual(report.rows[1].label, "museum_poi_mix")
        self.assertEqual(
            report.rows[1].debug_snapshot,
            ("museum|inferred|poi_mix",),
        )
        self.assertEqual(report.rows[2].label, "weak_signal")
        self.assertEqual(report.rows[2].debug_snapshot, ())

    def test_inspect_parsed_style_attribution_samples_aggregates_provenance_counts(self) -> None:
        def inspection_parser(text: str) -> ParsedTripIntentResponse:
            if "PARSER_INFERRED_SAMPLE" in text:
                return normalize_parsed_trip_intent(
                    ParsedTripIntentResponse(
                        city="上海",
                        trip_days=None,
                        hotel=None,
                        arrival_anchor=None,
                        departure_anchor=None,
                        availability_windows=[],
                        scenic_spots=[],
                        restaurants=[],
                        fixed_events=[],
                        preferences=[],
                        style_preferences=["night_view"],
                        style_preference_sources={"night_view": "inferred"},
                    )
                )
            return parse_trip_text_fallback(text)

        report = inspect_parsed_style_attribution_samples(
            [
                (
                    "museum_explicit",
                    """
                    城市: 上海
                    偏好: 博物馆, 展览
                    """,
                ),
                (
                    "citywalk_explicit",
                    """
                    城市: 上海
                    偏好: citywalk, 老街, 慢慢逛
                    """,
                ),
                (
                    "museum_poi_mix",
                    """
                    城市: 上海
                    景点: 上海博物馆, 上海自然博物馆
                    """,
                ),
                (
                    "night_parser_inferred",
                    """
                    PARSER_INFERRED_SAMPLE
                    """,
                ),
                (
                    "weak_signal",
                    """
                    城市: 上海
                    偏好: 轻松一点
                    """,
                ),
            ],
            parser=inspection_parser,
        )

        self.assertEqual(report.total_samples, 5)
        self.assertEqual(report.samples_with_styles, 4)
        self.assertEqual(report.aggregate_source_counts, {"explicit": 2, "inferred": 2})
        self.assertEqual(
            report.aggregate_evidence_counts,
            {
                "request_wording": 2,
                "parser_explicit": 0,
                "parser_inferred": 1,
                "poi_mix": 1,
            },
        )


class NLParserFreeTextFallbackTests(unittest.TestCase):
    def test_parse_trip_text_fallback_extracts_natural_language_trip_request(self) -> None:
        parsed = parse_trip_text_fallback(
            "五一去上海玩三天，想去外滩、武康路、豫园，想吃本帮菜和小吃，"
            "第一天下午两点到上海虹桥，第三天晚上八点前要去浦东机场，喜欢老街和夜景。"
        )

        self.assertEqual(parsed.city, "上海")
        self.assertEqual(parsed.trip_days, 3)
        self.assertEqual(parsed.arrival_anchor, "上海虹桥")
        self.assertEqual(parsed.departure_anchor, "浦东机场")
        self.assertEqual(parsed.scenic_spots, ["外滩", "武康路", "豫园"])
        self.assertEqual(parsed.preferences, ["本帮菜", "小吃", "老街", "夜景"])
        self.assertEqual(
            [window.model_dump() for window in parsed.availability_windows],
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
                    "available_end": "20:00",
                },
            ],
        )

    def test_parse_trip_text_supplements_llm_missing_day_boundary_windows(self) -> None:
        with patch("app.services.nl_parser.parse_trip_text_with_llm") as mock_parser:
            mock_parser.return_value = ParsedTripIntentResponse(
                city="西安",
                trip_days=3,
                scenic_spots=["兵马俑"],
                availability_windows=[],
            )

            parsed = parse_trip_text("第一天中午到，第三天晚上坐火车离开。")

        self.assertEqual(
            [window.model_dump() for window in parsed.availability_windows],
            [
                {
                    "day": 1,
                    "label": "第1天",
                    "available_start": "12:00",
                    "available_end": None,
                },
                {
                    "day": 3,
                    "label": "第3天",
                    "available_start": None,
                    "available_end": "20:00",
                },
            ],
        )

    def test_parse_trip_text_fallback_extracts_tianjin_scattered_seed_brief(self) -> None:
        parsed = parse_trip_text_fallback(
            "我周末想去天津，想去天津之眼，意大利风情街，想吃聚福缘菜馆，"
            "想去著名的国家海洋博物馆，准备去两天左右，我到站为天津西站，"
            "我还想去怪小妹的魔法商店。"
        )

        self.assertEqual(parsed.city, "天津")
        self.assertEqual(parsed.trip_days, 2)
        self.assertEqual(parsed.arrival_anchor, "天津西站")
        self.assertEqual(
            parsed.scenic_spots,
            ["天津之眼", "意大利风情街", "国家海洋博物馆", "怪小妹的魔法商店"],
        )
        self.assertEqual(parsed.restaurants, ["聚福缘菜馆"])

    def test_parse_trip_text_fallback_preserves_weekday_availability_and_soft_preferences(self) -> None:
        parsed = parse_trip_text_fallback(
            "周六下午到上海，周日晚走，想逛老街、citywalk、夜景，最好轻松一点。"
        )

        self.assertEqual(parsed.city, "上海")
        self.assertEqual(parsed.scenic_spots, [])
        self.assertEqual(parsed.preferences, ["老街", "citywalk", "夜景", "轻松"])
        self.assertEqual(
            [window.model_dump() for window in parsed.availability_windows],
            [
                {
                    "day": 1,
                    "label": "周六下午",
                    "available_start": "13:00",
                    "available_end": None,
                },
                {
                    "day": 2,
                    "label": "周日晚上",
                    "available_start": None,
                    "available_end": "20:00",
                },
            ],
        )

    def test_parse_trip_text_fallback_extracts_weekend_fixed_event_and_boundary_constraints(self) -> None:
        parsed = parse_trip_text_fallback(
            "周六下午到上海，周日下午三点有个预约，周日晚回去。"
        )

        self.assertEqual(parsed.city, "上海")
        self.assertEqual(parsed.fixed_events[0].model_dump(), {
            "name": "预约",
            "fixed_day": 2,
            "fixed_time_start": "15:00",
            "fixed_time_end": "17:00",
            "category": "other",
        })
        self.assertEqual(
            [window.model_dump() for window in parsed.availability_windows],
            [
                {
                    "day": 1,
                    "label": "周六下午",
                    "available_start": "13:00",
                    "available_end": None,
                },
                {
                    "day": 2,
                    "label": "周日晚上",
                    "available_start": None,
                    "available_end": "20:00",
                },
            ],
        )

    def test_parse_trip_text_fallback_extracts_fixed_event_with_explicit_time_range(self) -> None:
        parsed = parse_trip_text_fallback(
            "周日下午 3 点到 5 点要去见朋友，其他时间随意。"
        )

        self.assertEqual(len(parsed.fixed_events), 1)
        self.assertEqual(parsed.fixed_events[0].model_dump(), {
            "name": "见朋友",
            "fixed_day": 1,
            "fixed_time_start": "15:00",
            "fixed_time_end": "17:00",
            "category": "other",
        })

    def test_parse_trip_text_fallback_extracts_day_boundary_constraints_and_soft_time_preferences(self) -> None:
        parsed = parse_trip_text_fallback(
            "第一天到得晚，第二天可以早起，第三天中午就走，中间想留一段时间休息，希望每天不要太赶，晚上留给夜景和吃饭。"
        )

        self.assertEqual(
            [window.model_dump() for window in parsed.availability_windows],
            [
                {
                    "day": 1,
                    "label": "第1天",
                    "available_start": "18:00",
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
        self.assertEqual(
            parsed.preferences,
            [
                "第二天可以早起",
                "中间想留一段时间休息",
                "每天不要太赶",
                "晚上留给夜景和吃饭",
            ],
        )

    def test_parse_trip_text_fallback_preserves_soft_partial_day_pacing_preferences(self) -> None:
        parsed = parse_trip_text_fallback(
            "第一天晚上想吃点好的，第二天中午前不要排太满，某天下午有固定行程，其他时间随意。"
        )

        self.assertEqual(
            parsed.preferences,
            ["第一天晚上想吃点好的", "第二天中午前不要排太满"],
        )
        self.assertEqual(len(parsed.fixed_events), 1)
        self.assertEqual(parsed.fixed_events[0].model_dump(), {
            "name": "固定行程",
            "fixed_day": None,
            "fixed_time_start": "13:00",
            "fixed_time_end": "17:00",
            "category": "other",
        })

    def test_parse_trip_text_fallback_does_not_turn_evening_arrangement_preference_into_fixed_event(self) -> None:
        parsed = parse_trip_text_fallback(
            "我想去西安玩三天，晚上安排吃饭和夜游，不要太赶。"
        )

        self.assertEqual(parsed.fixed_events, [])
        self.assertTrue({"吃饭", "夜游"}.issubset(set(parsed.preferences)))

    def test_parse_trip_text_fallback_keeps_broad_interests_out_of_seed_pois(self) -> None:
        parsed = parse_trip_text_fallback(
            "我想去西安玩三天，主要想看历史文化，也想晚上去热闹一点的地方吃东西。"
            "已经想去兵马俑、陕西历史博物馆、大雁塔和西安城墙。"
            "第一天中午到，第三天晚上坐火车离开。希望白天看景点，晚上安排吃饭和夜游，不要太赶。"
        )

        self.assertEqual(parsed.city, "西安")
        self.assertEqual(parsed.trip_days, 3)
        self.assertNotIn("主要想看历史文化", parsed.scenic_spots)
        self.assertNotIn("历史文化", parsed.scenic_spots)
        self.assertEqual(
            parsed.scenic_spots,
            ["兵马俑", "陕西历史博物馆", "大雁塔", "西安城墙"],
        )
        self.assertIn("历史文化", parsed.preferences)
        self.assertIn("夜游", parsed.preferences)

    def test_normalize_parsed_trip_intent_drops_undated_generic_arrangement_artifact(self) -> None:
        parsed = ParsedTripIntentResponse(
            city="西安",
            trip_days=3,
            fixed_events=[
                ParsedFixedEvent(
                    name="有安排",
                    fixed_day=None,
                    fixed_time_start="18:00",
                    fixed_time_end="21:00",
                    category="other",
                )
            ],
            preferences=["晚上安排吃饭和夜游"],
        )

        normalized = normalize_parsed_trip_intent(parsed)

        self.assertEqual(normalized.fixed_events, [])
        self.assertEqual(normalized.preferences, ["晚上安排吃饭和夜游"])

    def test_normalize_parsed_trip_intent_moves_llm_broad_interest_artifact_to_preferences(self) -> None:
        parsed = ParsedTripIntentResponse(
            city="西安",
            trip_days=3,
            scenic_spots=["主要想看历史文化", "陕西历史博物馆", "西安城墙"],
            preferences=[],
        )

        normalized = normalize_parsed_trip_intent(parsed)

        self.assertEqual(normalized.scenic_spots, ["陕西历史博物馆", "西安城墙"])
        self.assertEqual(normalized.preferences, ["历史文化"])

    def test_parse_trip_text_fallback_extracts_departure_anchor_from_anchor_deadline_phrase(self) -> None:
        parsed = parse_trip_text_fallback("最后一天晚上八点前要到机场。")

        self.assertEqual(parsed.departure_anchor, "机场")
        self.assertEqual(
            [window.model_dump() for window in parsed.availability_windows],
            [
                {
                    "day": None,
                    "label": "最后一天",
                    "available_start": None,
                    "available_end": "20:00",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()

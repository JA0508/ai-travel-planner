from __future__ import annotations

import unittest

from app.schemas import NormalizedPOI, POIProfile, POIType, POIVisitStyle, TimeBlockType
from app.services.preference_policy import (
    build_style_preference_attribution,
    build_style_preference_attribution_from_names,
    build_style_preference_debug_snapshot,
    build_style_preference_signal_from_sources,
    build_style_preference_signal,
    infer_request_style_preferences,
    summarize_style_preference_attribution,
)


class PreferencePolicyStyleExtractionTests(unittest.TestCase):
    def build_poi(
        self,
        *,
        name: str,
        poi_type: POIType,
        visit_style: POIVisitStyle,
    ) -> NormalizedPOI:
        return NormalizedPOI(
            name=name,
            type=poi_type,
            city="上海",
            latitude=31.2304,
            longitude=121.4737,
            duration_minutes=60,
            profile=POIProfile(
                visit_style=visit_style,
                best_time_blocks=[TimeBlockType.AFTERNOON],
                typical_duration_minutes=60,
                intensity="medium",
            ),
        )

    def test_infer_request_style_preferences_extracts_explicit_museum_signal(self) -> None:
        styles = infer_request_style_preferences(
            ["想多看博物馆和展览"],
            scenic_spots=[],
            restaurants=[],
        )

        self.assertEqual(styles, {"museum"})

    def test_infer_request_style_preferences_extracts_explicit_wandering_signal(self) -> None:
        styles = infer_request_style_preferences(
            ["想慢慢散步，逛老街和街区"],
            scenic_spots=[],
            restaurants=[],
        )

        self.assertEqual(styles, {"old_street"})

    def test_infer_request_style_preferences_extracts_explicit_food_and_evening_signals(self) -> None:
        styles = infer_request_style_preferences(
            ["想安排咖啡、小吃，也想看夜景和滨江散步"],
            scenic_spots=[],
            restaurants=[],
        )

        self.assertEqual(styles, {"food_stop", "night_view"})

    def test_infer_request_style_preferences_stays_conservative_for_weak_signal(self) -> None:
        styles = infer_request_style_preferences(
            [],
            scenic_spots=[
                self.build_poi(
                    name="上海博物馆",
                    poi_type=POIType.SCENIC,
                    visit_style=POIVisitStyle.MUSEUM,
                )
            ],
            restaurants=[],
        )

        self.assertEqual(styles, set())

    def test_infer_request_style_preferences_uses_strong_request_side_poi_mix(self) -> None:
        styles = infer_request_style_preferences(
            [],
            scenic_spots=[
                self.build_poi(
                    name="上海博物馆",
                    poi_type=POIType.SCENIC,
                    visit_style=POIVisitStyle.MUSEUM,
                ),
                self.build_poi(
                    name="上海自然博物馆",
                    poi_type=POIType.SCENIC,
                    visit_style=POIVisitStyle.MUSEUM,
                ),
            ],
            restaurants=[],
        )

        self.assertEqual(styles, {"museum"})

    def test_build_style_preference_signal_marks_explicit_museum_request(self) -> None:
        signal = build_style_preference_signal(
            preferences=["想多看博物馆和展览"],
            scenic_spots=[],
            restaurants=[],
        )

        self.assertEqual(signal.explicit, frozenset({"museum"}))
        self.assertEqual(signal.inferred, frozenset())
        self.assertEqual(signal.source_for("museum"), "explicit")

    def test_build_style_preference_signal_marks_museum_poi_mix_as_inferred(self) -> None:
        signal = build_style_preference_signal(
            preferences=[],
            scenic_spots=[
                self.build_poi(
                    name="上海博物馆",
                    poi_type=POIType.SCENIC,
                    visit_style=POIVisitStyle.MUSEUM,
                ),
                self.build_poi(
                    name="上海自然博物馆",
                    poi_type=POIType.SCENIC,
                    visit_style=POIVisitStyle.MUSEUM,
                ),
            ],
            restaurants=[],
        )

        self.assertEqual(signal.explicit, frozenset())
        self.assertEqual(signal.inferred, frozenset({"museum"}))
        self.assertEqual(signal.source_for("museum"), "inferred")

    def test_build_style_preference_signal_from_sources_preserves_explicit_and_inferred(self) -> None:
        signal = build_style_preference_signal_from_sources(
            {"museum": "explicit", "night_view": "inferred"}
        )

        self.assertEqual(signal.explicit, frozenset({"museum"}))
        self.assertEqual(signal.inferred, frozenset({"night_view"}))
        self.assertEqual(signal.source_for("museum"), "explicit")
        self.assertEqual(signal.source_for("night_view"), "inferred")

    def test_build_style_preference_signal_upgrades_inferred_source_to_explicit_when_wording_is_explicit(self) -> None:
        signal = build_style_preference_signal(
            preferences=["想多看博物馆和展览"],
            scenic_spots=[],
            restaurants=[],
            parsed_style_preferences=["museum"],
            parsed_style_preference_sources={"museum": "inferred"},
        )

        self.assertEqual(signal.explicit, frozenset({"museum"}))
        self.assertEqual(signal.inferred, frozenset())

    def test_build_style_preference_signal_keeps_explicit_source_from_parser_when_supported(self) -> None:
        signal = build_style_preference_signal(
            preferences=[],
            scenic_spots=[],
            restaurants=[],
            parsed_style_preferences=["night_view"],
            parsed_style_preference_sources={"night_view": "explicit"},
        )

        self.assertEqual(signal.explicit, frozenset({"night_view"}))
        self.assertEqual(signal.inferred, frozenset())

    def test_build_style_preference_attribution_marks_request_wording_evidence(self) -> None:
        attribution = build_style_preference_attribution(
            preferences=["想多看博物馆和展览"],
            scenic_spots=[],
            restaurants=[],
        )

        self.assertEqual(attribution.signal.explicit, frozenset({"museum"}))
        self.assertEqual(attribution.evidence, {"museum": "request_wording"})

    def test_build_style_preference_attribution_marks_poi_mix_evidence(self) -> None:
        attribution = build_style_preference_attribution(
            preferences=[],
            scenic_spots=[
                self.build_poi(
                    name="上海博物馆",
                    poi_type=POIType.SCENIC,
                    visit_style=POIVisitStyle.MUSEUM,
                ),
                self.build_poi(
                    name="上海自然博物馆",
                    poi_type=POIType.SCENIC,
                    visit_style=POIVisitStyle.MUSEUM,
                ),
            ],
            restaurants=[],
        )

        self.assertEqual(attribution.signal.inferred, frozenset({"museum"}))
        self.assertEqual(attribution.evidence, {"museum": "poi_mix"})

    def test_build_style_preference_attribution_preserves_parser_explicit_evidence(self) -> None:
        attribution = build_style_preference_attribution_from_names(
            preferences=[],
            scenic_spot_names=[],
            restaurant_names=[],
            parsed_style_preferences=["night_view"],
            parsed_style_preference_sources={"night_view": "explicit"},
        )

        self.assertEqual(attribution.signal.explicit, frozenset({"night_view"}))
        self.assertEqual(attribution.evidence, {"night_view": "parser_explicit"})

    def test_build_style_preference_attribution_preserves_parser_inferred_evidence(self) -> None:
        attribution = build_style_preference_attribution_from_names(
            preferences=[],
            scenic_spot_names=[],
            restaurant_names=[],
            parsed_style_preferences=["museum"],
            parsed_style_preference_sources={"museum": "inferred"},
        )

        self.assertEqual(attribution.signal.inferred, frozenset({"museum"}))
        self.assertEqual(attribution.evidence, {"museum": "parser_inferred"})

    def test_summarize_style_preference_attribution_distinguishes_sources_and_evidence(self) -> None:
        attribution = build_style_preference_attribution_from_names(
            preferences=["想多看博物馆和展览"],
            scenic_spot_names=[],
            restaurant_names=[],
            parsed_style_preferences=["museum", "night_view"],
            parsed_style_preference_sources={"museum": "inferred", "night_view": "explicit"},
        )

        summary = summarize_style_preference_attribution(attribution)

        self.assertEqual(summary.total_styles, 2)
        self.assertEqual(summary.explicit_count, 2)
        self.assertEqual(summary.inferred_count, 0)
        self.assertEqual(summary.styles_by_source["explicit"], ("museum", "night_view"))
        self.assertEqual(summary.styles_by_evidence["request_wording"], ("museum",))
        self.assertEqual(summary.styles_by_evidence["parser_explicit"], ("night_view",))
        self.assertEqual(summary.styles_by_evidence["parser_inferred"], ())
        self.assertEqual(summary.evidence_counts["poi_mix"], 0)

    def test_build_style_preference_debug_snapshot_is_compact_and_stable(self) -> None:
        attribution = build_style_preference_attribution_from_names(
            preferences=["想多看博物馆和展览"],
            scenic_spot_names=[],
            restaurant_names=[],
            parsed_style_preferences=["museum", "night_view"],
            parsed_style_preference_sources={"museum": "inferred", "night_view": "explicit"},
        )

        snapshot = build_style_preference_debug_snapshot(attribution)

        self.assertEqual(
            snapshot,
            (
                "museum|explicit|request_wording",
                "night_view|explicit|parser_explicit",
            ),
        )

    def test_build_style_preference_debug_snapshot_marks_parser_inferred(self) -> None:
        attribution = build_style_preference_attribution_from_names(
            preferences=[],
            scenic_spot_names=[],
            restaurant_names=[],
            parsed_style_preferences=["museum"],
            parsed_style_preference_sources={"museum": "inferred"},
        )

        self.assertEqual(
            build_style_preference_debug_snapshot(attribution),
            ("museum|inferred|parser_inferred",),
        )


if __name__ == "__main__":
    unittest.main()

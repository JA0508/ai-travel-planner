from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tools.inspect_parsed_style_attribution import (
    DEFAULT_INTERNAL_SAMPLE_PATH,
    DEFAULT_REALISTIC_SAMPLE_PATH,
    DEFAULT_STRICT_SAMPLE_PATH,
    SAMPLE_SET_PATHS,
    format_inspection_summary_text,
    format_inspection_report_text,
    inspect_request_sample_specs,
    inspection_report_to_dict,
    load_request_samples,
    load_request_sample_specs,
    main,
)


class ParseStyleDebugRunnerTests(unittest.TestCase):
    def strict_sample_path(self) -> Path:
        return DEFAULT_STRICT_SAMPLE_PATH

    def realistic_sample_path(self) -> Path:
        return DEFAULT_REALISTIC_SAMPLE_PATH

    def internal_sample_path(self) -> Path:
        return DEFAULT_INTERNAL_SAMPLE_PATH

    def write_sample_file(self) -> str:
        records = [
            {"label": "museum_explicit", "text": "城市: 上海\n偏好: 博物馆, 展览"},
            {"label": "museum_poi_mix", "text": "城市: 上海\n景点: 上海博物馆, 上海自然博物馆"},
            {"label": "weak_signal", "text": "城市: 上海\n偏好: 轻松一点"},
        ]
        handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".jsonl", delete=False)
        with handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return handle.name

    def test_load_request_samples_reads_jsonl_file(self) -> None:
        path = self.write_sample_file()

        self.assertEqual(
            load_request_samples(path),
            [
                ("museum_explicit", "城市: 上海\n偏好: 博物馆, 展览"),
                ("museum_poi_mix", "城市: 上海\n景点: 上海博物馆, 上海自然博物馆"),
                ("weak_signal", "城市: 上海\n偏好: 轻松一点"),
            ],
        )

    def test_load_request_sample_specs_preserves_override_modes(self) -> None:
        sample_path = self.strict_sample_path()

        specs = load_request_sample_specs(sample_path)

        self.assertEqual(specs[0].label, "museum_explicit")
        self.assertEqual(specs[0].parser_mode, "fallback")
        self.assertEqual(specs[7].label, "mixed_explicit_dominates")
        self.assertEqual(specs[7].parser_mode, "normalized_override")
        self.assertEqual(specs[7].style_preference_sources, {"museum": "inferred"})
        self.assertEqual(specs[8].label, "parser_explicit_night_view")
        self.assertEqual(specs[8].style_preference_sources, {"night_view": "explicit"})
        self.assertEqual(specs[9].label, "parser_inferred_night_view")
        self.assertEqual(specs[9].style_preference_sources, {"night_view": "inferred"})

    def test_runner_outputs_human_readable_batch_report(self) -> None:
        path = self.write_sample_file()
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            exit_code = main([path, "--parser", "fallback", "--format", "text"])

        output = buffer.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Total samples: 3", output)
        self.assertIn("explicit: 1", output)
        self.assertIn("inferred: 1", output)
        self.assertIn("museum_explicit: museum|explicit|request_wording", output)
        self.assertIn("museum_poi_mix: museum|inferred|poi_mix", output)
        self.assertIn("weak_signal: -", output)

    def test_runner_outputs_json_batch_report(self) -> None:
        path = self.write_sample_file()
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            exit_code = main([path, "--parser", "fallback", "--format", "json"])

        payload = json.loads(buffer.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["total_samples"], 3)
        self.assertEqual(payload["samples_with_styles"], 2)
        self.assertEqual(payload["aggregate_source_counts"], {"explicit": 1, "inferred": 1})
        self.assertEqual(
            payload["aggregate_evidence_counts"],
            {
                "request_wording": 1,
                "parser_explicit": 0,
                "parser_inferred": 0,
                "poi_mix": 1,
            },
        )

    def test_report_formatters_stay_stable(self) -> None:
        sample_path = self.strict_sample_path()
        report = inspect_request_sample_specs(load_request_sample_specs(sample_path))

        report_dict = inspection_report_to_dict(report)
        report_text = format_inspection_report_text(report)
        summary_text = format_inspection_summary_text(report, sample_set_name="strict")

        self.assertEqual(report.total_samples, 10)
        self.assertEqual(report.samples_with_styles, 9)
        self.assertIn("citywalk_explicit", report_text)
        self.assertIn("night_view_explicit", report_text)
        self.assertIn("museum|explicit|request_wording", report_text)
        self.assertIn("museum|inferred|poi_mix", report_text)
        self.assertIn("night_view|explicit|parser_explicit", report_text)
        self.assertIn("night_view|inferred|parser_inferred", report_text)
        self.assertEqual(report_dict["aggregate_source_counts"]["explicit"], 6)
        self.assertEqual(report_dict["aggregate_source_counts"]["inferred"], 3)
        self.assertEqual(
            report_dict["aggregate_evidence_counts"],
            {
                "request_wording": 5,
                "parser_explicit": 1,
                "parser_inferred": 1,
                "poi_mix": 2,
            },
        )
        self.assertIn("Strict status: PASS", summary_text)
        self.assertIn("Styled: 9/10", summary_text)
        self.assertIn("Sources: explicit=6 inferred=3", summary_text)

    def test_realistic_corpus_stays_inspectable_without_brittle_counts(self) -> None:
        report = inspect_request_sample_specs(
            load_request_sample_specs(self.realistic_sample_path())
        )

        report_dict = inspection_report_to_dict(report)
        labels = {row["label"] for row in report_dict["rows"]}
        row_map = {row["label"]: row for row in report_dict["rows"]}

        self.assertEqual(report.total_samples, 9)
        self.assertGreaterEqual(report.samples_with_styles, 7)
        self.assertEqual(labels, {
            "museum_weekend_request",
            "citywalk_old_street_request",
            "cafe_break_request",
            "riverside_evening_request",
            "mixed_museum_citywalk_evening_request",
            "weak_open_request",
            "museum_named_spots_request",
            "old_street_named_spots_request",
            "soft_evening_parser_inferred_request",
        })
        self.assertIn("museum|explicit|request_wording", row_map["museum_weekend_request"]["debug_snapshot"])
        self.assertIn("old_street|inferred|poi_mix", row_map["old_street_named_spots_request"]["debug_snapshot"])
        self.assertIn("night_view|inferred|parser_inferred", row_map["soft_evening_parser_inferred_request"]["debug_snapshot"])
        self.assertEqual(row_map["weak_open_request"]["debug_snapshot"], [])
        self.assertGreaterEqual(report_dict["aggregate_source_counts"]["explicit"], 5)
        self.assertGreaterEqual(report_dict["aggregate_source_counts"]["inferred"], 3)
        self.assertGreaterEqual(report_dict["aggregate_evidence_counts"]["request_wording"], 5)
        self.assertGreaterEqual(report_dict["aggregate_evidence_counts"]["poi_mix"], 2)
        self.assertGreaterEqual(report_dict["aggregate_evidence_counts"]["parser_inferred"], 1)

    def test_runner_supports_named_realistic_sample_set(self) -> None:
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            exit_code = main(["--sample-set", "realistic", "--format", "json"])

        payload = json.loads(buffer.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["total_samples"], 9)
        self.assertGreaterEqual(payload["samples_with_styles"], 7)
        self.assertEqual(SAMPLE_SET_PATHS["strict"], self.strict_sample_path())
        self.assertEqual(SAMPLE_SET_PATHS["realistic"], self.realistic_sample_path())
        labels = {row["label"] for row in payload["rows"]}
        self.assertIn("museum_weekend_request", labels)
        self.assertIn("soft_evening_parser_inferred_request", labels)

    def test_runner_outputs_summary_for_strict_sample_set(self) -> None:
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            exit_code = main(["--sample-set", "strict", "--summary"])

        output = buffer.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Sample set: strict", output)
        self.assertIn("Strict status: PASS", output)
        self.assertIn("Styled: 9/10", output)
        self.assertIn("Sources: explicit=6 inferred=3", output)

    def test_runner_outputs_summary_for_realistic_sample_set(self) -> None:
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            exit_code = main(["--sample-set", "realistic", "--summary"])

        output = buffer.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Sample set: realistic", output)
        self.assertIn("Corpus status: OBSERVE", output)
        self.assertIn("Styled: 8/9", output)
        self.assertIn("Sources: explicit=8 inferred=3", output)

    def test_runner_outputs_summary_for_internal_sample_set(self) -> None:
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            exit_code = main(["--sample-set", "internal", "--summary"])

        output = buffer.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("Sample set: internal", output)
        self.assertIn("Corpus status: OBSERVE", output)
        self.assertIn("Styled: 9/10", output)
        self.assertIn("Sources: explicit=9 inferred=3", output)

    def test_runner_outputs_summary_for_all_sample_sets(self) -> None:
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            exit_code = main(["--sample-set", "all", "--summary"])

        output = buffer.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("[STRICT]", output)
        self.assertIn("Strict status: PASS", output)
        self.assertIn("[REALISTIC]", output)
        self.assertIn("Styled: 8/9", output)
        self.assertIn("[INTERNAL]", output)
        self.assertIn("Styled: 9/10", output)
        self.assertEqual(output.count("Sources:"), 3)

    def test_internal_corpus_is_inspectable_without_brittle_distribution_assertions(self) -> None:
        report = inspect_request_sample_specs(
            load_request_sample_specs(self.internal_sample_path())
        )

        report_dict = inspection_report_to_dict(report)
        labels = {row["label"] for row in report_dict["rows"]}
        row_map = {row["label"]: row for row in report_dict["rows"]}

        self.assertEqual(report.total_samples, 10)
        self.assertGreaterEqual(report.samples_with_styles, 8)
        self.assertIn("internal_museum_focused_long_weekend", labels)
        self.assertIn("internal_parser_inferred_evening_mood", labels)
        self.assertIn(
            "museum|explicit|request_wording",
            row_map["internal_museum_focused_long_weekend"]["debug_snapshot"],
        )
        self.assertIn(
            "old_street|inferred|poi_mix",
            row_map["internal_named_wandering_route"]["debug_snapshot"],
        )
        self.assertIn(
            "night_view|inferred|parser_inferred",
            row_map["internal_parser_inferred_evening_mood"]["debug_snapshot"],
        )
        self.assertIn(
            "museum|explicit|request_wording",
            row_map["internal_explicit_beats_inferred_museum"]["debug_snapshot"],
        )
        self.assertEqual(row_map["internal_open_ended_relaxed"]["debug_snapshot"], [])
        self.assertGreaterEqual(report_dict["aggregate_source_counts"]["explicit"], 5)
        self.assertGreaterEqual(report_dict["aggregate_source_counts"]["inferred"], 3)
        self.assertGreaterEqual(report_dict["aggregate_evidence_counts"]["request_wording"], 4)
        self.assertGreaterEqual(report_dict["aggregate_evidence_counts"]["poi_mix"], 2)
        self.assertGreaterEqual(report_dict["aggregate_evidence_counts"]["parser_inferred"], 1)

    def test_runner_supports_named_internal_sample_set(self) -> None:
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            exit_code = main(["--sample-set", "internal", "--format", "json"])

        payload = json.loads(buffer.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["total_samples"], 10)
        self.assertGreaterEqual(payload["samples_with_styles"], 8)
        self.assertEqual(SAMPLE_SET_PATHS["internal"], self.internal_sample_path())
        labels = {row["label"] for row in payload["rows"]}
        self.assertIn("internal_museum_focused_long_weekend", labels)
        self.assertIn("internal_explicit_beats_inferred_museum", labels)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from collections.abc import Callable

from app.schemas.intent import ParsedTripIntentResponse
from app.services.nl_parser import (
    ParsedStyleAttributionInspectionReport,
    inspect_parsed_style_attribution_parsed_samples,
    parse_trip_text,
    parse_trip_text_fallback,
    normalize_parsed_trip_intent,
)

TOOLS_DIR = Path(__file__).resolve().parent
DEFAULT_STRICT_SAMPLE_PATH = TOOLS_DIR / "samples" / "style_attribution_samples.jsonl"
DEFAULT_REALISTIC_SAMPLE_PATH = (
    TOOLS_DIR / "samples" / "style_attribution_realistic_corpus.jsonl"
)
DEFAULT_INTERNAL_SAMPLE_PATH = (
    TOOLS_DIR / "samples" / "style_attribution_internal_corpus.jsonl"
)
SAMPLE_SET_PATHS = {
    "strict": DEFAULT_STRICT_SAMPLE_PATH,
    "realistic": DEFAULT_REALISTIC_SAMPLE_PATH,
    "internal": DEFAULT_INTERNAL_SAMPLE_PATH,
}
SAMPLE_SET_CHOICES = (*SAMPLE_SET_PATHS.keys(), "all")
STRICT_BASELINE = {
    "total_samples": 10,
    "samples_with_styles": 9,
    "aggregate_source_counts": {"explicit": 6, "inferred": 3},
    "aggregate_evidence_counts": {
        "request_wording": 5,
        "parser_explicit": 1,
        "parser_inferred": 1,
        "poi_mix": 2,
    },
}


@dataclass(frozen=True, slots=True)
class RequestSampleSpec:
    label: str
    text: str
    parser_mode: str = "fallback"
    style_preferences: tuple[str, ...] = ()
    style_preference_sources: dict[str, str] = field(default_factory=dict)


def load_request_sample_specs(path: str | Path) -> list[RequestSampleSpec]:
    specs: list[RequestSampleSpec] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        record = json.loads(stripped)
        label = str(record["label"]).strip()
        text = str(record["text"]).strip()
        if not label or not text:
            continue
        specs.append(
            RequestSampleSpec(
                label=label,
                text=text,
                parser_mode=str(record.get("parser_mode", "fallback")).strip() or "fallback",
                style_preferences=tuple(record.get("style_preferences", [])),
                style_preference_sources=dict(record.get("style_preference_sources", {})),
            )
        )
    return specs


def load_request_samples(path: str | Path) -> list[tuple[str, str]]:
    return [(spec.label, spec.text) for spec in load_request_sample_specs(path)]


def parse_sample_spec(
    spec: RequestSampleSpec,
    *,
    default_parser: Callable[[str], ParsedTripIntentResponse] = parse_trip_text_fallback,
) -> ParsedTripIntentResponse:
    if spec.parser_mode == "fallback":
        return default_parser(spec.text)
    if spec.parser_mode == "main":
        return parse_trip_text(spec.text)
    if spec.parser_mode == "normalized_override":
        base = parse_trip_text_fallback(spec.text)
        reparsed = ParsedTripIntentResponse(
            city=base.city,
            trip_days=base.trip_days,
            hotel=base.hotel,
            arrival_anchor=base.arrival_anchor,
            departure_anchor=base.departure_anchor,
            availability_windows=base.availability_windows,
            scenic_spots=base.scenic_spots,
            restaurants=base.restaurants,
            fixed_events=base.fixed_events,
            preferences=base.preferences,
            style_preferences=list(spec.style_preferences) or base.style_preferences,
            style_preference_sources=spec.style_preference_sources or base.style_preference_sources,
        )
        return normalize_parsed_trip_intent(reparsed)
    raise ValueError(f"Unsupported parser_mode: {spec.parser_mode}")


def inspect_request_sample_specs(
    specs: list[RequestSampleSpec],
) -> ParsedStyleAttributionInspectionReport:
    return inspect_parsed_style_attribution_parsed_samples(
        ((spec.label, parse_sample_spec(spec)) for spec in specs)
    )


def inspection_report_to_dict(
    report: ParsedStyleAttributionInspectionReport,
) -> dict[str, Any]:
    return {
        "total_samples": report.total_samples,
        "samples_with_styles": report.samples_with_styles,
        "aggregate_source_counts": dict(report.aggregate_source_counts),
        "aggregate_evidence_counts": dict(report.aggregate_evidence_counts),
        "rows": [
            {
                "label": row.label,
                "style_preferences": list(row.style_preferences),
                "style_preference_sources": dict(row.style_preference_sources),
                "debug_snapshot": list(row.debug_snapshot),
            }
            for row in report.rows
        ],
    }


def format_inspection_report_text(
    report: ParsedStyleAttributionInspectionReport,
) -> str:
    lines = [
        f"Total samples: {report.total_samples}",
        f"Samples with styles: {report.samples_with_styles}",
        "Aggregate source counts:",
        f"  explicit: {report.aggregate_source_counts['explicit']}",
        f"  inferred: {report.aggregate_source_counts['inferred']}",
        "Aggregate evidence counts:",
        f"  request_wording: {report.aggregate_evidence_counts['request_wording']}",
        f"  parser_explicit: {report.aggregate_evidence_counts['parser_explicit']}",
        f"  parser_inferred: {report.aggregate_evidence_counts['parser_inferred']}",
        f"  poi_mix: {report.aggregate_evidence_counts['poi_mix']}",
        "Samples:",
    ]
    for row in report.rows:
        snapshot = ", ".join(row.debug_snapshot) if row.debug_snapshot else "-"
        lines.append(f"- {row.label}: {snapshot}")
    return "\n".join(lines)


def resolve_sample_set_name(input_path: str | Path) -> str | None:
    resolved = Path(input_path).resolve()
    for name, path in SAMPLE_SET_PATHS.items():
        if resolved == path.resolve():
            return name
    return None


def summarize_strict_status(
    report: ParsedStyleAttributionInspectionReport,
) -> tuple[str, list[str]]:
    mismatches: list[str] = []
    if report.total_samples != STRICT_BASELINE["total_samples"]:
        mismatches.append(
            f"total={report.total_samples} (expected {STRICT_BASELINE['total_samples']})"
        )
    if report.samples_with_styles != STRICT_BASELINE["samples_with_styles"]:
        mismatches.append(
            "styled="
            f"{report.samples_with_styles} (expected {STRICT_BASELINE['samples_with_styles']})"
        )
    for source, expected in STRICT_BASELINE["aggregate_source_counts"].items():
        actual = report.aggregate_source_counts[source]
        if actual != expected:
            mismatches.append(f"{source}={actual} (expected {expected})")
    for evidence, expected in STRICT_BASELINE["aggregate_evidence_counts"].items():
        actual = report.aggregate_evidence_counts[evidence]
        if actual != expected:
            mismatches.append(f"{evidence}={actual} (expected {expected})")
    return ("PASS" if not mismatches else "FAIL", mismatches)


def format_inspection_summary_text(
    report: ParsedStyleAttributionInspectionReport,
    *,
    sample_set_name: str | None,
) -> str:
    lines: list[str] = []
    if sample_set_name:
        lines.append(f"Sample set: {sample_set_name}")
    if sample_set_name == "strict":
        status, mismatches = summarize_strict_status(report)
        lines.append(f"Strict status: {status}")
        if mismatches:
            lines.append("Differences: " + "; ".join(mismatches))
    elif sample_set_name:
        lines.append("Corpus status: OBSERVE")
    else:
        lines.append("Corpus status: CUSTOM")

    lines.append(f"Styled: {report.samples_with_styles}/{report.total_samples}")
    lines.append(
        "Sources: "
        f"explicit={report.aggregate_source_counts['explicit']} "
        f"inferred={report.aggregate_source_counts['inferred']}"
    )
    lines.append(
        "Evidence: "
        f"wording={report.aggregate_evidence_counts['request_wording']} "
        f"parser_explicit={report.aggregate_evidence_counts['parser_explicit']} "
        f"parser_inferred={report.aggregate_evidence_counts['parser_inferred']} "
        f"poi_mix={report.aggregate_evidence_counts['poi_mix']}"
    )
    return "\n".join(lines)


def format_all_sample_set_summaries_text(
    reports: dict[str, ParsedStyleAttributionInspectionReport],
) -> str:
    sections: list[str] = []
    for sample_set_name in ("strict", "realistic", "internal"):
        report = reports[sample_set_name]
        section_body = format_inspection_summary_text(
            report,
            sample_set_name=sample_set_name,
        ).splitlines()[1:]
        sections.append(
            "\n".join([f"[{sample_set_name.upper()}]", *section_body])
        )
    return "\n\n".join(sections)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Batch-inspect parsed style attribution provenance over request samples."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=None,
        help="Path to a JSONL file with {\"label\": ..., \"text\": ...} samples.",
    )
    parser.add_argument(
        "--sample-set",
        choices=SAMPLE_SET_CHOICES,
        default="strict",
        help=(
            "Named internal sample layer: strict for hard boundary regressions, "
            "realistic for lighter drift inspection, internal for long-lived corpus QA, "
            "all for a compact overview of all three. "
            "Ignored when an explicit input path is provided."
        ),
    )
    parser.add_argument(
        "--parser",
        choices=("fallback", "main"),
        default="fallback",
        help="Which parse path to use. Default keeps local inspection deterministic.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a compact QA summary instead of the full per-sample text report.",
    )
    args = parser.parse_args(argv)

    if args.input and args.sample_set == "all":
        parser.error("--sample-set all cannot be combined with an explicit input path.")

    if args.sample_set == "all" and args.summary:
        reports = {
            name: inspect_request_sample_specs(load_request_sample_specs(path))
            for name, path in SAMPLE_SET_PATHS.items()
        }
        print(format_all_sample_set_summaries_text(reports))
        return 0

    input_path = args.input or str(SAMPLE_SET_PATHS[args.sample_set])
    specs = load_request_sample_specs(input_path)
    if args.parser != "fallback":
        override_mode = args.parser
        specs = [
            RequestSampleSpec(
                label=spec.label,
                text=spec.text,
                parser_mode=override_mode if spec.parser_mode == "fallback" else spec.parser_mode,
                style_preferences=spec.style_preferences,
                style_preference_sources=spec.style_preference_sources,
            )
            for spec in specs
        ]
    report = inspect_request_sample_specs(specs)
    sample_set_name = resolve_sample_set_name(input_path)

    if args.format == "json":
        print(json.dumps(inspection_report_to_dict(report), ensure_ascii=False, indent=2))
    elif args.summary:
        print(format_inspection_summary_text(report, sample_set_name=sample_set_name))
    else:
        print(format_inspection_report_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

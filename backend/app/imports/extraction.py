from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Protocol

from app.imports.domain import (
    IMPORT_EXTRACTOR_VERSION,
    ExtractedMentionDraft,
    MentionEntityType,
    TextExtractionResult,
)
from app.services.itinerary_completion_recommendation import CITY_CANDIDATES, normalize_city_name
from app.services.nl_parser import COMMON_CITY_NAMES, split_items


class TextImportExtractor(Protocol):
    def extract(self, *, text: str, trip_context: dict) -> TextExtractionResult:
        ...


class DeterministicTextImportExtractor:
    def extract(self, *, text: str, trip_context: dict) -> TextExtractionResult:
        drafts: list[ExtractedMentionDraft] = []
        warnings: list[str] = []
        city_hint = normalize_city_name(str(trip_context.get("city") or "")) or find_city_hint(text)

        drafts.extend(extract_labeled_place_items(text, city_hint=city_hint))
        drafts.extend(extract_known_catalog_places(text, city_hint=city_hint))
        drafts.extend(extract_fixed_events(text, city_hint=city_hint))
        drafts.extend(extract_time_constraints(text, city_hint=city_hint))
        injection_notes = extract_instruction_like_notes(text)
        if injection_notes:
            warnings.append("instruction_like_content")
            drafts.extend(injection_notes)

        deduped = deduplicate_exact_mentions(sorted(drafts, key=lambda item: (item.start_offset, item.end_offset, item.entity_type.value)))
        if len(deduped) != len(drafts):
            warnings.append("duplicate_span_suppressed")

        return TextExtractionResult(
            mentions=deduped,
            warning_codes=warnings,
            extractor_version=IMPORT_EXTRACTOR_VERSION,
            processing_summary={
                "mention_count": len(deduped),
                "entity_counts": entity_counts(deduped),
            },
        )


def find_city_hint(text: str) -> str | None:
    for city in sorted(COMMON_CITY_NAMES, key=len, reverse=True):
        if city in text:
            return city
    return None


def extract_labeled_place_items(text: str, *, city_hint: str | None) -> list[ExtractedMentionDraft]:
    drafts: list[ExtractedMentionDraft] = []
    for match in re.finditer(r"(?P<label>景点|想去|餐厅|美食|吃饭|地点|POI|places?)\s*[:：]\s*(?P<body>[^\n。；;]+)", text, flags=re.I):
        label = match.group("label")
        body = match.group("body")
        body_start = match.start("body")
        for item in split_items(body):
            item_index = body.find(item)
            if item_index < 0:
                continue
            start = body_start + item_index
            drafts.append(
                mention_draft(
                    entity_type=MentionEntityType.PLACE,
                    raw_text=item,
                    start=start,
                    end=start + len(item),
                    city_hint=city_hint,
                    reason=f"explicit_{label}_list",
                    confidence=0.82,
                )
            )
    return drafts


def extract_known_catalog_places(text: str, *, city_hint: str | None) -> list[ExtractedMentionDraft]:
    names: set[str] = set()
    cities = [city_hint] if city_hint else list(CITY_CANDIDATES)
    for city in cities:
        if not city:
            continue
        for candidate in CITY_CANDIDATES.get(normalize_city_name(city) or "", []):
            names.add(candidate.name)
    for fallback in ("Starbucks Reserve Roastery", "Blue Bottle Coffee", "Disneytown"):
        names.add(fallback)

    drafts: list[ExtractedMentionDraft] = []
    for name in sorted(names, key=len, reverse=True):
        if len(name.strip()) < 2:
            continue
        for match in re.finditer(re.escape(name), text, flags=re.I):
            drafts.append(
                mention_draft(
                    entity_type=MentionEntityType.PLACE,
                    raw_text=text[match.start():match.end()],
                    start=match.start(),
                    end=match.end(),
                    city_hint=city_hint,
                    reason="known_local_candidate_catalog",
                    confidence=0.9,
                )
            )
    return drafts


def extract_fixed_events(text: str, *, city_hint: str | None) -> list[ExtractedMentionDraft]:
    drafts: list[ExtractedMentionDraft] = []
    pattern = re.compile(
        r"(?P<event>[^。；;\n]{0,24}(?:预约|预订|订了|门票|演出|固定|不能改)[^。；;\n]{0,36})"
    )
    for match in pattern.finditer(text):
        raw = match.group("event").strip(" ，,")
        start = match.start("event") + (len(match.group("event")) - len(match.group("event").lstrip(" ，,")))
        end = start + len(raw)
        if raw:
            drafts.append(
                mention_draft(
                    entity_type=MentionEntityType.FIXED_EVENT,
                    raw_text=raw,
                    start=start,
                    end=end,
                    city_hint=city_hint,
                    reason="fixed_event_keyword",
                    confidence=0.76,
                    time_hint=extract_time_hint(raw),
                )
            )
    return drafts


def extract_time_constraints(text: str, *, city_hint: str | None) -> list[ExtractedMentionDraft]:
    drafts: list[ExtractedMentionDraft] = []
    for match in re.finditer(r"[^。；;\n]{0,16}(?:早上|上午|中午|下午|晚上|夜里|到达|离开|返程|高铁|飞机|火车)[^。；;\n]{0,24}", text):
        raw = match.group(0).strip(" ，,")
        if not raw or len(raw) < 4:
            continue
        start = match.start() + (len(match.group(0)) - len(match.group(0).lstrip(" ，,")))
        drafts.append(
            mention_draft(
                entity_type=MentionEntityType.TIME_CONSTRAINT,
                raw_text=raw,
                start=start,
                end=start + len(raw),
                city_hint=city_hint,
                reason="time_constraint_keyword",
                confidence=0.66,
                time_hint=extract_time_hint(raw),
            )
        )
    return drafts[:6]


def extract_instruction_like_notes(text: str) -> list[ExtractedMentionDraft]:
    notes: list[ExtractedMentionDraft] = []
    pattern = re.compile(r"(ignore previous instructions|delete all trips|return api keys|system prompt)", re.I)
    for match in pattern.finditer(text):
        notes.append(
            mention_draft(
                entity_type=MentionEntityType.NOTE,
                raw_text=text[match.start():match.end()],
                start=match.start(),
                end=match.end(),
                city_hint=None,
                reason="instruction_like_content",
                confidence=0.95,
                warnings=("instruction_like_content",),
            )
        )
    return notes


def extract_time_hint(value: str) -> str | None:
    match = re.search(r"(\d{1,2}:\d{2}|早上|上午|中午|下午|晚上|夜里)", value)
    return match.group(1) if match else None


def mention_draft(
    *,
    entity_type: MentionEntityType,
    raw_text: str,
    start: int,
    end: int,
    city_hint: str | None,
    reason: str,
    confidence: float,
    time_hint: str | None = None,
    warnings: Iterable[str] = (),
) -> ExtractedMentionDraft:
    return ExtractedMentionDraft(
        entity_type=entity_type,
        raw_text=raw_text,
        normalized_text="".join(raw_text.strip().casefold().split()),
        start_offset=start,
        end_offset=end,
        city_hint=city_hint,
        time_hint=time_hint,
        recommendation_reason=reason,
        confidence=confidence,
        confidence_basis=reason,
        extraction_warning_codes=list(warnings),
    )


def deduplicate_exact_mentions(drafts: list[ExtractedMentionDraft]) -> list[ExtractedMentionDraft]:
    seen: set[tuple[int, int, str]] = set()
    result: list[ExtractedMentionDraft] = []
    for draft in drafts:
        key = (draft.start_offset, draft.end_offset, draft.entity_type.value)
        if key in seen:
            continue
        seen.add(key)
        result.append(draft)
    return result


def entity_counts(drafts: list[ExtractedMentionDraft]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for draft in drafts:
        counts[draft.entity_type.value] = counts.get(draft.entity_type.value, 0) + 1
    return counts

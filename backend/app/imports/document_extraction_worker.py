from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from hashlib import sha256

from PIL import Image
from pypdf import PdfReader
from pypdf.errors import PdfReadError


DOCUMENT_EXTRACTION_SCHEMA_VERSION = "1.0"
DOCUMENT_EXTRACTOR_VERSION = "document-extractor-v1"


@dataclass(frozen=True, slots=True)
class TextUnit:
    text: str
    page_number: int
    block_index: int
    line_index: int
    token_index: int | None
    page_width: float
    page_height: float
    bbox: dict[str, float]
    source_kind: str
    confidence: float | None
    warning_codes: list[str]


@dataclass(frozen=True, slots=True)
class PageExtraction:
    page_number: int
    extraction_method: str
    status: str
    native_text_quality: float | None
    text_chars: int
    span_count: int
    rendered_page_ref: str | None
    preview_page_ref: str | None
    retryable: bool
    error_code: str | None
    warning_codes: list[str]
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RenderedPage:
    ref: str
    page_number: int
    mime_type: str
    byte_size: int
    width: int
    height: int
    content_checksum: str


@dataclass(slots=True)
class RenderBudget:
    max_total_pixels: int
    used_pixels: int = 0
    rejected_pages: int = 0

    def reserve(self, pixels: int) -> bool:
        if pixels <= 0:
            self.rejected_pages += 1
            return False
        if self.used_pixels + pixels > self.max_total_pixels:
            self.rejected_pages += 1
            return False
        self.used_pixels += pixels
        return True

    def to_metadata(self) -> dict[str, int]:
        return {
            "max_total_pixels": self.max_total_pixels,
            "used_pixels": self.used_pixels,
            "rejected_pages": self.rejected_pages,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True)
    parser.add_argument("--kind", required=True, choices=["image", "pdf"])
    parser.add_argument("--mime-type", required=True)
    parser.add_argument("--limits-json", required=True)
    args = parser.parse_args()
    limits = json.loads(args.limits_json)
    try:
        if args.kind == "pdf":
            payload = extract_pdf(path=Path(args.path), limits=limits)
        else:
            payload = extract_image(path=Path(args.path), limits=limits)
    except Exception as exc:
        payload = {
            "schema_version": DOCUMENT_EXTRACTION_SCHEMA_VERSION,
            "extractor_version": DOCUMENT_EXTRACTOR_VERSION,
            "strategy": "image_ocr" if args.kind == "image" else "pdf_native_text",
            "status": "failed",
            "error_code": "import_document_extraction_worker_failed",
            "normalized_text": "",
            "page_count": 0,
            "spans": [],
            "warning_codes": [],
            "metadata": {"failure": exc.__class__.__name__},
        }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


def extract_pdf(*, path: Path, limits: dict[str, Any]) -> dict[str, Any]:
    try:
        reader = PdfReader(str(path), strict=False)
    except PdfReadError:
        return failed("pdf_native_text", "import_pdf_malformed", {"page_failures": [{"page_number": 0, "error_code": "import_pdf_malformed"}]})
    if reader.is_encrypted:
        return failed("pdf_native_text", "import_pdf_encrypted", {"page_failures": [{"page_number": 0, "error_code": "import_pdf_encrypted"}]})
    page_count = len(reader.pages)
    max_pages = int(limits.get("max_pdf_pages", 80))
    if page_count > max_pages:
        return failed("pdf_native_text", "import_pdf_page_limit_exceeded", {"page_count": page_count})

    units: list[TextUnit] = []
    pages: list[PageExtraction] = []
    rendered_pages: list[RenderedPage] = []
    page_failures: list[dict[str, Any]] = []
    ocr_pages = 0
    native_text_pages = 0
    retry_page_number = int(limits.get("retry_page_number") or 0)
    render_budget = RenderBudget(
        max_total_pixels=int(limits.get("pdf_render_max_total_pixels", 12_000_000)),
    )
    for page_index, page in enumerate(reader.pages):
        page_number = page_index + 1
        if retry_page_number and page_number != retry_page_number:
            continue
        rendered_ref: str | None = None
        preview_ref: str | None = None
        try:
            native_units = native_pdfium_units(path=path, page_index=page_index)
            native_bbox_source = "pdfium_charbox"
            if native_text_is_suspicious(native_units):
                raise ValueError("native_pdf_text_mojibake")
        except Exception as exc:
            try:
                native_units = native_pdf_units(page=page, page_number=page_number)
                native_bbox_source = "pypdf_estimated"
            except Exception:
                page_failures.append({"page_number": page_number, "error_code": "import_pdf_native_text_failed", "failure": exc.__class__.__name__})
                native_units = []
                native_bbox_source = "none"
        native_quality, native_quality_components = assess_native_text_quality(native_units)
        if should_render_pdf_previews(limits):
            rendered_preview = render_pdf_page(path=path, page_index=page_index, limits=limits, purpose="preview", budget=render_budget)
            if rendered_preview is not None:
                rendered_pages.append(rendered_preview)
                preview_ref = rendered_preview.ref
        if native_units and native_quality >= float(limits.get("pdf_native_min_quality", 0.35)):
            units.extend(native_units)
            native_text_pages += 1
            pages.append(
                PageExtraction(
                    page_number=page_number,
                    extraction_method="native_pdf_text",
                    status="extracted",
                    native_text_quality=native_quality,
                    text_chars=sum(len(unit.text) for unit in native_units),
                    span_count=len(native_units),
                    rendered_page_ref=None,
                    preview_page_ref=preview_ref,
                    retryable=False,
                    error_code=None,
                    warning_codes=[],
                    metadata={
                        "unit_count": len(native_units),
                        "image_width": float(page.mediabox.width),
                        "image_height": float(page.mediabox.height),
                        "native_text_quality_components": native_quality_components,
                        "native_bbox_source": native_bbox_source,
                    },
                )
            )
            continue
        if native_units:
            page_failures.append({"page_number": page_number, "error_code": "import_pdf_native_text_low_quality"})
        if bool(limits.get("enable_pdf_page_ocr", False)):
            rendered = render_pdf_page(path=path, page_index=page_index, limits=limits, purpose="ocr", budget=render_budget)
            if rendered is None:
                page_failures.append({"page_number": page_number, "error_code": "import_pdf_render_unavailable"})
                pages.append(
                    PageExtraction(
                        page_number=page_number,
                        extraction_method="none",
                        status="failed",
                        native_text_quality=native_quality,
                        text_chars=0,
                        span_count=0,
                        rendered_page_ref=None,
                        preview_page_ref=preview_ref,
                        retryable=True,
                        error_code="import_pdf_render_unavailable",
                        warning_codes=["pdf_page_render_failed"],
                        metadata={
                            "native_unit_count": len(native_units),
                            "image_width": float(page.mediabox.width),
                            "image_height": float(page.mediabox.height),
                            "native_text_quality_components": native_quality_components,
                            "native_bbox_source": native_bbox_source,
                        },
                    )
                )
                continue
            try:
                rendered_pages.append(rendered)
                rendered_ref = rendered.ref
                page_ocr = ocr_image(path=Path(rendered.ref), page_number=page_number, limits=limits, source_kind="ocr_token")
            except Exception:
                page_ocr = []
            if page_ocr:
                ocr_pages += 1
                units.extend(page_ocr)
                pages.append(
                    PageExtraction(
                        page_number=page_number,
                        extraction_method="pdf_page_ocr",
                        status="extracted",
                        native_text_quality=native_quality,
                        text_chars=sum(len(unit.text) for unit in page_ocr),
                        span_count=len(page_ocr),
                        rendered_page_ref=rendered_ref,
                        preview_page_ref=preview_ref or rendered_ref,
                        retryable=False,
                        error_code=None,
                        warning_codes=["pdf_native_text_low_quality"] if native_units else [],
                        metadata={
                            "native_unit_count": len(native_units),
                            "ocr_unit_count": len(page_ocr),
                            "image_width": float(page.mediabox.width),
                            "image_height": float(page.mediabox.height),
                            "native_text_quality_components": native_quality_components,
                            "native_bbox_source": native_bbox_source,
                        },
                    )
                )
            else:
                page_failures.append({"page_number": page_number, "error_code": "import_document_ocr_unavailable"})
                pages.append(
                    PageExtraction(
                        page_number=page_number,
                        extraction_method="pdf_page_ocr",
                        status="failed",
                        native_text_quality=native_quality,
                        text_chars=0,
                        span_count=0,
                        rendered_page_ref=rendered_ref,
                        preview_page_ref=preview_ref or rendered_ref,
                        retryable=True,
                        error_code="import_document_ocr_unavailable",
                        warning_codes=["document_ocr_unavailable"],
                        metadata={
                            "native_unit_count": len(native_units),
                            "image_width": float(page.mediabox.width),
                            "image_height": float(page.mediabox.height),
                            "native_text_quality_components": native_quality_components,
                            "native_bbox_source": native_bbox_source,
                        },
                    )
                )
        else:
            page_failures.append({"page_number": page_number, "error_code": "import_pdf_page_has_no_native_text"})
            pages.append(
                PageExtraction(
                    page_number=page_number,
                    extraction_method="none",
                    status="failed",
                    native_text_quality=native_quality,
                    text_chars=0,
                    span_count=0,
                    rendered_page_ref=None,
                    preview_page_ref=preview_ref,
                    retryable=True,
                    error_code="import_pdf_page_has_no_native_text",
                    warning_codes=["pdf_page_no_text"],
                    metadata={
                        "native_unit_count": len(native_units),
                        "image_width": float(page.mediabox.width),
                        "image_height": float(page.mediabox.height),
                        "native_text_quality_components": native_quality_components,
                        "native_bbox_source": native_bbox_source,
                    },
                )
            )

    return build_result(
        strategy="pdf_native_plus_selective_ocr" if ocr_pages else "pdf_native_text",
        units=units,
        page_count=page_count,
        metadata={
            "native_text_pages": native_text_pages,
            "ocr_pages": ocr_pages,
            "page_failures": page_failures,
            "ocr_capabilities": ocr_capabilities(limits),
            "native_quality_threshold": float(limits.get("pdf_native_min_quality", 0.35)),
            "reading_order_algorithm": "layout-reading-order-v2",
            "render_budget": render_budget.to_metadata(),
            "retry_page_number": retry_page_number or None,
        },
        warning_codes=["partial_page_extraction_failed"] if page_failures and units else [],
        error_code="import_document_extraction_no_text" if not units else None,
        pages=pages,
        rendered_pages=rendered_pages,
    )


def native_pdf_units(*, page, page_number: int) -> list[TextUnit]:
    page_height = float(page.mediabox.height)
    raw_units: list[TextUnit] = []

    def visitor(text: str, _cm, tm, _font_dict, font_size) -> None:
        cleaned = normalize_unit_text(text)
        if not cleaned:
            return
        x = float(tm[4])
        y = float(tm[5])
        estimated_width = max(float(font_size) * max(1, len(cleaned)) * 0.5, 1.0)
        char_width = estimated_width / max(1, len(cleaned))
        height = max(float(font_size), 1.0)
        for token_index, (segment, start_index, end_index) in enumerate(native_text_segments(cleaned)):
            segment_x = x + (char_width * start_index)
            segment_width = max(char_width * max(1, end_index - start_index), 1.0)
            raw_units.append(
                TextUnit(
                    text=segment,
                    page_number=page_number,
                    block_index=0,
                    line_index=0,
                    token_index=token_index,
                    page_width=float(page.mediabox.width),
                    page_height=page_height,
                    bbox=normalize_bbox(
                        segment_x,
                        max(0.0, page_height - y - height),
                        segment_width,
                        height,
                        float(page.mediabox.width),
                        page_height,
                    ),
                    source_kind="native_pdf_text",
                    confidence=None,
                    warning_codes=["native_pdf_bbox_estimated"],
                )
            )

    page.extract_text(visitor_text=visitor)
    ordered = sorted(raw_units, key=lambda unit: (unit.page_number, unit.bbox["y"], unit.bbox["x"], unit.text))
    return [
        TextUnit(
            text=unit.text,
            page_number=unit.page_number,
            block_index=index,
            line_index=index,
            token_index=unit.token_index,
            page_width=unit.page_width,
            page_height=unit.page_height,
            bbox=unit.bbox,
            source_kind=unit.source_kind,
            confidence=unit.confidence,
            warning_codes=unit.warning_codes,
        )
        for index, unit in enumerate(ordered)
    ]


def native_pdfium_units(*, path: Path, page_index: int) -> list[TextUnit]:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(str(path))
    try:
        page = document[page_index]
        page_number = page_index + 1
        page_width = float(page.get_width())
        page_height = float(page.get_height())
        textpage = page.get_textpage()
        try:
            chars = textpage.count_chars()
            raw_text = textpage.get_text_range(0, chars)
            segments = text_segments_with_boxes(
                raw_text=raw_text,
                char_boxes=[textpage.get_charbox(index) for index in range(chars)],
                page_number=page_number,
                page_width=page_width,
                page_height=page_height,
            )
            return layout_units_from_segments(segments)
        finally:
            textpage.close()
    finally:
        document.close()


def text_segments_with_boxes(
    *,
    raw_text: str,
    char_boxes: list[tuple[float, float, float, float]],
    page_number: int,
    page_width: float,
    page_height: float,
) -> list[TextUnit]:
    segments: list[TextUnit] = []
    current_text: list[str] = []
    current_boxes: list[tuple[float, float, float, float]] = []
    for char, char_box in zip(raw_text, char_boxes, strict=False):
        if char.isspace() or char in "，,、:：;；。.!?！？()（）[]【】":
            if current_text:
                segments.append(pdfium_segment_unit(current_text, current_boxes, page_number, page_width, page_height))
                current_text = []
                current_boxes = []
            continue
        current_text.append(char)
        current_boxes.append(char_box)
    if current_text:
        segments.append(pdfium_segment_unit(current_text, current_boxes, page_number, page_width, page_height))
    return segments


def pdfium_segment_unit(
    text_parts: list[str],
    boxes: list[tuple[float, float, float, float]],
    page_number: int,
    page_width: float,
    page_height: float,
) -> TextUnit:
    left = min(box[0] for box in boxes)
    bottom = min(box[1] for box in boxes)
    right = max(box[2] for box in boxes)
    top = max(box[3] for box in boxes)
    return TextUnit(
        text="".join(text_parts),
        page_number=page_number,
        block_index=0,
        line_index=0,
        token_index=0,
        page_width=page_width,
        page_height=page_height,
        bbox=normalize_bbox(
            left,
            max(0.0, page_height - top),
            max(1.0, right - left),
            max(1.0, top - bottom),
            page_width,
            page_height,
        ),
        source_kind="native_pdf_text",
        confidence=None,
        warning_codes=[],
    )


def layout_units_from_segments(segments: list[TextUnit]) -> list[TextUnit]:
    if not segments:
        return []
    ordered = sorted(segments, key=lambda unit: (unit.page_number, unit.bbox["y"], unit.bbox["x"], unit.text))
    line_threshold = 0.018
    paragraph_threshold = 0.06
    lines: list[list[TextUnit]] = []
    for unit in ordered:
        if not lines:
            lines.append([unit])
            continue
        previous_line = lines[-1]
        previous_y = sum(float(item.bbox["y"]) for item in previous_line) / max(1, len(previous_line))
        if abs(float(unit.bbox["y"]) - previous_y) <= line_threshold:
            previous_line.append(unit)
        else:
            lines.append([unit])
    laid_out: list[TextUnit] = []
    block_index = 0
    previous_line_y: float | None = None
    for line_index, line in enumerate(lines):
        line.sort(key=lambda unit: float(unit.bbox["x"]))
        line_y = sum(float(item.bbox["y"]) for item in line) / max(1, len(line))
        if previous_line_y is not None and abs(line_y - previous_line_y) > paragraph_threshold:
            block_index += 1
        for token_index, unit in enumerate(line):
            laid_out.append(
                TextUnit(
                    text=unit.text,
                    page_number=unit.page_number,
                    block_index=block_index,
                    line_index=line_index,
                    token_index=token_index,
                    page_width=unit.page_width,
                    page_height=unit.page_height,
                    bbox=unit.bbox,
                    source_kind=unit.source_kind,
                    confidence=unit.confidence,
                    warning_codes=unit.warning_codes,
                )
            )
        previous_line_y = line_y
    return laid_out


def native_text_is_suspicious(units: list[TextUnit]) -> bool:
    text = "".join(unit.text for unit in units)
    if not text:
        return False
    suspicious_chars = sum(1 for char in text if char in "ÃÂâ€æçï…Łåªä‚µØƒ�")
    cjk_chars = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    return cjk_chars == 0 and suspicious_chars / max(1, len(text)) > 0.18


def native_text_segments(text: str) -> list[tuple[str, int, int]]:
    segments: list[tuple[str, int, int]] = []
    start: int | None = None
    for index, char in enumerate(text):
        if char.isspace() or char in "，,、:：;；。.!?！？()（）[]【】":
            if start is not None:
                segments.append((text[start:index], start, index))
                start = None
            continue
        if start is None:
            start = index
    if start is not None:
        segments.append((text[start:], start, len(text)))
    return segments or [(text, 0, len(text))]


def extract_image(*, path: Path, limits: dict[str, Any]) -> dict[str, Any]:
    try:
        with Image.open(path) as image:
            image.load()
            width, height = image.size
    except Exception:
        return failed("image_ocr", "import_image_decode_failed", {"page_failures": [{"page_number": 1, "error_code": "import_image_decode_failed"}]})
    units = ocr_image(path=path, page_number=1, limits=limits, source_kind="ocr_token", page_width=width, page_height=height)
    page = PageExtraction(
        page_number=1,
        extraction_method="image_ocr",
        status="extracted" if units else "failed",
        native_text_quality=None,
        text_chars=sum(len(unit.text) for unit in units),
        span_count=len(units),
        rendered_page_ref=None,
        preview_page_ref="sanitized-image",
        retryable=not bool(units),
        error_code=None if units else "import_document_ocr_unavailable",
        warning_codes=[] if units else ["document_ocr_unavailable"],
        metadata={"image_width": width, "image_height": height},
    )
    return build_result(
        strategy="image_ocr",
        units=units,
        page_count=1,
        metadata={
            "image_width": width,
            "image_height": height,
            "ocr_capabilities": ocr_capabilities(limits),
            "page_failures": [] if units else [{"page_number": 1, "error_code": "import_document_ocr_unavailable"}],
        },
        warning_codes=[],
        error_code="import_document_ocr_unavailable" if not units else None,
        pages=[page],
        rendered_pages=[],
    )


def ocr_image(
    *,
    path: Path,
    page_number: int,
    limits: dict[str, Any],
    source_kind: str,
    page_width: float | None = None,
    page_height: float | None = None,
) -> list[TextUnit]:
    command = str(limits.get("ocr_command") or "tesseract")
    executable = shutil.which(command)
    if not executable:
        return []
    languages = str(limits.get("ocr_languages") or "eng")
    timeout = float(limits.get("ocr_timeout_seconds", 8.0))
    units = run_tesseract_units(
        executable=executable,
        path=path,
        languages=languages,
        timeout=timeout,
        page_number=page_number,
        source_kind=source_kind,
        page_width=page_width,
        page_height=page_height,
    )
    requested_languages = language_sequence(languages)
    if len(requested_languages) > 1:
        for language in requested_languages:
            units = merge_ocr_units(
                units,
                run_tesseract_units(
                    executable=executable,
                    path=path,
                    languages=language,
                    timeout=timeout,
                    page_number=page_number,
                    source_kind=source_kind,
                    page_width=page_width,
                    page_height=page_height,
                ),
            )
    return sorted(units, key=lambda unit: (unit.page_number, unit.block_index, unit.line_index, unit.token_index or 0, unit.bbox["x"], unit.text))


def run_tesseract_units(
    *,
    executable: str,
    path: Path,
    languages: str,
    timeout: float,
    page_number: int,
    source_kind: str,
    page_width: float | None,
    page_height: float | None,
) -> list[TextUnit]:
    process = subprocess.run(
        [executable, str(path), "stdout", "-l", languages, "--psm", "6", "tsv"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if process.returncode != 0:
        return []
    if page_width is None or page_height is None:
        try:
            with Image.open(path) as image:
                width, height = image.size
        except Exception:
            width, height = 1.0, 1.0
    else:
        width = float(page_width)
        height = float(page_height)
    return tsv_units(process.stdout.decode("utf-8", errors="replace"), page_number=page_number, source_kind=source_kind, page_width=width, page_height=height)


def language_sequence(languages: str) -> list[str]:
    return [item for item in languages.replace(",", "+").split("+") if item]


def merge_ocr_units(existing: list[TextUnit], additional: list[TextUnit]) -> list[TextUnit]:
    merged = list(existing)
    for unit in additional:
        if is_duplicate_ocr_unit(unit, merged):
            continue
        if contains_cjk(unit.text) or not overlaps_existing_text(unit, merged):
            merged.append(unit)
    return merged


def is_duplicate_ocr_unit(unit: TextUnit, existing: list[TextUnit]) -> bool:
    normalized = unit.text.casefold()
    return any(other.text.casefold() == normalized and bbox_iou(other.bbox, unit.bbox) >= 0.75 for other in existing)


def overlaps_existing_text(unit: TextUnit, existing: list[TextUnit]) -> bool:
    return any(bbox_iou(other.bbox, unit.bbox) >= 0.75 for other in existing)


def contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def bbox_iou(first: dict[str, float], second: dict[str, float]) -> float:
    left = max(float(first.get("x", 0.0)), float(second.get("x", 0.0)))
    top = max(float(first.get("y", 0.0)), float(second.get("y", 0.0)))
    right = min(
        float(first.get("x", 0.0)) + float(first.get("width", 0.0)),
        float(second.get("x", 0.0)) + float(second.get("width", 0.0)),
    )
    bottom = min(
        float(first.get("y", 0.0)) + float(first.get("height", 0.0)),
        float(second.get("y", 0.0)) + float(second.get("height", 0.0)),
    )
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    if intersection <= 0.0:
        return 0.0
    first_area = max(0.0, float(first.get("width", 0.0))) * max(0.0, float(first.get("height", 0.0)))
    second_area = max(0.0, float(second.get("width", 0.0))) * max(0.0, float(second.get("height", 0.0)))
    return intersection / max(1e-9, first_area + second_area - intersection)


def tsv_units(raw: str, *, page_number: int, source_kind: str, page_width: float, page_height: float) -> list[TextUnit]:
    units: list[TextUnit] = []
    reader = csv.DictReader(io.StringIO(raw), delimiter="\t")
    for row in reader:
        text = normalize_unit_text(row.get("text") or "")
        if not text:
            continue
        try:
            conf = float(row.get("conf") or "-1")
            left = float(row.get("left") or "0")
            top = float(row.get("top") or "0")
            width = float(row.get("width") or "0")
            height = float(row.get("height") or "0")
            block = max(0, int(row.get("block_num") or "1") - 1)
            line = max(0, int(row.get("line_num") or "1") - 1)
            token = max(0, int(row.get("word_num") or "1") - 1)
        except ValueError:
            continue
        if conf < 0:
            continue
        units.append(
            TextUnit(
                text=text,
                page_number=page_number,
                block_index=block,
                line_index=line,
                token_index=token,
                page_width=page_width,
                page_height=page_height,
                bbox=normalize_bbox(left, top, width, height, page_width, page_height),
                source_kind=source_kind,
                confidence=max(0.0, min(conf / 100.0, 1.0)),
                warning_codes=[],
            )
        )
    return sorted(units, key=lambda unit: (unit.page_number, unit.block_index, unit.line_index, unit.token_index or 0, unit.bbox["x"]))


def render_pdf_page(*, path: Path, page_index: int, limits: dict[str, Any], purpose: str, budget: RenderBudget) -> RenderedPage | None:
    try:
        import pypdfium2 as pdfium
    except Exception:
        return None
    scale = float(limits.get("pdf_render_scale", 2.0))
    max_pixels = int(limits.get("pdf_render_max_pixels", 4_000_000))
    max_bytes = int(limits.get("pdf_render_max_bytes", 2_000_000))
    document = pdfium.PdfDocument(str(path))
    try:
        page = document[page_index]
        projected_width = int(float(page.get_width()) * scale)
        projected_height = int(float(page.get_height()) * scale)
        projected_pixels = projected_width * projected_height
        if projected_pixels > max_pixels or not budget.reserve(projected_pixels):
            return None
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil()
        if image.width * image.height > max_pixels:
            return None
        tmp = Path(tempfile.gettempdir()) / f"pdf-page-{page_index}-{id(image)}.png"
        image.save(tmp, format="PNG")
        content = tmp.read_bytes()
        if len(content) > max_bytes:
            tmp.unlink(missing_ok=True)
            return None
        return RenderedPage(
            ref=str(tmp),
            page_number=page_index + 1,
            mime_type="image/png",
            byte_size=len(content),
            width=int(image.width),
            height=int(image.height),
            content_checksum=sha256(content).hexdigest(),
        )
    finally:
        document.close()


def build_result(
    *,
    strategy: str,
    units: list[TextUnit],
    page_count: int,
    metadata: dict[str, Any],
    warning_codes: list[str],
    error_code: str | None,
    pages: list[PageExtraction],
    rendered_pages: list[RenderedPage],
) -> dict[str, Any]:
    text, spans, layout_manifest, span_map = compose_text_and_spans(units)
    status = "failed" if not text.strip() else ("partial" if warning_codes or metadata.get("page_failures") else "review_ready")
    return {
        "schema_version": DOCUMENT_EXTRACTION_SCHEMA_VERSION,
        "extractor_version": DOCUMENT_EXTRACTOR_VERSION,
        "strategy": strategy,
        "status": status,
        "error_code": error_code if status == "failed" else None,
        "normalized_text": text,
        "page_count": page_count,
        "spans": spans,
        "warning_codes": unique(warning_codes + (["document_text_empty"] if status == "failed" else [])),
        "metadata": metadata,
        "layout_manifest": layout_manifest,
        "span_map": span_map,
        "pages": [page_to_payload(page) for page in pages],
        "rendered_pages": [rendered_page_to_payload(page) for page in rendered_pages],
    }


def assess_native_text_quality(units: list[TextUnit]) -> tuple[float, dict[str, float | int]]:
    if not units:
        return 0.0, {
            "text_chars": 0,
            "geometry_coverage": 0.0,
            "line_coherence": 0.0,
            "non_control_ratio": 0.0,
            "density_score": 0.0,
        }
    text_chars = sum(len(unit.text.strip()) for unit in units)
    boxes_with_area = sum(1 for unit in units if float(unit.bbox.get("width", 0)) > 0 and float(unit.bbox.get("height", 0)) > 0)
    unique_lines = len({(unit.page_number, unit.block_index, unit.line_index) for unit in units})
    non_control_chars = sum(1 for unit in units for char in unit.text if char.isprintable() and char != "\ufffd")
    total_chars = sum(len(unit.text) for unit in units)
    page_area = max(1.0, sum(unit.page_width * unit.page_height for unit in units) / max(1, len(units)))
    normalized_box_area = sum(float(unit.bbox.get("width", 0)) * float(unit.bbox.get("height", 0)) for unit in units)
    char_score = min(text_chars / 80.0, 1.0)
    geometry_score = boxes_with_area / max(1, len(units))
    line_coherence = max(0.0, min(1.0, len(units) / max(1, unique_lines) / 24.0))
    non_control_ratio = non_control_chars / max(1, total_chars)
    density_score = max(0.0, min(1.0, (normalized_box_area * page_area) / max(1.0, text_chars * 12.0)))
    score = round(
        (char_score * 0.28)
        + (geometry_score * 0.28)
        + (line_coherence * 0.16)
        + (non_control_ratio * 0.18)
        + (density_score * 0.10),
        4,
    )
    return score, {
        "text_chars": text_chars,
        "geometry_coverage": round(geometry_score, 4),
        "line_coherence": round(line_coherence, 4),
        "non_control_ratio": round(non_control_ratio, 4),
        "density_score": round(density_score, 4),
    }


def should_render_pdf_previews(limits: dict[str, Any]) -> bool:
    return bool(limits.get("persist_pdf_page_previews", True))


def page_to_payload(page: PageExtraction) -> dict[str, Any]:
    return {
        "page_number": page.page_number,
        "extraction_method": page.extraction_method,
        "status": page.status,
        "native_text_quality": page.native_text_quality,
        "text_chars": page.text_chars,
        "span_count": page.span_count,
        "rendered_page_ref": page.rendered_page_ref,
        "preview_page_ref": page.preview_page_ref,
        "retryable": page.retryable,
        "error_code": page.error_code,
        "warning_codes": page.warning_codes,
        "metadata": page.metadata,
    }


def rendered_page_to_payload(page: RenderedPage) -> dict[str, Any]:
    return {
        "ref": page.ref,
        "page_number": page.page_number,
        "mime_type": page.mime_type,
        "byte_size": page.byte_size,
        "width": page.width,
        "height": page.height,
        "content_checksum": page.content_checksum,
    }


def compose_text_and_spans(units: list[TextUnit]) -> tuple[str, list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    text_parts: list[str] = []
    spans: list[dict[str, Any]] = []
    span_map: list[dict[str, Any]] = []
    previous_key: tuple[int, int, int] | None = None
    ordered = sorted(
        units,
        key=lambda unit: (
            unit.page_number,
            round(float(unit.bbox.get("y", 0)), 4),
            round(float(unit.bbox.get("x", 0)), 4),
            unit.block_index,
            unit.line_index,
            unit.token_index or 0,
            unit.text,
        ),
    )
    pages: dict[int, dict[str, Any]] = {}
    blocks: dict[str, dict[str, Any]] = {}
    lines: dict[str, dict[str, Any]] = {}
    for reading_order, unit in enumerate(ordered):
        key = (unit.page_number, unit.block_index, unit.line_index)
        if text_parts:
            text_parts.append("\n" if key != previous_key else " ")
        start = sum(len(part) for part in text_parts)
        text_parts.append(unit.text)
        end = start + len(unit.text)
        block_id = stable_layout_id("block", unit.page_number, unit.block_index)
        line_id = stable_layout_id("line", unit.page_number, unit.block_index, unit.line_index)
        token_id = stable_layout_id("token", unit.page_number, unit.block_index, unit.line_index, unit.token_index or 0, unit.text, reading_order)
        spans.append(
            {
                "span_start": start,
                "span_end": end,
                "page_number": unit.page_number,
                "block_index": unit.block_index,
                "line_index": unit.line_index,
                "token_index": unit.token_index,
                "block_id": block_id,
                "line_id": line_id,
                "token_id": token_id,
                "reading_order": reading_order,
                "bbox": unit.bbox,
                "source_kind": unit.source_kind,
                "confidence": unit.confidence,
                "warning_codes": unit.warning_codes,
            }
        )
        span_map.append(
            {
                "start_offset": start,
                "end_offset": end,
                "page_number": unit.page_number,
                "block_ids": [block_id],
                "line_ids": [line_id],
                "token_ids": [token_id],
                "bounding_boxes": [unit.bbox],
                "extraction_method": unit.source_kind,
                "text_digest": sha256(unit.text.encode("utf-8")).hexdigest(),
            }
        )
        page = pages.setdefault(
            unit.page_number,
            {
                "id": stable_layout_id("page", unit.page_number),
                "page_number": unit.page_number,
                "width": unit.page_width,
                "height": unit.page_height,
                "rotation": 0,
                "bbox": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0, "origin": "top-left", "unit": "normalized"},
                "block_ids": [],
            },
        )
        block = blocks.setdefault(
            block_id,
            {
                "id": block_id,
                "page_number": unit.page_number,
                "taxonomy": classify_block(unit.text, unit.block_index),
                "reading_order": reading_order,
                "bbox": unit.bbox,
                "line_ids": [],
            },
        )
        line = lines.setdefault(
            line_id,
            {
                "id": line_id,
                "page_number": unit.page_number,
                "block_id": block_id,
                "reading_order": reading_order,
                "bbox": unit.bbox,
                "token_ids": [],
            },
        )
        token = {
            "id": token_id,
            "page_number": unit.page_number,
            "text": unit.text,
            "normalized_text": normalize_unit_text(unit.text),
            "bbox": unit.bbox,
            "confidence_raw": unit.confidence,
            "extraction_method": unit.source_kind,
            "reading_order": reading_order,
            "block_id": block_id,
            "line_id": line_id,
        }
        line["token_ids"].append(token_id)
        line.setdefault("tokens", []).append(token)
        if line_id not in block["line_ids"]:
            block["line_ids"].append(line_id)
        if block_id not in page["block_ids"]:
            page["block_ids"].append(block_id)
        previous_key = key
    for line in lines.values():
        line["bbox"] = union_bboxes([token["bbox"] for token in line.get("tokens", [])])
    for block in blocks.values():
        block["bbox"] = union_bboxes([lines[line_id]["bbox"] for line_id in block["line_ids"] if line_id in lines])
    layout_manifest = {
        "schema_version": DOCUMENT_EXTRACTION_SCHEMA_VERSION,
        "reading_order_algorithm": "layout-reading-order-v2",
        "coordinate_space": {"origin": "top-left", "unit": "normalized", "range": [0.0, 1.0]},
        "pages": [
            {
                **page,
                "blocks": [blocks[block_id] for block_id in page["block_ids"] if block_id in blocks],
            }
            for page in sorted(pages.values(), key=lambda item: item["page_number"])
        ],
    }
    return "".join(text_parts).strip(), spans, layout_manifest, span_map


def stable_layout_id(kind: str, *parts: object) -> str:
    digest = sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:16]
    return f"{kind}_{digest}"


def normalize_bbox(x: float, y: float, width: float, height: float, page_width: float, page_height: float) -> dict[str, float | str]:
    safe_width = max(page_width, 1.0)
    safe_height = max(page_height, 1.0)
    nx = clamp01(x / safe_width)
    ny = clamp01(y / safe_height)
    nw = clamp01(width / safe_width)
    nh = clamp01(height / safe_height)
    if nx + nw > 1.0:
        nw = max(0.0, 1.0 - nx)
    if ny + nh > 1.0:
        nh = max(0.0, 1.0 - ny)
    return {"x": round(nx, 6), "y": round(ny, 6), "width": round(nw, 6), "height": round(nh, 6), "origin": "top-left", "unit": "normalized"}


def clamp01(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def union_bboxes(boxes: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [box for box in boxes if all(key in box for key in ("x", "y", "width", "height"))]
    if not valid:
        return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0, "origin": "top-left", "unit": "normalized"}
    x0 = min(float(box["x"]) for box in valid)
    y0 = min(float(box["y"]) for box in valid)
    x1 = max(float(box["x"]) + float(box["width"]) for box in valid)
    y1 = max(float(box["y"]) + float(box["height"]) for box in valid)
    return normalize_bbox(x0, y0, x1 - x0, y1 - y0, 1.0, 1.0)


def classify_block(text: str, block_index: int) -> str:
    stripped = text.strip()
    if block_index == 0 and len(stripped) <= 48:
        return "heading"
    if stripped[:1] in {"-", "*", "•"} or stripped[:2].isdigit():
        return "list_item"
    return "paragraph" if stripped else "unknown"


def failed(strategy: str, error_code: str, metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": DOCUMENT_EXTRACTION_SCHEMA_VERSION,
        "extractor_version": DOCUMENT_EXTRACTOR_VERSION,
        "strategy": strategy,
        "status": "failed",
        "error_code": error_code,
        "normalized_text": "",
        "page_count": int(metadata.get("page_count") or 0),
        "spans": [],
        "warning_codes": ["document_text_empty"],
        "metadata": metadata,
    }


def normalize_unit_text(value: str) -> str:
    repaired = value
    try:
        candidate = value.encode("latin-1").decode("utf-8")
        if sum("\u4e00" <= char <= "\u9fff" for char in candidate) > sum("\u4e00" <= char <= "\u9fff" for char in value):
            repaired = candidate
    except UnicodeError:
        pass
    return " ".join(repaired.replace("\x00", "").replace("\r", "\n").split())


def ocr_capabilities(limits: dict[str, Any]) -> dict[str, Any]:
    command = str(limits.get("ocr_command") or "tesseract")
    executable = shutil.which(command)
    requested = [item for item in str(limits.get("ocr_languages") or "eng").replace(",", "+").split("+") if item]
    installed = installed_tesseract_languages(executable) if executable else []
    return {
        "engine": "tesseract",
        "available": executable is not None,
        "languages": "+".join(requested),
        "requested_languages": requested,
        "installed_languages": installed,
        "missing_languages": [language for language in requested if language not in installed],
        "silent_fallback": False,
    }


def installed_tesseract_languages(executable: str) -> list[str]:
    try:
        process = subprocess.run(
            [executable, "--list-langs"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=4,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if process.returncode != 0:
        return []
    lines = process.stdout.decode("utf-8", errors="replace").splitlines()
    return sorted(line.strip() for line in lines[1:] if line.strip())


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


if __name__ == "__main__":
    raise SystemExit(main())

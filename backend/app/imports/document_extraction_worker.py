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
    page_failures: list[dict[str, Any]] = []
    ocr_pages = 0
    for page_index, page in enumerate(reader.pages):
        page_number = page_index + 1
        try:
            native_units = native_pdf_units(page=page, page_number=page_number)
        except Exception as exc:
            page_failures.append({"page_number": page_number, "error_code": "import_pdf_native_text_failed", "failure": exc.__class__.__name__})
            native_units = []
        if native_units:
            units.extend(native_units)
            continue
        if bool(limits.get("enable_pdf_page_ocr", False)):
            rendered = render_pdf_page(path=path, page_index=page_index, limits=limits)
            if rendered is None:
                page_failures.append({"page_number": page_number, "error_code": "import_pdf_render_unavailable"})
                continue
            try:
                page_ocr = ocr_image(path=rendered, page_number=page_number, limits=limits, source_kind="ocr_token")
            finally:
                rendered.unlink(missing_ok=True)
            if page_ocr:
                ocr_pages += 1
                units.extend(page_ocr)
            else:
                page_failures.append({"page_number": page_number, "error_code": "import_document_ocr_unavailable"})
        else:
            page_failures.append({"page_number": page_number, "error_code": "import_pdf_page_has_no_native_text"})

    return build_result(
        strategy="pdf_native_plus_selective_ocr" if ocr_pages else "pdf_native_text",
        units=units,
        page_count=page_count,
        metadata={
            "native_text_pages": page_count - len([item for item in page_failures if item.get("error_code") == "import_pdf_page_has_no_native_text"]),
            "ocr_pages": ocr_pages,
            "page_failures": page_failures,
            "ocr_capabilities": ocr_capabilities(limits),
        },
        warning_codes=["partial_page_extraction_failed"] if page_failures and units else [],
        error_code="import_document_extraction_no_text" if not units else None,
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
        width = max(float(font_size) * max(1, len(cleaned)) * 0.5, 1.0)
        height = max(float(font_size), 1.0)
        raw_units.append(
            TextUnit(
                text=cleaned,
                page_number=page_number,
                block_index=0,
                line_index=0,
                token_index=None,
                page_width=float(page.mediabox.width),
                page_height=page_height,
                bbox=normalize_bbox(x, max(0.0, page_height - y - height), width, height, float(page.mediabox.width), page_height),
                source_kind="native_pdf_text",
                confidence=None,
                warning_codes=[],
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
            token_index=None,
            page_width=unit.page_width,
            page_height=unit.page_height,
            bbox=unit.bbox,
            source_kind=unit.source_kind,
            confidence=unit.confidence,
            warning_codes=unit.warning_codes,
        )
        for index, unit in enumerate(ordered)
    ]


def extract_image(*, path: Path, limits: dict[str, Any]) -> dict[str, Any]:
    try:
        with Image.open(path) as image:
            image.load()
            width, height = image.size
    except Exception:
        return failed("image_ocr", "import_image_decode_failed", {"page_failures": [{"page_number": 1, "error_code": "import_image_decode_failed"}]})
    units = ocr_image(path=path, page_number=1, limits=limits, source_kind="ocr_token", page_width=width, page_height=height)
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


def render_pdf_page(*, path: Path, page_index: int, limits: dict[str, Any]) -> Path | None:
    try:
        import pypdfium2 as pdfium
    except Exception:
        return None
    scale = float(limits.get("pdf_render_scale", 2.0))
    document = pdfium.PdfDocument(str(path))
    try:
        page = document[page_index]
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil()
        tmp = Path(tempfile.gettempdir()) / f"pdf-page-{page_index}-{id(image)}.png"
        image.save(tmp, format="PNG")
        return tmp
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
    }


def compose_text_and_spans(units: list[TextUnit]) -> tuple[str, list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    text_parts: list[str] = []
    spans: list[dict[str, Any]] = []
    span_map: list[dict[str, Any]] = []
    previous_key: tuple[int, int, int] | None = None
    ordered = sorted(units, key=lambda unit: (unit.page_number, unit.block_index, unit.line_index, unit.token_index or 0, unit.bbox.get("x", 0)))
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
        "reading_order_algorithm": "layout-reading-order-v1",
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

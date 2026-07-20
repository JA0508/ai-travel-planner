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
                bbox={"x0": x, "y0": max(0.0, page_height - y - height), "x1": x + width, "y1": max(0.0, page_height - y), "unit": "pt"},
                source_kind="native_pdf_text",
                confidence=None,
                warning_codes=[],
            )
        )

    page.extract_text(visitor_text=visitor)
    ordered = sorted(raw_units, key=lambda unit: (unit.page_number, unit.bbox["y0"], unit.bbox["x0"], unit.text))
    return [
        TextUnit(
            text=unit.text,
            page_number=unit.page_number,
            block_index=index,
            line_index=index,
            token_index=None,
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
    units = ocr_image(path=path, page_number=1, limits=limits, source_kind="ocr_token")
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


def ocr_image(*, path: Path, page_number: int, limits: dict[str, Any], source_kind: str) -> list[TextUnit]:
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
    return tsv_units(process.stdout.decode("utf-8", errors="replace"), page_number=page_number, source_kind=source_kind)


def tsv_units(raw: str, *, page_number: int, source_kind: str) -> list[TextUnit]:
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
                bbox={"x0": left, "y0": top, "x1": left + width, "y1": top + height, "unit": "px"},
                source_kind=source_kind,
                confidence=max(0.0, min(conf / 100.0, 1.0)),
                warning_codes=[],
            )
        )
    return sorted(units, key=lambda unit: (unit.page_number, unit.block_index, unit.line_index, unit.token_index or 0, unit.bbox["x0"]))


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
    text, spans = compose_text_and_spans(units)
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
    }


def compose_text_and_spans(units: list[TextUnit]) -> tuple[str, list[dict[str, Any]]]:
    text_parts: list[str] = []
    spans: list[dict[str, Any]] = []
    previous_key: tuple[int, int, int] | None = None
    ordered = sorted(units, key=lambda unit: (unit.page_number, unit.block_index, unit.line_index, unit.token_index or 0, unit.bbox.get("x0", 0)))
    for unit in ordered:
        key = (unit.page_number, unit.block_index, unit.line_index)
        if text_parts:
            text_parts.append("\n" if key != previous_key else " ")
        start = sum(len(part) for part in text_parts)
        text_parts.append(unit.text)
        end = start + len(unit.text)
        spans.append(
            {
                "span_start": start,
                "span_end": end,
                "page_number": unit.page_number,
                "block_index": unit.block_index,
                "line_index": unit.line_index,
                "token_index": unit.token_index,
                "bbox": unit.bbox,
                "source_kind": unit.source_kind,
                "confidence": unit.confidence,
                "warning_codes": unit.warning_codes,
            }
        )
        previous_key = key
    return "".join(text_parts).strip(), spans


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
    return {
        "engine": "tesseract",
        "available": shutil.which(command) is not None,
        "languages": str(limits.get("ocr_languages") or "eng"),
        "silent_fallback": False,
    }


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

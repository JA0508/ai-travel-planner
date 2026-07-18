from __future__ import annotations

import argparse
import hashlib
import json
import sys
import warnings
from pathlib import Path
from typing import Any

from PIL import Image, ImageFile, ImageOps, ImageSequence
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, NameObject


ARTIFACT_INSPECTION_SCHEMA_VERSION = "1.0"
ARTIFACT_INSPECTOR_VERSION = "binary-inspector-v1"

FINDING_SEVERITY = {"info", "warning", "block"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True)
    parser.add_argument("--declared-kind", required=True)
    parser.add_argument("--detected-mime", required=True)
    parser.add_argument("--sanitized-output")
    parser.add_argument("--limits-json", required=True)
    args = parser.parse_args()
    limits = json.loads(args.limits_json)
    try:
        if args.declared_kind == "image":
            result = inspect_image(
                path=Path(args.path),
                detected_mime=args.detected_mime,
                sanitized_output=Path(args.sanitized_output) if args.sanitized_output else None,
                limits=limits,
            )
        elif args.declared_kind == "pdf":
            result = inspect_pdf(path=Path(args.path), limits=limits)
        else:
            result = rejected_result("import_binary_type_unsupported", "BINARY_DECLARED_TYPE_MISMATCH")
    except Exception as exc:
        result = {
            "status": "inspection_failed",
            "classification": "inspection_failed",
            "error_code": "import_inspection_worker_failed",
            "metadata": {},
            "findings": [
                finding(
                    code="BINARY_MALFORMED",
                    severity="block",
                    category="worker",
                    evidence={"failure": exc.__class__.__name__},
                )
            ],
        }
    print(json.dumps(with_versions(result), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0


def inspect_image(
    *,
    path: Path,
    detected_mime: str,
    sanitized_output: Path | None,
    limits: dict[str, Any],
) -> dict[str, Any]:
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    Image.MAX_IMAGE_PIXELS = int(limits.get("max_image_pixels", 40_000_000))
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    findings: list[dict[str, Any]] = []
    try:
        with Image.open(path) as probe:
            probe.verify()
        with Image.open(path) as image:
            frame_count = count_frames(image)
            if frame_count != 1:
                return rejected_result("import_image_animation_unsupported", "IMAGE_ANIMATION_UNSUPPORTED")
            width, height = image.size
            pixel_count = width * height
            if pixel_count > int(limits.get("max_image_pixels", 40_000_000)):
                return rejected_result("import_image_pixel_limit_exceeded", "IMAGE_PIXEL_LIMIT_EXCEEDED")
            if width > int(limits.get("max_image_dimension", 12_000)) or height > int(limits.get("max_image_dimension", 12_000)):
                return rejected_result("import_image_dimension_limit_exceeded", "IMAGE_DIMENSION_LIMIT_EXCEEDED")
            if max(width, height) / max(1, min(width, height)) > float(limits.get("max_aspect_ratio", 20.0)):
                findings.append(finding("IMAGE_EXTREME_ASPECT_RATIO", "warning", "structure", {"dimension_class": "extreme_aspect_ratio"}))
            metadata = image_metadata_flags(image)
            if metadata["metadata_present"]:
                findings.append(finding("IMAGE_METADATA_PRESENT", "warning", "privacy", {"metadata": "stripped"}))
            image.load()
            normalized = ImageOps.exif_transpose(image)
            derivative_mime = "image/png" if normalized.mode in {"RGBA", "LA", "P"} and "transparency" in image.info else "image/jpeg"
            if sanitized_output is not None:
                sanitized_output.parent.mkdir(parents=True, exist_ok=True)
                if derivative_mime == "image/png":
                    normalized.save(sanitized_output, format="PNG", optimize=False)
                else:
                    normalized.convert("RGB").save(
                        sanitized_output,
                        format="JPEG",
                        quality=90,
                        optimize=False,
                        progressive=False,
                    )
            return {
                "status": "artifact_ready",
                "classification": "artifact_ready",
                "error_code": None,
                "metadata": {
                    "detected_format": detected_mime,
                    "width": width,
                    "height": height,
                    "pixel_count": pixel_count,
                    "frame_count": frame_count,
                    "metadata_present": metadata["metadata_present"],
                    "gps_metadata_present": metadata["gps_metadata_present"],
                    "orientation_present": metadata["orientation_present"],
                    "sanitized_derivative_mime_type": derivative_mime,
                },
                "findings": findings,
            }
    except Image.DecompressionBombWarning:
        return rejected_result("import_image_pixel_limit_exceeded", "IMAGE_PIXEL_LIMIT_EXCEEDED")
    except Exception:
        return rejected_result("import_image_decode_failed", "IMAGE_DECODE_FAILED")


def count_frames(image: Image.Image) -> int:
    count = 0
    for _frame in ImageSequence.Iterator(image):
        count += 1
        if count > 1:
            return count
    return max(count, 1)


def image_metadata_flags(image: Image.Image) -> dict[str, bool]:
    exif = image.getexif()
    gps_present = 34853 in exif
    orientation_present = 274 in exif
    info_keys = {str(key).casefold() for key in image.info}
    metadata_present = bool(exif) or bool(info_keys & {"icc_profile", "exif", "xmp", "comment", "description", "xml:com.adobe.xmp"})
    return {
        "metadata_present": metadata_present,
        "gps_metadata_present": gps_present,
        "orientation_present": orientation_present,
    }


def inspect_pdf(*, path: Path, limits: dict[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    try:
        reader = PdfReader(str(path), strict=False)
    except PdfReadError:
        return rejected_result("import_pdf_malformed", "PDF_MALFORMED")
    except Exception:
        return rejected_result("import_pdf_malformed", "PDF_MALFORMED")
    if reader.is_encrypted:
        return {
            "status": "needs_password",
            "classification": "needs_password",
            "error_code": "import_pdf_encrypted",
            "metadata": {
                "detected_format": "application/pdf",
                "encrypted": True,
                "page_count": 0,
            },
            "findings": [finding("PDF_ENCRYPTED", "block", "encryption", {"encrypted": True})],
        }
    try:
        page_count = len(reader.pages)
    except Exception:
        return rejected_result("import_pdf_malformed", "PDF_MALFORMED")
    if page_count > int(limits.get("max_pdf_pages", 80)):
        return rejected_result("import_pdf_page_limit_exceeded", "PDF_PAGE_LIMIT_EXCEEDED", {"page_count": page_count})

    try:
        object_count = pdf_object_count(reader)
    except Exception:
        object_count = None
    if object_count is not None and object_count > int(limits.get("max_pdf_objects", 5_000)):
        return rejected_result("import_pdf_structure_limit_exceeded", "PDF_OBJECT_LIMIT_EXCEEDED", {"object_count": object_count})

    flags = scan_pdf_flags(reader, max_nodes=int(limits.get("max_pdf_scan_nodes", 3_000)))
    if flags["javascript"]:
        findings.append(finding("PDF_JAVASCRIPT_PRESENT", "block", "active_content", {"present": True}))
    if flags["open_action"]:
        findings.append(finding("PDF_OPEN_ACTION_PRESENT", "block", "active_content", {"present": True}))
    if flags["additional_actions"]:
        findings.append(finding("PDF_ADDITIONAL_ACTIONS_PRESENT", "block", "active_content", {"present": True}))
    if flags["launch"]:
        findings.append(finding("PDF_LAUNCH_ACTION_PRESENT", "block", "active_content", {"present": True}))
    if flags["embedded_files"]:
        findings.append(finding("PDF_EMBEDDED_FILES_PRESENT", "block", "embedded_files", {"present": True}))
    if flags["rich_media"]:
        findings.append(finding("PDF_RICH_MEDIA_PRESENT", "block", "active_content", {"present": True}))
    if flags["xfa"]:
        findings.append(finding("PDF_XFA_PRESENT", "block", "active_content", {"present": True}))
    if flags["acroform"]:
        findings.append(finding("PDF_ACROFORM_PRESENT", "warning", "form", {"present": True}))
    if flags["external_uri"]:
        findings.append(finding("PDF_EXTERNAL_URI_PRESENT", "warning", "external_reference", {"present": True}))
    unusual_pages = unusual_page_count(reader)
    if unusual_pages:
        findings.append(finding("PDF_UNUSUAL_PAGE_DIMENSIONS", "warning", "structure", {"page_count": unusual_pages}))
    block = any(item["severity"] == "block" for item in findings)
    return {
        "status": "rejected" if block else "artifact_ready",
        "classification": "rejected" if block else "artifact_ready",
        "error_code": "import_pdf_active_content_detected" if block else None,
        "metadata": {
            "detected_format": "application/pdf",
            "encrypted": False,
            "page_count": page_count,
            "object_count": object_count,
            "acroform_present": flags["acroform"],
            "xfa_present": flags["xfa"],
            "external_uri_present": flags["external_uri"],
            "active_content_present": block,
            "embedded_files_present": flags["embedded_files"],
            "unusual_page_dimensions": unusual_pages > 0,
        },
        "findings": findings,
    }


def scan_pdf_flags(reader: PdfReader, *, max_nodes: int) -> dict[str, bool]:
    flags = {
        "javascript": False,
        "open_action": False,
        "additional_actions": False,
        "launch": False,
        "embedded_files": False,
        "rich_media": False,
        "xfa": False,
        "acroform": False,
        "external_uri": False,
    }
    root = reader.trailer.get("/Root", {})
    seen: set[int] = set()
    stack: list[Any] = [root]
    nodes = 0
    while stack and nodes < max_nodes:
        current = stack.pop()
        nodes += 1
        try:
            if isinstance(current, IndirectObject):
                ident = id(current)
                if ident in seen:
                    continue
                seen.add(ident)
                current = current.get_object()
            if isinstance(current, DictionaryObject):
                keys = {str(key) for key in current.keys()}
                flags["open_action"] = flags["open_action"] or "/OpenAction" in keys
                flags["additional_actions"] = flags["additional_actions"] or "/AA" in keys
                flags["javascript"] = flags["javascript"] or bool(keys & {"/JavaScript", "/JS", "/Names"})
                flags["launch"] = flags["launch"] or "/Launch" in keys or current.get("/S") == NameObject("/Launch")
                flags["embedded_files"] = flags["embedded_files"] or bool(keys & {"/EmbeddedFiles", "/Filespec", "/EF"})
                flags["rich_media"] = flags["rich_media"] or "/RichMedia" in keys
                flags["xfa"] = flags["xfa"] or "/XFA" in keys
                flags["acroform"] = flags["acroform"] or "/AcroForm" in keys
                flags["external_uri"] = flags["external_uri"] or current.get("/S") == NameObject("/URI") or "/URI" in keys
                stack.extend(current.values())
            elif isinstance(current, ArrayObject):
                stack.extend(current)
        except Exception:
            continue
    return flags


def unusual_page_count(reader: PdfReader) -> int:
    count = 0
    for page in reader.pages:
        try:
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
        except Exception:
            continue
        if width <= 0 or height <= 0 or width > 2400 or height > 2400 or max(width, height) / max(1.0, min(width, height)) > 8:
            count += 1
    return count


def pdf_object_count(reader: PdfReader) -> int | None:
    xref = getattr(reader, "xref", None)
    if not isinstance(xref, dict):
        return None
    return sum(len(section) for section in xref.values() if hasattr(section, "__len__"))


def rejected_result(error_code: str, finding_code: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": "rejected",
        "classification": "rejected",
        "error_code": error_code,
        "metadata": {},
        "findings": [finding(finding_code, "block", "structure", evidence or {"present": True})],
    }


def finding(code: str, severity: str, category: str, evidence: dict[str, Any]) -> dict[str, Any]:
    if severity not in FINDING_SEVERITY:
        severity = "warning"
    return {
        "code": code,
        "severity": severity,
        "category": category,
        "evidence": sanitize_evidence(evidence),
    }


def sanitize_evidence(value: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, raw in value.items():
        if isinstance(raw, (bool, int, float)):
            safe[key] = raw
        elif isinstance(raw, str):
            safe[key] = raw[:80]
    return safe


def with_versions(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": ARTIFACT_INSPECTION_SCHEMA_VERSION,
        "inspector_version": ARTIFACT_INSPECTOR_VERSION,
        **result,
    }


def file_checksum(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


if __name__ == "__main__":
    sys.exit(main())

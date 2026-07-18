from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from app.trips.errors import TripError


SUPPORTED_DECLARED_KINDS = {"image", "pdf"}
IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
PDF_MIME_TYPE = "application/pdf"


@dataclass(frozen=True, slots=True)
class BinaryDetection:
    declared_kind: str
    detected_kind: str
    detected_mime_type: str
    extension: str
    warning_codes: list[str]


def sanitize_original_label(value: str | None) -> str | None:
    if not value:
        return None
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.replace("\x00", "").replace("/", "_").replace("\\", "_")
    normalized = re.sub(r"[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]", "", normalized)
    normalized = normalized.strip().strip(". ")
    if not normalized:
        return None
    name = Path(normalized).name.strip().strip(". ")
    if not name:
        return None
    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    stem = name.split(".", 1)[0].upper()
    if stem in reserved:
        name = f"file-{name}"
    return name[:160]


def extension_from_label(value: str | None) -> str | None:
    label = sanitize_original_label(value)
    if not label or "." not in label:
        return None
    suffix = label.rsplit(".", 1)[-1].strip().casefold()
    return suffix or None


def detect_binary_file(
    *,
    path: Path,
    declared_kind: str,
    content_type: str | None,
    original_label: str | None,
) -> BinaryDetection:
    declared = declared_kind.strip().casefold()
    if declared not in SUPPORTED_DECLARED_KINDS:
        raise TripError("import_binary_type_unsupported", "Only image and PDF artifact uploads are supported.", 422)
    head, tail = read_bounds(path)
    if not head:
        raise TripError("import_binary_empty", "Uploaded artifact is empty.", 422)
    executable_code = detect_executable_signature(head)
    if executable_code:
        raise TripError("import_binary_signature_mismatch", "Uploaded artifact content is not a supported image or PDF.", 422)
    detected_mime, extension = detect_signature(head)
    if detected_mime is None:
        raise TripError("import_binary_type_unsupported", "Uploaded artifact type is not supported.", 422)
    detected_kind = "pdf" if detected_mime == PDF_MIME_TYPE else "image"
    if declared != detected_kind:
        raise TripError("import_binary_declared_type_mismatch", "Declared artifact kind does not match file content.", 422)

    warnings: list[str] = []
    normalized_content_type = normalize_content_type(content_type)
    if normalized_content_type and normalized_content_type not in {detected_mime, "application/octet-stream"}:
        raise TripError("import_binary_signature_mismatch", "Declared MIME type does not match file content.", 422)
    label_extension = extension_from_label(original_label)
    if label_extension and not extension_matches(label_extension, detected_mime):
        raise TripError("import_binary_extension_mismatch", "File extension does not match file content.", 422)
    if has_conflicting_container(head=head, tail=tail, detected_mime=detected_mime):
        raise TripError("import_binary_polyglot_suspected", "Artifact has conflicting embedded container signatures.", 422)
    return BinaryDetection(
        declared_kind=declared,
        detected_kind=detected_kind,
        detected_mime_type=detected_mime,
        extension=extension,
        warning_codes=warnings,
    )


def read_bounds(path: Path, *, limit: int = 8192) -> tuple[bytes, bytes]:
    with path.open("rb") as handle:
        head = handle.read(limit)
        try:
            handle.seek(max(0, path.stat().st_size - limit))
        except OSError:
            return head, b""
        tail = handle.read(limit)
    return head, tail


def detect_signature(head: bytes) -> tuple[str | None, str]:
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp", "webp"
    if head.startswith(b"%PDF-"):
        return PDF_MIME_TYPE, "pdf"
    return None, "bin"


def normalize_content_type(value: str | None) -> str | None:
    if not value:
        return None
    return value.split(";", 1)[0].strip().casefold() or None


def extension_matches(extension: str, detected_mime: str) -> bool:
    extension = extension.strip(".").casefold()
    expected = {
        "image/jpeg": {"jpg", "jpeg", "jpe"},
        "image/png": {"png"},
        "image/webp": {"webp"},
        PDF_MIME_TYPE: {"pdf"},
    }
    return extension in expected.get(detected_mime, set())


def detect_executable_signature(head: bytes) -> str | None:
    lowered = head[:128].lstrip().lower()
    if head.startswith(b"MZ") or head.startswith(b"\x7fELF") or head.startswith((b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe")):
        return "BINARY_SIGNATURE_MISMATCH"
    if lowered.startswith((b"#!", b"<script", b"javascript:", b"@echo", b"powershell")):
        return "BINARY_SIGNATURE_MISMATCH"
    return None


def has_conflicting_container(*, head: bytes, tail: bytes, detected_mime: str) -> bool:
    combined = head + b"\n" + tail
    zip_markers = [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"]
    executable_markers = [b"MZ", b"\x7fELF", b"<script", b"javascript:"]
    if detected_mime != PDF_MIME_TYPE and b"%PDF-" in combined:
        return True
    if detected_mime != "image/png" and b"\x89PNG\r\n\x1a\n" in combined:
        return True
    if detected_mime != "image/jpeg" and b"\xff\xd8\xff" in combined:
        return True
    if detected_mime != "image/webp" and b"WEBP" in combined[:256]:
        return True
    if any(marker in combined for marker in zip_markers):
        return True
    if any(marker in combined for marker in executable_markers):
        return True
    return False

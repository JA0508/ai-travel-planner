from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Protocol

from app.imports.domain import URL_DOCUMENT_TEXT_TRANSFORMER_VERSION
from app.trips.errors import TripError


@dataclass(frozen=True, slots=True)
class FetchedDocument:
    content: bytes
    content_type: str
    declared_charset: str | None
    max_text_bytes: int


@dataclass(frozen=True, slots=True)
class SafeExtractionMetrics:
    raw_bytes: int
    text_bytes: int
    script_bytes: int
    visible_text_chars: int


@dataclass(frozen=True, slots=True)
class DocumentTextResult:
    title: str | None
    language_hint: str | None
    normalized_text: str
    text_checksum: str
    transformer_version: str
    warning_codes: list[str]
    extraction_metrics: SafeExtractionMetrics
    derivation_type: str
    effective_charset: str
    declared_canonical_url: str | None = None
    recovery_actions: list[str] = field(default_factory=list)


class DocumentTextExtractor(Protocol):
    def extract(self, document: FetchedDocument) -> DocumentTextResult:
        ...


class DeterministicDocumentTextExtractor:
    def extract(self, document: FetchedDocument) -> DocumentTextResult:
        content_type = document.content_type.split(";", 1)[0].strip().lower()
        decoded, effective_charset, warnings = decode_document(
            document.content,
            declared_charset=document.declared_charset,
        )
        if content_type == "text/plain":
            text = normalize_visible_text(decoded)
            derivation_type = "plain_text_normalization"
            title = None
            language = None
            script_bytes = 0
            canonical = None
        else:
            parser = MainTextHTMLParser()
            try:
                parser.feed(decoded)
                parser.close()
            except Exception as exc:
                raise TripError("import_url_extraction_failed", "HTML document could not be parsed.", 422) from exc
            text = normalize_visible_text("\n".join(parser.text_parts))
            title = normalize_single_line(parser.title) if parser.title else None
            language = normalize_single_line(parser.language_hint) if parser.language_hint else None
            canonical = parser.canonical_url
            script_bytes = parser.script_bytes
            derivation_type = "html_to_text"
            warnings.extend(parser.warning_codes)
        if len(text.encode("utf-8")) > document.max_text_bytes:
            encoded = text.encode("utf-8")[: document.max_text_bytes]
            text = encoded.decode("utf-8", errors="ignore").rstrip()
            warnings.append("import_url_text_truncated")
        if detects_dynamic_shell(text, raw=document.content):
            raise TripError("import_url_dynamic_rendering_required", "URL requires browser script rendering.", 422)
        if detects_login_wall(text, title=title, raw=document.content):
            raise TripError("import_url_login_wall_detected", "URL appears to require login.", 422)
        if not text.strip():
            raise TripError("import_url_empty_content", "URL document did not contain reviewable text.", 422)
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return DocumentTextResult(
            title=title,
            language_hint=language,
            normalized_text=text,
            text_checksum=checksum,
            transformer_version=URL_DOCUMENT_TEXT_TRANSFORMER_VERSION,
            warning_codes=unique(warnings),
            extraction_metrics=SafeExtractionMetrics(
                raw_bytes=len(document.content),
                text_bytes=len(text.encode("utf-8")),
                script_bytes=script_bytes,
                visible_text_chars=len(text),
            ),
            derivation_type=derivation_type,
            effective_charset=effective_charset,
            declared_canonical_url=canonical,
            recovery_actions=[],
        )


class MainTextHTMLParser(HTMLParser):
    BLOCK_TAGS = {"p", "div", "section", "article", "main", "li", "br", "h1", "h2", "h3", "h4", "tr"}
    SKIP_TAGS = {"script", "style", "template", "noscript", "svg", "canvas", "form", "button", "input", "nav", "header", "footer"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text_parts: list[str] = []
        self.title_parts: list[str] = []
        self.language_hint: str | None = None
        self.canonical_url: str | None = None
        self.warning_codes: list[str] = []
        self.skip_stack: list[str] = []
        self.in_title = False
        self.script_bytes = 0

    @property
    def title(self) -> str | None:
        value = normalize_visible_text(" ".join(self.title_parts))
        return value or None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): value or "" for key, value in attrs}
        lowered = tag.lower()
        if lowered == "html" and attr_map.get("lang"):
            self.language_hint = attr_map["lang"][:40]
        if lowered == "meta":
            name = (attr_map.get("name") or attr_map.get("property") or "").lower()
            if name == "description" and attr_map.get("content"):
                self.text_parts.append(attr_map["content"])
        if lowered == "link" and attr_map.get("rel", "").lower() == "canonical" and attr_map.get("href"):
            self.canonical_url = attr_map["href"][:2048]
        if lowered == "title":
            self.in_title = True
        if lowered in self.SKIP_TAGS:
            self.skip_stack.append(lowered)
        if lowered in self.BLOCK_TAGS and not self.skip_stack:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered == "title":
            self.in_title = False
        if self.skip_stack and self.skip_stack[-1] == lowered:
            self.skip_stack.pop()
        if lowered in self.BLOCK_TAGS and not self.skip_stack:
            self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_stack:
            if self.skip_stack[-1] == "script":
                self.script_bytes += len(data.encode("utf-8", errors="ignore"))
            return
        if self.in_title:
            self.title_parts.append(data)
            return
        self.text_parts.append(data)


def decode_document(content: bytes, *, declared_charset: str | None) -> tuple[str, str, list[str]]:
    warnings: list[str] = []
    if content.startswith(b"\xef\xbb\xbf"):
        return content[3:].decode("utf-8", errors="strict"), "utf-8-sig", warnings
    candidate = normalize_charset(declared_charset) or find_meta_charset(content[:4096]) or "utf-8"
    try:
        return content.decode(candidate, errors="strict"), candidate, warnings
    except (LookupError, UnicodeDecodeError):
        warnings.append("import_url_charset_fallback")
        try:
            return content.decode("utf-8", errors="replace"), "utf-8", warnings
        except UnicodeDecodeError as exc:
            raise TripError("import_url_decoding_failed", "URL document could not be decoded.", 422) from exc


def normalize_charset(value: str | None) -> str | None:
    if not value:
        return None
    charset = value.strip().strip('"').lower()
    if not charset or len(charset) > 40:
        return None
    return charset


def find_meta_charset(sample: bytes) -> str | None:
    text = sample.decode("ascii", errors="ignore")
    match = re.search(r"<meta[^>]+charset=[\"']?([A-Za-z0-9._:-]+)", text, re.I)
    return normalize_charset(match.group(1)) if match else None


def normalize_visible_text(value: str) -> str:
    value = html.unescape(value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in value.split("\n")]
    collapsed: list[str] = []
    previous_blank = False
    for line in lines:
        if not line:
            if not previous_blank:
                collapsed.append("")
            previous_blank = True
            continue
        collapsed.append(line)
        previous_blank = False
    return "\n".join(collapsed).strip()


def normalize_single_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()[:240]


def detects_login_wall(text: str, *, title: str | None, raw: bytes) -> bool:
    lowered = f"{title or ''}\n{text[:2000]}".lower()
    raw_lowered = raw[:10000].lower()
    if len(text.strip()) < 500 and (b"type='password'" in raw_lowered or b'type="password"' in raw_lowered):
        if b"log in" in raw_lowered or b"login" in raw_lowered or "登录".encode("utf-8") in raw_lowered:
            return True
    markers = ["login required", "sign in to continue", "please log in", "需要登录", "登录后查看", "请先登录"]
    formish = any(marker in lowered for marker in ["password", "验证码", "captcha", "sign in", "登录"])
    return len(text) < 1200 and formish and any(marker in lowered for marker in markers)


def detects_dynamic_shell(text: str, *, raw: bytes) -> bool:
    lowered = text[:1200].lower()
    raw_lowered = raw[:20000].lower()
    shell_markers = [b"enable javascript", b"__next", b"id=\"root\"", b"id=\"app\"", b"webpack"]
    if len(text.strip()) < 160 and sum(marker in raw_lowered for marker in shell_markers) >= 2:
        return True
    return "enable javascript" in lowered and len(text.strip()) < 500


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result

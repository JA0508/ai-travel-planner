from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from typing import Any
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.trips.errors import TripError


class WorkerDocumentSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    span_start: int = Field(..., ge=0)
    span_end: int = Field(..., gt=0)
    page_number: int = Field(..., ge=1)
    block_index: int = Field(..., ge=0)
    line_index: int = Field(..., ge=0)
    token_index: int | None = Field(default=None, ge=0)
    bbox: dict[str, Any] = Field(default_factory=dict)
    source_kind: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    warning_codes: list[str] = Field(default_factory=list)


class WorkerDocumentExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    extractor_version: str
    strategy: str
    status: str
    error_code: str | None = None
    normalized_text: str = ""
    page_count: int = Field(..., ge=0)
    spans: list[WorkerDocumentSpan] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DocumentExtractionResourceCapabilities:
    wall_clock: bool
    memory: bool
    cpu: bool
    ocr_engine: bool
    pdf_renderer: bool


class DocumentExtractionRunner:
    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_memory_mb: int,
        max_output_bytes: int,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_memory_mb = max_memory_mb
        self.max_output_bytes = max_output_bytes

    def extract(
        self,
        *,
        path: Path,
        kind: str,
        mime_type: str,
        limits: dict[str, Any],
    ) -> WorkerDocumentExtractionResult:
        command = [
            sys.executable,
            "-m",
            "app.imports.document_extraction_worker",
            "--path",
            str(path),
            "--kind",
            kind,
            "--mime-type",
            mime_type,
            "--limits-json",
            json.dumps(limits, ensure_ascii=False, sort_keys=True),
        ]
        backend_root = Path(__file__).resolve().parents[2]
        env = {
            "PYTHONPATH": str(backend_root),
            "PATH": os.environ.get("PATH", ""),
        }
        process = subprocess.Popen(
            command,
            cwd=str(backend_root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
            preexec_fn=self._resource_limiter(),
        )
        try:
            stdout, stderr = process.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            self._kill_process_group(process)
            process.communicate()
            raise TripError("import_document_extraction_timeout", "Document extraction timed out.", 422) from exc
        if len(stdout) > self.max_output_bytes or len(stderr) > self.max_output_bytes:
            raise TripError("import_document_extraction_output_invalid", "Document extraction output exceeded the configured limit.", 422)
        if process.returncode != 0:
            raise TripError("import_document_extraction_worker_failed", "Document extraction worker failed.", 422)
        try:
            payload = json.loads(stdout.decode("utf-8"))
            return WorkerDocumentExtractionResult.model_validate(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
            raise TripError("import_document_extraction_output_invalid", "Document extraction output was invalid.", 422) from exc

    @staticmethod
    def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except Exception:
            process.kill()

    def _resource_limiter(self):
        try:
            import resource
        except Exception:
            return None

        max_memory_bytes = max(1, self.max_memory_mb) * 1024 * 1024

        def limit() -> None:
            try:
                resource.setrlimit(resource.RLIMIT_CPU, (max(1, int(self.timeout_seconds) + 1), max(1, int(self.timeout_seconds) + 2)))
            except Exception:
                pass
            try:
                resource.setrlimit(resource.RLIMIT_AS, (max_memory_bytes, max_memory_bytes))
            except Exception:
                pass
            try:
                resource.setrlimit(resource.RLIMIT_NOFILE, (48, 48))
            except Exception:
                pass

        return limit


def document_extraction_resource_capabilities() -> DocumentExtractionResourceCapabilities:
    wall_clock = True
    memory = False
    cpu = False
    try:
        import resource

        memory = hasattr(resource, "RLIMIT_AS") and sys.platform != "darwin"
        cpu = hasattr(resource, "RLIMIT_CPU")
    except Exception:
        pass
    ocr_engine = False
    try:
        import shutil

        ocr_engine = shutil.which(os.getenv("IMPORT_DOCUMENT_OCR_COMMAND", "tesseract")) is not None
    except Exception:
        pass
    pdf_renderer = False
    try:
        import pypdfium2  # noqa: F401

        pdf_renderer = True
    except Exception:
        pass
    return DocumentExtractionResourceCapabilities(
        wall_clock=wall_clock,
        memory=memory,
        cpu=cpu,
        ocr_engine=ocr_engine,
        pdf_renderer=pdf_renderer,
    )

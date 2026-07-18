from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.trips.errors import TripError


@dataclass(frozen=True, slots=True)
class InspectionResourceCapabilities:
    wall_clock: bool
    memory: bool
    cpu: bool


class WorkerFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1, max_length=80)
    severity: str = Field(..., pattern="^(info|warning|block)$")
    category: str = Field(..., min_length=1, max_length=80)
    evidence: dict[str, Any] = Field(default_factory=dict)


class WorkerInspectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    inspector_version: str
    status: str
    classification: str
    error_code: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    findings: list[WorkerFinding] = Field(default_factory=list)


class ArtifactInspectionRunner:
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

    def inspect(
        self,
        *,
        path: Path,
        declared_kind: str,
        detected_mime_type: str,
        sanitized_output_path: Path | None,
        limits: dict[str, Any],
    ) -> WorkerInspectionResult:
        command = [
            sys.executable,
            "-m",
            "app.imports.inspection_worker",
            "--path",
            str(path),
            "--declared-kind",
            declared_kind,
            "--detected-mime",
            detected_mime_type,
            "--limits-json",
            json.dumps(limits, ensure_ascii=False, sort_keys=True),
        ]
        if sanitized_output_path is not None:
            command.extend(["--sanitized-output", str(sanitized_output_path)])
        backend_root = Path(__file__).resolve().parents[2]
        env = {"PYTHONPATH": str(backend_root)}
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
            stdout, stderr = process.communicate()
            raise TripError("import_inspection_timeout", "Artifact inspection timed out.", 422) from exc
        if len(stdout) > self.max_output_bytes or len(stderr) > self.max_output_bytes:
            raise TripError("import_inspection_output_invalid", "Artifact inspection output exceeded the configured limit.", 422)
        if process.returncode != 0:
            raise TripError("import_inspection_worker_failed", "Artifact inspection worker failed.", 422)
        try:
            payload = json.loads(stdout.decode("utf-8"))
            return WorkerInspectionResult.model_validate(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
            raise TripError("import_inspection_output_invalid", "Artifact inspection output was invalid.", 422) from exc

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
                resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
            except Exception:
                pass

        return limit


def resource_capabilities() -> InspectionResourceCapabilities:
    wall_clock = True
    memory = False
    cpu = False
    try:
        import resource

        memory = hasattr(resource, "RLIMIT_AS") and sys.platform != "darwin"
        cpu = hasattr(resource, "RLIMIT_CPU")
    except Exception:
        pass
    return InspectionResourceCapabilities(wall_clock=wall_clock, memory=memory, cpu=cpu)

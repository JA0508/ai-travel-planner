from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.imports.binary_detection import sanitize_original_label
from app.trips.errors import TripError


@dataclass(frozen=True, slots=True)
class StagedUpload:
    path: Path
    checksum: str
    byte_size: int
    sanitized_label: str | None


async def stream_upload_to_staging(
    *,
    upload_file: UploadFile,
    staging_root: Path,
    max_bytes: int,
    chunk_bytes: int,
    original_label: str | None,
) -> StagedUpload:
    staging_root.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(staging_root, 0o700)
    except OSError:
        pass
    target = staging_root / f"upload-{uuid4().hex}.bin"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    checksum = hashlib.sha256()
    total = 0
    fd = os.open(target, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            while True:
                chunk = await upload_file.read(chunk_bytes)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise TripError("import_binary_too_large", "Uploaded artifact exceeds the configured byte limit.", 413)
                checksum.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        if total == 0:
            raise TripError("import_binary_empty", "Uploaded artifact is empty.", 422)
        return StagedUpload(
            path=target,
            checksum=checksum.hexdigest(),
            byte_size=total,
            sanitized_label=sanitize_original_label(original_label or upload_file.filename),
        )
    except Exception:
        try:
            target.unlink()
        except OSError:
            pass
        raise
    finally:
        await upload_file.close()


def delete_staged_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def cleanup_staging_root(path: Path) -> None:
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        return

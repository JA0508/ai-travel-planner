from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Protocol
from uuid import uuid4


class ArtifactStore(Protocol):
    def put(self, *, storage_key: str, content: bytes) -> None:
        ...

    def put_file(self, *, storage_key: str, source_path: Path) -> None:
        ...

    def get(self, *, storage_key: str) -> bytes:
        ...

    def exists(self, *, storage_key: str) -> bool:
        ...

    def delete(self, *, storage_key: str) -> None:
        ...


class MemoryArtifactStore:
    def __init__(self) -> None:
        self._items: dict[str, bytes] = {}

    def put(self, *, storage_key: str, content: bytes) -> None:
        self._items[storage_key] = bytes(content)

    def put_file(self, *, storage_key: str, source_path: Path) -> None:
        self._items[storage_key] = source_path.read_bytes()

    def get(self, *, storage_key: str) -> bytes:
        try:
            return self._items[storage_key]
        except KeyError as exc:
            raise FileNotFoundError(storage_key) from exc

    def exists(self, *, storage_key: str) -> bool:
        return storage_key in self._items

    def delete(self, *, storage_key: str) -> None:
        self._items.pop(storage_key, None)


class LocalPrivateArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass

    def put(self, *, storage_key: str, content: bytes) -> None:
        path = self._resolve(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".artifact-", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def put_file(self, *, storage_key: str, source_path: Path) -> None:
        path = self._resolve(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=".artifact-", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as target, source_path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
            os.replace(tmp_name, path)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def get(self, *, storage_key: str) -> bytes:
        return self._resolve(storage_key).read_bytes()

    def exists(self, *, storage_key: str) -> bool:
        return self._resolve(storage_key).exists()

    def delete(self, *, storage_key: str) -> None:
        try:
            self._resolve(storage_key).unlink()
        except FileNotFoundError:
            return

    def _resolve(self, storage_key: str) -> Path:
        if not is_safe_storage_key(storage_key):
            raise ValueError("unsafe storage key")
        path = (self.root / storage_key).resolve()
        root = self.root.resolve()
        if root not in path.parents and path != root:
            raise ValueError("unsafe storage key")
        return path


def make_storage_key(*, artifact_type: str = "text", extension: str = "txt") -> str:
    safe_type = artifact_type.strip().replace("_", "-")
    safe_extension = extension.strip().lstrip(".") or "bin"
    return f"{safe_type}/{uuid4().hex}.{safe_extension}"


def is_safe_storage_key(value: str) -> bool:
    if not value or value.startswith("/") or "\\" in value:
        return False
    parts = Path(value).parts
    return all(part not in {"", ".", ".."} for part in parts)

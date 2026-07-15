from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.core.runtime_config import (
    get_import_artifact_root,
    get_import_artifact_store_mode,
    get_import_max_resolution_candidates,
)
from app.imports.artifacts import ArtifactStore, LocalPrivateArtifactStore, MemoryArtifactStore
from app.imports.extraction import DeterministicTextImportExtractor
from app.imports.repository import ImportRepository, MemoryImportRepository, SQLiteImportRepository
from app.imports.resolution import DeterministicPlaceMentionResolver
from app.imports.service import TextImportService
from app.persistence.database import (
    SQLiteConnectionFactory,
    get_trip_store_busy_timeout_seconds,
    get_trip_store_mode,
    get_trip_store_path,
)
from app.trips.dependencies import get_trip_persistence_service, get_trip_repository


_memory_import_repository = MemoryImportRepository()
_memory_artifact_store = MemoryArtifactStore()


@lru_cache(maxsize=1)
def get_import_repository() -> ImportRepository:
    if get_trip_store_mode() == "memory":
        return _memory_import_repository
    factory = SQLiteConnectionFactory(
        get_trip_store_path(),
        busy_timeout_seconds=get_trip_store_busy_timeout_seconds(),
    )
    factory.initialize()
    return SQLiteImportRepository(factory.connect)


@lru_cache(maxsize=1)
def get_artifact_store() -> ArtifactStore:
    mode = get_import_artifact_store_mode()
    if mode == "memory":
        return _memory_artifact_store
    return LocalPrivateArtifactStore(Path(get_import_artifact_root()))


def get_text_import_service() -> TextImportService:
    return TextImportService(
        import_repository=get_import_repository(),
        trip_repository=get_trip_repository(),
        trip_service=get_trip_persistence_service(),
        artifact_store=get_artifact_store(),
        extractor=DeterministicTextImportExtractor(),
        resolver=DeterministicPlaceMentionResolver(
            max_candidates=get_import_max_resolution_candidates()
        ),
    )


def reset_import_dependencies_for_tests() -> None:
    global _memory_import_repository, _memory_artifact_store
    get_import_repository.cache_clear()
    get_artifact_store.cache_clear()
    _memory_import_repository = MemoryImportRepository()
    _memory_artifact_store = MemoryArtifactStore()

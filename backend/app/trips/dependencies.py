from __future__ import annotations

from functools import lru_cache

from app.persistence.database import (
    SQLiteConnectionFactory,
    get_trip_store_busy_timeout_seconds,
    get_trip_store_mode,
    get_trip_store_path,
)
from app.persistence.memory_trip_repository import MemoryTripRepository
from app.persistence.sqlite_trip_repository import SQLiteTripRepository
from .repository import TripRepository
from .service import TripPersistenceService


_memory_repository = MemoryTripRepository()


@lru_cache(maxsize=1)
def get_trip_repository() -> TripRepository:
    mode = get_trip_store_mode()
    if mode == "memory":
        return _memory_repository
    factory = SQLiteConnectionFactory(
        get_trip_store_path(),
        busy_timeout_seconds=get_trip_store_busy_timeout_seconds(),
    )
    factory.initialize()
    return SQLiteTripRepository(factory.connect)


def get_trip_persistence_service() -> TripPersistenceService:
    return TripPersistenceService(get_trip_repository())


def reset_trip_repository_cache_for_tests() -> None:
    get_trip_repository.cache_clear()

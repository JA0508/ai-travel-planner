from __future__ import annotations

from functools import lru_cache

from app.persistence.sqlite_trip_repository import SQLiteTripRepository
from app.trips.dependencies import get_trip_repository

from .planning_run_repository import SQLitePlanningRunRepository


@lru_cache(maxsize=1)
def get_planning_run_repository() -> SQLitePlanningRunRepository:
    repository = get_trip_repository()
    if not isinstance(repository, SQLiteTripRepository):
        raise RuntimeError("planning_run_persistence_requires_sqlite")
    return SQLitePlanningRunRepository(repository.connection_factory)


def reset_planning_run_repository_cache_for_tests() -> None:
    get_planning_run_repository.cache_clear()

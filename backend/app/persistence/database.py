from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterator


MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
CURRENT_SCHEMA_VERSION = "0008_document_extraction_generations"
DEFAULT_TRIP_STORE_PATH = "data/trips.sqlite3"


def get_trip_store_mode() -> str:
    return os.getenv("TRIP_STORE_MODE", "sqlite").strip().lower() or "sqlite"


def get_trip_store_path() -> Path:
    return Path(os.getenv("TRIP_STORE_PATH", DEFAULT_TRIP_STORE_PATH))


def get_trip_store_busy_timeout_seconds() -> float:
    raw = os.getenv("TRIP_STORE_BUSY_TIMEOUT_SECONDS", "5")
    try:
        value = float(raw)
    except ValueError:
        return 5.0
    return value if value > 0 else 5.0


def connect_sqlite(path: Path, *, busy_timeout_seconds: float | None = None) -> sqlite3.Connection:
    if path != Path(":memory:"):
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(
        str(path),
        timeout=busy_timeout_seconds or get_trip_store_busy_timeout_seconds(),
        check_same_thread=False,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {int((busy_timeout_seconds or get_trip_store_busy_timeout_seconds()) * 1000)}")
    if path != Path(":memory:"):
        connection.execute("PRAGMA journal_mode = WAL")
    return connection


def apply_migrations(connection: sqlite3.Connection) -> None:
    for migration_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = migration_path.stem
        if migration_already_applied(connection, version):
            continue
        connection.executescript(migration_path.read_text(encoding="utf-8"))


def migration_already_applied(connection: sqlite3.Connection, version: str) -> bool:
    table = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchone()
    if table is None:
        return False
    row = connection.execute(
        "SELECT 1 FROM schema_migrations WHERE version = ?",
        (version,),
    ).fetchone()
    return row is not None


def assert_schema_current(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT 1 FROM schema_migrations WHERE version = ?",
        (CURRENT_SCHEMA_VERSION,),
    ).fetchone()
    if row is None:
        raise RuntimeError("persistence_schema_mismatch")


class SQLiteConnectionFactory:
    def __init__(self, path: Path, *, busy_timeout_seconds: float | None = None) -> None:
        self.path = path
        self.busy_timeout_seconds = busy_timeout_seconds

    def initialize(self) -> None:
        connection = self.connect()
        try:
            apply_migrations(connection)
            assert_schema_current(connection)
        finally:
            connection.close()

    def connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.path, busy_timeout_seconds=self.busy_timeout_seconds)


def sqlite_memory_connection() -> Iterator[sqlite3.Connection]:
    connection = connect_sqlite(Path(":memory:"))
    apply_migrations(connection)
    try:
        yield connection
    finally:
        connection.close()

"""Offline deployment snapshot; stop every writer before invoking the CLI."""

import argparse
import json
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def backup(source: Path, target: Path) -> None:
    database = source / "trips.sqlite3"
    if not database.is_file():
        raise FileNotFoundError("Trip database is absent; no snapshot created")
    if target.resolve().is_relative_to(source.resolve()):
        raise ValueError("Backup destination must be outside the source volume")
    target.mkdir(mode=0o700, parents=False, exist_ok=False)
    # backup() includes committed WAL data; copying the SQLite file alone does not.
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as original:
        with closing(sqlite3.connect(target / "trips.sqlite3")) as snapshot:
            original.backup(snapshot)
            snapshot.execute("PRAGMA journal_mode=DELETE")
            if snapshot.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise RuntimeError("Snapshot integrity check failed")
    artifacts = source / "import-artifacts"
    if artifacts.exists():
        shutil.copytree(artifacts, target / "import-artifacts")
    # Only this final marker identifies a complete backup. Partial failures remain
    # inspectable and must never be restored. Staging contains no durable artifacts.
    (target / "complete.json").write_text(json.dumps({
        "format": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "database_integrity": "ok",
    }) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("/data"))
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--writers-stopped", action="store_true", required=True,
                        help="Confirm backend and all other volume writers are stopped")
    args = parser.parse_args()
    backup(args.source.resolve(), args.target.resolve())

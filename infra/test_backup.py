import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path


class BackupTest(unittest.TestCase):
    def test_backup_preserves_committed_wal_and_artifacts(self):
        spec = importlib.util.spec_from_file_location("backup", Path(__file__).with_name("backup.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "data"
            source.mkdir()
            db = sqlite3.connect(source / "trips.sqlite3")
            self.addCleanup(db.close)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE trips (value TEXT)")
            db.execute("INSERT INTO trips VALUES ('fixture')")
            db.commit()
            artifacts = source / "import-artifacts"
            artifacts.mkdir()
            (artifacts / "fixture.txt").write_text("fixture")
            target = Path(root) / "snapshot"
            module.backup(source, target)
            with sqlite3.connect(target / "trips.sqlite3") as snapshot:
                self.assertEqual(snapshot.execute("SELECT value FROM trips").fetchone(), ("fixture",))
            self.assertEqual((target / "import-artifacts/fixture.txt").read_text(), "fixture")
            self.assertFalse((target / "trips.sqlite3-wal").exists())
            with self.assertRaises(FileExistsError):
                module.backup(source, target)

    def test_missing_database_does_not_create_snapshot(self):
        spec = importlib.util.spec_from_file_location("backup", Path(__file__).with_name("backup.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "snapshot"
            with self.assertRaises(FileNotFoundError):
                module.backup(Path(root), target)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()

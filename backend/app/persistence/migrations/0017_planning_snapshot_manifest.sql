ALTER TABLE planning_runs ADD COLUMN poi_snapshot_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE planning_runs ADD COLUMN route_snapshot_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE planning_runs ADD COLUMN strategy_manifest_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE planning_runs ADD COLUMN snapshot_manifest_json TEXT NOT NULL DEFAULT '{}';

CREATE TRIGGER IF NOT EXISTS planning_runs_immutable_manifest
BEFORE UPDATE ON planning_runs
WHEN OLD.poi_snapshot_json <> NEW.poi_snapshot_json
  OR OLD.route_snapshot_json <> NEW.route_snapshot_json
  OR OLD.strategy_manifest_json <> NEW.strategy_manifest_json
  OR OLD.snapshot_manifest_json <> NEW.snapshot_manifest_json
BEGIN SELECT RAISE(ABORT, 'immutable_planning_run_manifest'); END;

INSERT INTO schema_migrations(version, applied_at)
VALUES ('0017_planning_snapshot_manifest', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

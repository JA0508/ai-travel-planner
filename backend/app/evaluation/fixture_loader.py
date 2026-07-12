from __future__ import annotations

import json
from pathlib import Path


DEFAULT_FIXTURE_DIR = (
    Path(__file__).resolve().parents[2]
    / "tests"
    / "fixtures"
    / "planner_evaluation"
)


def load_manifest(fixture_dir: Path = DEFAULT_FIXTURE_DIR) -> dict:
    with (fixture_dir / "manifest.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_cases(fixture_dir: Path = DEFAULT_FIXTURE_DIR) -> list[dict]:
    manifest = load_manifest(fixture_dir)
    cases = []
    for case_file in manifest["cases"]:
        with (fixture_dir / case_file).open("r", encoding="utf-8") as handle:
            cases.append(json.load(handle))
    return cases

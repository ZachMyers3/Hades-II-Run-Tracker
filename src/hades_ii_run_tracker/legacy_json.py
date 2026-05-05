"""Read legacy JSON config and runs files (one-time bootstrap / migration)."""

from __future__ import annotations

import json
from pathlib import Path

from .models import RunRecord, TrackerConfig


def load_tracker_config_from_path(config_path: Path) -> TrackerConfig:
    with config_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return TrackerConfig.model_validate(data)


def read_runs_from_json_file(data_path: Path) -> list[RunRecord]:
    if not data_path.exists():
        return []
    with data_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    raw_runs = data if isinstance(data, list) else data.get("runs", [])
    return [RunRecord.model_validate(run) for run in raw_runs]

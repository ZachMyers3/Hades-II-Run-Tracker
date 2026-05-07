"""Read legacy JSON config and runs files (one-time bootstrap / migration)."""

from __future__ import annotations

import json
from pathlib import Path

from .models import AnalyticsSettings, RunRecord, TrackerConfig
from .scoring import compute_win_score


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
    analytics = AnalyticsSettings()
    records: list[RunRecord] = []
    for raw in raw_runs:
        item = dict(raw)
        if "computed_win_score" not in item:
            fear_raw = item.get("fear", 0)
            fear_val = int(fear_raw) if fear_raw is not None else 0
            item["computed_win_score"] = compute_win_score(
                item["side"], fear_val, analytics
            )
        records.append(RunRecord.model_validate(item))
    return records

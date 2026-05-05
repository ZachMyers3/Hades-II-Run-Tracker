"""Legacy paths and helpers (runs JSON path used only for first-run bootstrap)."""

import os
from pathlib import Path


DEFAULT_DATA_PATH = Path("data/runs.json")


def get_data_path() -> Path:
    return Path(os.getenv("HADES_DATA_PATH", DEFAULT_DATA_PATH))

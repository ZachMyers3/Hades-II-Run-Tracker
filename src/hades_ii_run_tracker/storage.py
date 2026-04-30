import json
import os
import threading
from pathlib import Path

from .models import RunRecord


DEFAULT_DATA_PATH = Path("data/runs.json")


class JsonRunStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or get_data_path()
        self._lock = threading.Lock()

    def list_runs(self) -> list[RunRecord]:
        with self._lock:
            return self._read_runs()

    def append_run(self, run: RunRecord) -> RunRecord:
        with self._lock:
            runs = self._read_runs()
            runs.append(run)
            self._write_runs(runs)
        return run

    def update_run(self, run_id: str, updated_run: RunRecord) -> RunRecord | None:
        with self._lock:
            runs = self._read_runs()
            for index, run in enumerate(runs):
                if run.id == run_id:
                    runs[index] = updated_run
                    self._write_runs(runs)
                    return updated_run

        return None

    def delete_run(self, run_id: str) -> bool:
        with self._lock:
            runs = self._read_runs()
            remaining = [run for run in runs if run.id != run_id]
            if len(remaining) == len(runs):
                return False

            self._write_runs(remaining)
            return True

    def _read_runs(self) -> list[RunRecord]:
        if not self.path.exists():
            return []

        with self.path.open("r", encoding="utf-8") as data_file:
            data = json.load(data_file)

        raw_runs = data if isinstance(data, list) else data.get("runs", [])
        return [RunRecord.model_validate(run) for run in raw_runs]

    def _write_runs(self, runs: list[RunRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        data = {
            "runs": [
                run.model_dump(mode="json")
                for run in sorted(runs, key=lambda item: item.created_at)
            ]
        }

        with temp_path.open("w", encoding="utf-8") as data_file:
            json.dump(data, data_file, indent=2)
            data_file.write("\n")

        temp_path.replace(self.path)


def get_data_path() -> Path:
    return Path(os.getenv("HADES_DATA_PATH", DEFAULT_DATA_PATH))

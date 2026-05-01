import json
import os
import threading
from collections.abc import Callable
from pathlib import Path

from .models import PublicConfig, SIDES, TrackerConfig


DEFAULT_CONFIG_PATH = Path("config.example.json")
_CONFIG_LOCK = threading.Lock()


def get_config_path() -> Path:
    return Path(os.getenv("HADES_CONFIG_PATH", DEFAULT_CONFIG_PATH))


def load_config(path: Path | None = None) -> TrackerConfig:
    config_path = path or get_config_path()
    return _load_config_path(config_path)


def update_config(
    updater: Callable[[TrackerConfig], TrackerConfig],
    path: Path | None = None,
) -> TrackerConfig:
    config_path = path or get_config_path()
    with _CONFIG_LOCK:
        config = _load_config_path(config_path)
        updated_config = updater(config)
        _validate_unique_users(updated_config)
        _write_config_path(config_path, updated_config)
        return updated_config


def _load_config_path(config_path: Path) -> TrackerConfig:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as config_file:
        data = json.load(config_file)

    config = TrackerConfig.model_validate(data)
    _validate_unique_users(config)
    return config


def _write_config_path(config_path: Path, config: TrackerConfig) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = config_path.with_suffix(f"{config_path.suffix}.tmp")
    data = config.model_dump(mode="json")

    with temp_path.open("w", encoding="utf-8") as config_file:
        json.dump(data, config_file, indent=2)
        config_file.write("\n")

    temp_path.replace(config_path)


def public_config(config: TrackerConfig) -> PublicConfig:
    return PublicConfig(
        users=config.public_users(),
        weapons=config.weapons,
        boons=config.boons,
        sides=SIDES,
    )


def _validate_unique_users(config: TrackerConfig) -> None:
    user_ids = [user.id for user in config.users]
    codes = [user.access_code for user in config.users]

    if len(user_ids) != len(set(user_ids)):
        raise ValueError("User ids must be unique.")

    if len(codes) != len(set(codes)):
        raise ValueError("Access codes must be unique.")

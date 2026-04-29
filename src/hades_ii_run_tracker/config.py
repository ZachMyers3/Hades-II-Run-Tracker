import json
import os
from pathlib import Path

from .models import PublicConfig, SIDES, TrackerConfig


DEFAULT_CONFIG_PATH = Path("config.example.json")


def get_config_path() -> Path:
    return Path(os.getenv("HADES_CONFIG_PATH", DEFAULT_CONFIG_PATH))


def load_config(path: Path | None = None) -> TrackerConfig:
    config_path = path or get_config_path()
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as config_file:
        data = json.load(config_file)

    config = TrackerConfig.model_validate(data)
    _validate_unique_users(config)
    return config


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

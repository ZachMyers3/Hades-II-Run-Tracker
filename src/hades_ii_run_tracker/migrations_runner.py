"""Run Alembic migrations (used at application startup)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

# Matches first revision in alembic/versions (legacy DBs created with create_all).
BASELINE_REVISION = "001_baseline_schema"


def _alembic_ini_path() -> Path:
    return Path(__file__).resolve().parent / "alembic.ini"


def run_migrations(engine: Engine) -> None:
    """Apply Alembic revisions. Stamps baseline on legacy SQLite files that lack
    alembic_version but already have the pre-Fear schema.
    """
    ini_path = _alembic_ini_path()
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", str(engine.url))

    inspector = inspect(engine)
    if inspector.has_table("runs") and not inspector.has_table(
        "alembic_version",
    ):
        command.stamp(cfg, BASELINE_REVISION)

    cfg.attributes["connection"] = engine
    command.upgrade(cfg, "head")
    cfg.attributes.pop("connection", None)

"""SQLAlchemy engine and session factory for the SQLite backend."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker


DEFAULT_DATABASE_URL = "sqlite:///data/hades.sqlite"


def get_database_url() -> str:
    return os.getenv("HADES_DATABASE_URL", DEFAULT_DATABASE_URL)


def _sqlite_connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def create_db_engine(url: str | None = None) -> Engine:
    resolved = url or get_database_url()
    parsed = make_url(resolved)
    if parsed.drivername == "sqlite" and parsed.database:
        db_path = Path(parsed.database)
        if not db_path.is_absolute():
            db_path = Path.cwd() / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        resolved,
        connect_args=_sqlite_connect_args(resolved),
        future=True,
    )


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, future=True)


def run_migrations(engine: Engine) -> None:
    """Apply Alembic migrations to the given engine (see migrations_runner)."""
    from .migrations_runner import run_migrations as apply_migrations

    apply_migrations(engine)

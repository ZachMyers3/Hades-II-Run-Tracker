"""SQLite-backed persistence for tracker config and runs."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, selectinload

from .config import _validate_unique_users
from .database import create_db_engine, get_database_url, run_migrations, session_factory
from .legacy_json import load_tracker_config_from_path, read_runs_from_json_file
from .models import (
    AdminSettings,
    AnalyticsSettings,
    ConfigOption,
    ConfigUser,
    RunRecord,
    TrackerConfig,
    default_fear_option,
)
from .orm_models import AppSettingsRow, OptionRow, RunBoonRow, RunRow, UserRow
from .scoring import compute_win_score


class SqliteAppStore:
    """Thread-safe store: config (users, options, settings) and runs in SQLite."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._Session = session_factory(engine)
        self._lock = threading.RLock()

    @classmethod
    def from_url(cls, url: str | None = None) -> SqliteAppStore:
        engine = create_db_engine(url or get_database_url())
        run_migrations(engine)
        return cls(engine)

    def init_db(self) -> None:
        with self._Session() as session:
            with session.begin():
                existing = session.scalar(
                    select(AppSettingsRow).where(AppSettingsRow.id == 1)
                )
                if existing is None:
                    session.add(
                        AppSettingsRow(
                            id=1,
                            admin_password=os.getenv(
                                "HADES_ADMIN_PASSWORD", ""
                            ),
                            analytics_date_range_days=7,
                            fear_weight=1.0,
                            run_amount_topside=1.3,
                            run_amount_bottomside=1.0,
                        )
                    )

    def is_empty(self) -> bool:
        with self._lock:
            with self._Session() as session:
                n_users = session.scalar(select(func.count()).select_from(UserRow))
                n_runs = session.scalar(select(func.count()).select_from(RunRow))
                return (n_users or 0) == 0 and (n_runs or 0) == 0

    def load_config(self) -> TrackerConfig:
        with self._lock:
            with self._Session() as session:
                return self._load_config_from_session(session)

    def update_config(
        self,
        updater: Callable[[TrackerConfig], TrackerConfig],
    ) -> TrackerConfig:
        with self._lock:
            with self._Session() as session:
                with session.begin():
                    config = self._load_config_from_session(session)
                    updated = updater(config.model_copy(deep=True))
                    updated = TrackerConfig.model_validate(updated.model_dump())
                    _validate_unique_users(updated)
                    self._sync_users(session, updated.users)
                    self._replace_options(
                        session,
                        updated.weapons,
                        updated.boons,
                        updated.fear,
                    )
                    self._update_settings_row(
                        session,
                        updated.admin.password,
                        updated.analytics,
                    )
                    return updated

    def list_runs(self) -> list[RunRecord]:
        with self._lock:
            with self._Session() as session:
                stmt = (
                    select(RunRow)
                    .options(selectinload(RunRow.boon_links))
                    .order_by(RunRow.created_at)
                )
                rows = session.scalars(stmt).all()
                return [self._run_row_to_record(row) for row in rows]

    def append_run(self, run: RunRecord) -> RunRecord:
        with self._lock:
            with self._Session() as session:
                with session.begin():
                    session.add(self._record_to_run_row(run))
                return run

    def update_run(self, run_id: str, updated_run: RunRecord) -> RunRecord | None:
        with self._lock:
            with self._Session() as session:
                with session.begin():
                    stmt = (
                        select(RunRow)
                        .where(RunRow.id == run_id)
                        .options(selectinload(RunRow.boon_links))
                    )
                    row = session.scalars(stmt).first()
                    if row is None:
                        return None
                    session.execute(
                        delete(RunBoonRow).where(RunBoonRow.run_id == run_id)
                    )
                    row.user_id = updated_run.user_id
                    row.side = updated_run.side
                    row.weapon = updated_run.weapon
                    row.notes = updated_run.notes
                    row.fear = updated_run.fear
                    row.computed_win_score = updated_run.computed_win_score
                    row.created_at = updated_run.created_at
                    for position, name in enumerate(updated_run.boons):
                        session.add(
                            RunBoonRow(
                                run_id=row.id,
                                position=position,
                                name=name,
                            )
                        )
                    return updated_run

    def recalculate_all_win_scores(self, analytics: AnalyticsSettings) -> int:
        """Recompute stored scores for every run using the given weights. Returns rows updated."""
        with self._lock:
            with self._Session() as session:
                with session.begin():
                    stmt = select(RunRow).options(selectinload(RunRow.boon_links))
                    rows = session.scalars(stmt).all()
                    for row in rows:
                        row.computed_win_score = compute_win_score(
                            row.side, row.fear, analytics
                        )
                    return len(rows)

    def delete_run(self, run_id: str) -> bool:
        with self._lock:
            with self._Session() as session:
                with session.begin():
                    row = session.get(RunRow, run_id)
                    if row is None:
                        return False
                    session.delete(row)
                    return True

    def replace_all_from_backup(
        self,
        config: TrackerConfig,
        runs: list[RunRecord],
    ) -> None:
        """Replace all persisted state (used for import and test seeding)."""
        _validate_unique_users(config)
        with self._lock:
            with self._Session() as session:
                with session.begin():
                    session.execute(delete(RunRow))
                    session.execute(delete(UserRow))
                    session.execute(delete(OptionRow))
                    self._insert_full_config(session, config)
                    for run in runs:
                        session.add(self._record_to_run_row(run))

    def _load_config_from_session(self, session: Session) -> TrackerConfig:
        settings = session.get(AppSettingsRow, 1)
        if settings is None:
            raise RuntimeError("App settings row missing; database not initialized.")

        users = list(
            session.scalars(
                select(UserRow).order_by(UserRow.position, UserRow.id)
            )
        )
        options = list(
            session.scalars(
                select(OptionRow).order_by(OptionRow.kind, OptionRow.position)
            )
        )
        weapons = [
            ConfigOption(
                name=row.name,
                image_url=row.image_url,
                source_url=row.source_url,
            )
            for row in options
            if row.kind == "weapon"
        ]
        boons = [
            ConfigOption(
                name=row.name,
                image_url=row.image_url,
                source_url=row.source_url,
            )
            for row in options
            if row.kind == "boon"
        ]
        fear_rows = [row for row in options if row.kind == "fear"]
        if fear_rows:
            row = min(fear_rows, key=lambda r: r.position)
            fear_opt = ConfigOption(
                name=row.name,
                image_url=row.image_url,
                source_url=row.source_url,
            )
        else:
            fear_opt = default_fear_option()
        return TrackerConfig(
            users=[
                ConfigUser(
                    id=row.id,
                    display_name=row.display_name,
                    access_code=row.access_code,
                )
                for row in users
            ],
            weapons=weapons,
            boons=boons,
            fear=fear_opt,
            analytics=AnalyticsSettings(
                date_range_days=settings.analytics_date_range_days,
                fear_weight=float(settings.fear_weight),
                run_amount_topside=float(settings.run_amount_topside),
                run_amount_bottomside=float(settings.run_amount_bottomside),
            ),
            admin=AdminSettings(password=settings.admin_password),
        )

    def _insert_full_config(
        self,
        session: Session,
        config: TrackerConfig,
    ) -> None:
        self._update_settings_row(
            session,
            config.admin.password,
            config.analytics,
        )
        for position, user in enumerate(config.users):
            session.add(
                UserRow(
                    position=position,
                    id=user.id,
                    display_name=user.display_name,
                    access_code=user.access_code,
                )
            )
        for position, weapon in enumerate(config.weapons):
            session.add(
                OptionRow(
                    kind="weapon",
                    position=position,
                    name=weapon.name,
                    image_url=weapon.image_url,
                    source_url=weapon.source_url,
                )
            )
        for position, boon in enumerate(config.boons):
            session.add(
                OptionRow(
                    kind="boon",
                    position=position,
                    name=boon.name,
                    image_url=boon.image_url,
                    source_url=boon.source_url,
                )
            )
        session.add(
            OptionRow(
                kind="fear",
                position=0,
                name=config.fear.name,
                image_url=config.fear.image_url,
                source_url=config.fear.source_url,
            )
        )

    def _update_settings_row(
        self,
        session: Session,
        admin_password: str,
        analytics: AnalyticsSettings,
    ) -> None:
        row = session.get(AppSettingsRow, 1)
        if row is None:
            session.add(
                AppSettingsRow(
                    id=1,
                    admin_password=admin_password,
                    analytics_date_range_days=analytics.date_range_days,
                    fear_weight=analytics.fear_weight,
                    run_amount_topside=analytics.run_amount_topside,
                    run_amount_bottomside=analytics.run_amount_bottomside,
                )
            )
        else:
            row.admin_password = admin_password
            row.analytics_date_range_days = analytics.date_range_days
            row.fear_weight = analytics.fear_weight
            row.run_amount_topside = analytics.run_amount_topside
            row.run_amount_bottomside = analytics.run_amount_bottomside

    def _replace_options(
        self,
        session: Session,
        weapons: list[ConfigOption],
        boons: list[ConfigOption],
        fear: ConfigOption,
    ) -> None:
        session.execute(delete(OptionRow))
        for position, weapon in enumerate(weapons):
            session.add(
                OptionRow(
                    kind="weapon",
                    position=position,
                    name=weapon.name,
                    image_url=weapon.image_url,
                    source_url=weapon.source_url,
                )
            )
        for position, boon in enumerate(boons):
            session.add(
                OptionRow(
                    kind="boon",
                    position=position,
                    name=boon.name,
                    image_url=boon.image_url,
                    source_url=boon.source_url,
                )
            )
        session.add(
            OptionRow(
                kind="fear",
                position=0,
                name=fear.name,
                image_url=fear.image_url,
                source_url=fear.source_url,
            )
        )

    def _sync_users(self, session: Session, users: list[ConfigUser]) -> None:
        old_ids = {
            row.id for row in session.scalars(select(UserRow)).all()
        }
        new_ids = {user.id for user in users}
        for removed_id in old_ids - new_ids:
            has_run = session.scalar(
                select(RunRow.id).where(RunRow.user_id == removed_id).limit(1)
            )
            if has_run:
                raise ValueError(
                    "Cannot delete a user with logged runs.",
                )
            row = session.get(UserRow, removed_id)
            if row is not None:
                session.delete(row)

        for position, user in enumerate(users):
            existing = session.get(UserRow, user.id)
            if existing is None:
                session.add(
                    UserRow(
                        position=position,
                        id=user.id,
                        display_name=user.display_name,
                        access_code=user.access_code,
                    )
                )
            else:
                existing.position = position
                existing.display_name = user.display_name
                existing.access_code = user.access_code

    @staticmethod
    def _run_row_to_record(row: RunRow) -> RunRecord:
        boons = [link.name for link in row.boon_links]
        return RunRecord(
            id=row.id,
            user_id=row.user_id,
            side=row.side,  # type: ignore[arg-type]
            weapon=row.weapon,
            boons=boons,
            notes=row.notes,
            fear=row.fear,
            computed_win_score=float(row.computed_win_score),
            created_at=row.created_at,
        )

    @staticmethod
    def _record_to_run_row(run: RunRecord) -> RunRow:
        row = RunRow(
            id=run.id,
            user_id=run.user_id,
            side=run.side,
            weapon=run.weapon,
            notes=run.notes,
            fear=run.fear,
            computed_win_score=run.computed_win_score,
            created_at=run.created_at,
        )
        for position, name in enumerate(run.boons):
            row.boon_links.append(
                RunBoonRow(position=position, name=name),
            )
        return row


def try_bootstrap_store_from_legacy_files(
    store: SqliteAppStore,
    config_path: Path | None,
    data_path: Path | None,
) -> bool:
    """If the DB is empty and a legacy config JSON exists, import it (and runs)."""
    if not store.is_empty():
        return False
    if not config_path or not Path(config_path).exists():
        return False
    config = load_tracker_config_from_path(Path(config_path))
    runs: list[RunRecord] = []
    if data_path:
        runs = read_runs_from_json_file(Path(data_path))
    store.replace_all_from_backup(config, runs)
    return True

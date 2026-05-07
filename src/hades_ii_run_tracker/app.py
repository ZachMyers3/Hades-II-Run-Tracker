import os
import secrets
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from hmac import compare_digest
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError

from .app_store import SqliteAppStore, try_bootstrap_store_from_legacy_files
from .config import get_config_path, public_config
from .storage import get_data_path
from .models import (
    AdminBackupImport,
    AdminConfigUpdate,
    AdminLogin,
    AdminRunUpdate,
    AdminUser,
    AdminUserCreate,
    AdminUserUpdate,
    Analytics,
    AnalyticsSettings,
    ConfigUser,
    DateBucket,
    ExtraAnalytics,
    FearAnalytics,
    FearUserRow,
    RunCreate,
    RunRecord,
    TrackerConfig,
    UserAnalytics,
    UserExtraAnalytics,
    UserMetric,
    UserWinScoreStackedRow,
    WinScoreLeaderboardAnalytics,
    WinScoreLeaderboardSettings,
    WinScoreLeaderboardUserRow,
)
from .scoring import compute_win_score, display_points


STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    database_url: str | None = None,
    config_path: Path | str | None = None,
    data_path: Path | str | None = None,
    bootstrap_legacy_json: bool = True,
) -> FastAPI:
    web_app = FastAPI(title="Hades II Run Tracker")
    store = SqliteAppStore.from_url(database_url)
    store.init_db()
    web_app.state.store = store
    web_app.state.config_path = (
        Path(config_path) if config_path is not None else None
    )
    web_app.state.data_path = (
        Path(data_path) if data_path is not None else None
    )
    legacy_config = (
        Path(config_path) if config_path is not None else get_config_path()
    )
    legacy_data = Path(data_path) if data_path is not None else get_data_path()
    if bootstrap_legacy_json:
        try_bootstrap_store_from_legacy_files(
            store,
            legacy_config,
            legacy_data,
        )

    web_app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @web_app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @web_app.get("/admin", include_in_schema=False)
    def admin() -> FileResponse:
        return FileResponse(STATIC_DIR / "admin.html")

    @web_app.get("/api/config/public")
    def get_public_config():
        return public_config(_load_runtime_config(web_app))

    @web_app.post("/api/admin/login")
    def admin_login(payload: AdminLogin) -> dict[str, bool]:
        _validate_admin_password(
            _load_runtime_config(web_app), payload.password
        )
        return {"authenticated": True}

    @web_app.get("/api/admin/users", response_model=list[AdminUser])
    def admin_list_users(
        x_admin_password: str | None = Header(default=None),
    ) -> list[AdminUser]:
        config = _require_admin(web_app, x_admin_password)
        run_counts = Counter(
            run.user_id for run in web_app.state.store.list_runs()
        )
        return [
            AdminUser(
                id=user.id,
                display_name=user.display_name,
                access_code=user.access_code,
                run_count=run_counts[user.id],
            )
            for user in config.users
        ]

    @web_app.post(
        "/api/admin/users",
        response_model=AdminUser,
        status_code=201,
    )
    def admin_create_user(
        payload: AdminUserCreate,
        x_admin_password: str | None = Header(default=None),
    ) -> AdminUser:
        _require_admin(web_app, x_admin_password)

        def add_user(config):
            config.users.append(
                ConfigUser(
                    id=payload.id,
                    display_name=payload.display_name,
                    access_code=payload.access_code,
                )
            )
            return config

        config = _update_config_or_400(web_app, add_user)
        user = next(user for user in config.users if user.id == payload.id)
        return AdminUser(**user.model_dump(), run_count=0)

    @web_app.put("/api/admin/users/{user_id}", response_model=AdminUser)
    def admin_update_user(
        user_id: str,
        payload: AdminUserUpdate,
        x_admin_password: str | None = Header(default=None),
    ) -> AdminUser:
        _require_admin(web_app, x_admin_password)
        runs = web_app.state.store.list_runs()

        def edit_user(config):
            user = _config_user(config, user_id)
            user.display_name = payload.display_name
            user.access_code = payload.access_code
            return config

        config = _update_config_or_400(web_app, edit_user)
        user = _config_user(config, user_id)
        run_count = sum(run.user_id == user.id for run in runs)
        return AdminUser(**user.model_dump(), run_count=run_count)

    @web_app.post(
        "/api/admin/users/{user_id}/rotate-code",
        response_model=AdminUser,
    )
    def admin_rotate_user_code(
        user_id: str,
        x_admin_password: str | None = Header(default=None),
    ) -> AdminUser:
        _require_admin(web_app, x_admin_password)
        runs = web_app.state.store.list_runs()

        def rotate_code(config):
            user = _config_user(config, user_id)
            existing_codes = {
                config_user.access_code
                for config_user in config.users
                if config_user.id != user_id
            }
            user.access_code = _generate_access_code(existing_codes)
            return config

        config = _update_config_or_400(web_app, rotate_code)
        user = _config_user(config, user_id)
        run_count = sum(run.user_id == user.id for run in runs)
        return AdminUser(**user.model_dump(), run_count=run_count)

    @web_app.delete("/api/admin/users/{user_id}", status_code=204)
    def admin_delete_user(
        user_id: str,
        x_admin_password: str | None = Header(default=None),
    ) -> None:
        _require_admin(web_app, x_admin_password)
        runs = web_app.state.store.list_runs()
        if any(run.user_id == user_id for run in runs):
            raise HTTPException(
                status_code=409,
                detail="Cannot delete a user with logged runs.",
            )

        def delete_user(config):
            _config_user(config, user_id)
            config.users = [
                user for user in config.users if user.id != user_id
            ]
            return config

        _update_config_or_400(web_app, delete_user)

    @web_app.get("/api/admin/runs", response_model=list[RunRecord])
    def admin_list_runs(
        x_admin_password: str | None = Header(default=None),
    ) -> list[RunRecord]:
        _require_admin(web_app, x_admin_password)
        return _sorted_runs(web_app.state.store.list_runs())

    @web_app.put("/api/admin/runs/{run_id}", response_model=RunRecord)
    def admin_update_run(
        run_id: str,
        payload: AdminRunUpdate,
        x_admin_password: str | None = Header(default=None),
    ) -> RunRecord:
        config = _require_admin(web_app, x_admin_password)
        if _config_user_or_none(config, payload.user_id) is None:
            raise HTTPException(status_code=400, detail="Unknown user.")

        _validate_options(
            payload,
            [weapon.name for weapon in config.weapons],
            [boon.name for boon in config.boons],
        )
        existing_run = next(
            (
                run
                for run in web_app.state.store.list_runs()
                if run.id == run_id
            ),
            None,
        )
        if existing_run is None:
            raise HTTPException(status_code=404, detail="Run not found.")

        updated_run = RunRecord(
            id=existing_run.id,
            user_id=payload.user_id,
            side=payload.side,
            weapon=payload.weapon,
            boons=payload.boons,
            notes=payload.notes,
            fear=payload.fear,
            computed_win_score=compute_win_score(
                payload.side,
                payload.fear,
                config.analytics,
            ),
            created_at=existing_run.created_at,
        )
        saved_run = web_app.state.store.update_run(run_id, updated_run)
        if saved_run is None:
            raise HTTPException(status_code=404, detail="Run not found.")

        return saved_run

    @web_app.delete("/api/admin/runs/{run_id}", status_code=204)
    def admin_delete_run(
        run_id: str,
        x_admin_password: str | None = Header(default=None),
    ) -> None:
        _require_admin(web_app, x_admin_password)
        deleted = web_app.state.store.delete_run(run_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Run not found.")

    @web_app.get("/api/admin/config", response_model=AdminConfigUpdate)
    def admin_get_config(
        x_admin_password: str | None = Header(default=None),
    ) -> AdminConfigUpdate:
        config = _require_admin(web_app, x_admin_password)
        return AdminConfigUpdate(
            weapons=config.weapons,
            boons=config.boons,
            fear=config.fear,
            analytics=config.analytics,
        )

    @web_app.put("/api/admin/config", response_model=AdminConfigUpdate)
    def admin_update_config(
        payload: AdminConfigUpdate,
        x_admin_password: str | None = Header(default=None),
    ) -> AdminConfigUpdate:
        _require_admin(web_app, x_admin_password)

        def edit_config(config):
            config.weapons = payload.weapons
            config.boons = payload.boons
            config.analytics = payload.analytics
            if payload.fear is not None:
                config.fear = payload.fear
            return config

        config = _update_config_or_400(web_app, edit_config)
        return AdminConfigUpdate(
            weapons=config.weapons,
            boons=config.boons,
            fear=config.fear,
            analytics=config.analytics,
        )

    @web_app.get("/api/admin/export")
    def admin_export(
        x_admin_password: str | None = Header(default=None),
    ) -> dict:
        config = _require_admin(web_app, x_admin_password)
        runs = web_app.state.store.list_runs()
        return {
            "exported_at": _utc_now(),
            "config": config.model_dump(mode="json"),
            "runs": [
                run.model_dump(mode="json") for run in _sorted_runs(runs)
            ],
        }

    @web_app.post("/api/admin/import")
    def admin_import(
        payload: AdminBackupImport,
        x_admin_password: str | None = Header(default=None),
    ) -> dict[str, bool | int]:
        _require_admin(web_app, x_admin_password)
        store = web_app.state.store
        if not store.is_empty() and not payload.confirm_replace:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Database is not empty. "
                    "Send confirm_replace: true to wipe and import."
                ),
            )
        try:
            config = TrackerConfig.model_validate(payload.config)
            runs = [
                _run_record_from_import_dict(run, config.analytics)
                for run in payload.runs
            ]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            store.replace_all_from_backup(config, runs)
        except IntegrityError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "imported_users": len(config.users),
            "imported_runs": len(runs),
            "replaced": True,
        }

    @web_app.post("/api/admin/recalculate-scores")
    def admin_recalculate_scores(
        x_admin_password: str | None = Header(default=None),
    ) -> dict[str, int]:
        config = _require_admin(web_app, x_admin_password)
        updated = web_app.state.store.recalculate_all_win_scores(config.analytics)
        return {"runs_updated": updated}

    @web_app.get("/api/runs", response_model=list[RunRecord])
    def list_runs() -> list[RunRecord]:
        return _sorted_runs(web_app.state.store.list_runs())

    @web_app.post("/api/runs", response_model=RunRecord, status_code=201)
    def create_run(payload: RunCreate) -> RunRecord:
        config = _load_runtime_config(web_app)
        user = config.user_for_code(payload.access_code)
        if user is None:
            raise HTTPException(status_code=403, detail="Invalid access code.")

        _validate_options(
            payload,
            [weapon.name for weapon in config.weapons],
            [boon.name for boon in config.boons],
        )
        fear_value = _fear_for_create(payload)
        run = RunRecord(
            id=str(uuid4()),
            user_id=user.id,
            side=payload.side,
            weapon=payload.weapon,
            boons=payload.boons,
            notes=payload.notes,
            fear=fear_value,
            computed_win_score=compute_win_score(
                payload.side,
                fear_value,
                config.analytics,
            ),
            created_at=_utc_now(),
        )
        return web_app.state.store.append_run(run)

    @web_app.put("/api/runs/{run_id}", response_model=RunRecord)
    def update_run(run_id: str, payload: RunCreate) -> RunRecord:
        config = _load_runtime_config(web_app)
        runs = web_app.state.store.list_runs()
        existing_run = next((run for run in runs if run.id == run_id), None)
        if existing_run is None:
            raise HTTPException(status_code=404, detail="Run not found.")

        user = config.user_for_code(payload.access_code)
        if user is None or user.id != existing_run.user_id:
            raise HTTPException(status_code=403, detail="Invalid access code.")

        _validate_options(
            payload,
            [weapon.name for weapon in config.weapons],
            [boon.name for boon in config.boons],
        )
        fear_value = _fear_for_owner_update(payload, existing_run)
        updated_run = RunRecord(
            id=existing_run.id,
            user_id=existing_run.user_id,
            side=payload.side,
            weapon=payload.weapon,
            boons=payload.boons,
            notes=payload.notes,
            fear=fear_value,
            computed_win_score=compute_win_score(
                payload.side,
                fear_value,
                config.analytics,
            ),
            created_at=existing_run.created_at,
        )
        saved_run = web_app.state.store.update_run(run_id, updated_run)
        if saved_run is None:
            raise HTTPException(status_code=404, detail="Run not found.")

        return saved_run

    @web_app.delete("/api/runs/{run_id}", status_code=204)
    def delete_run(
        run_id: str,
        x_admin_code: str | None = Header(default=None),
        x_access_code: str | None = Header(default=None),
    ) -> None:
        admin_code = os.getenv("ADMIN_CODE")
        is_admin = bool(admin_code and x_admin_code == admin_code)
        if not is_admin:
            config = _load_runtime_config(web_app)
            runs = web_app.state.store.list_runs()
            existing_run = next(
                (run for run in runs if run.id == run_id), None
            )
            if existing_run is None:
                raise HTTPException(status_code=404, detail="Run not found.")

            user = config.user_for_code(x_access_code or "")
            if user is None or user.id != existing_run.user_id:
                raise HTTPException(
                    status_code=403, detail="Invalid access code."
                )

        deleted = web_app.state.store.delete_run(run_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Run not found.")

    @web_app.get("/api/analytics", response_model=Analytics)
    def get_analytics(
        date_range_days: int | None = Query(default=None, ge=1, le=365),
    ) -> Analytics:
        config = _load_runtime_config(web_app)
        runs = web_app.state.store.list_runs()
        effective_range = date_range_days or config.analytics.date_range_days
        by_side = Counter(run.side for run in runs)
        by_weapon = Counter(run.weapon for run in runs if run.weapon)
        by_boon = Counter(boon for run in runs for boon in run.boons)
        daily_runs = _build_daily_runs(runs, config.users, effective_range)

        user_summaries = []
        for user in config.users:
            user_runs = [run for run in runs if run.user_id == user.id]
            weapons = Counter(run.weapon for run in user_runs if run.weapon)
            boons = Counter(boon for run in user_runs for boon in run.boons)
            user_summaries.append(
                UserAnalytics(
                    user_id=user.id,
                    display_name=user.display_name,
                    total=len(user_runs),
                    topside=sum(run.side == "topside" for run in user_runs),
                    bottomside=sum(
                        run.side == "bottomside" for run in user_runs
                    ),
                    favorite_weapon=_first_counter_key(weapons),
                    favorite_boons=[
                        boon for boon, _count in boons.most_common(3)
                    ],
                )
            )

        return Analytics(
            date_range_days=effective_range,
            total_runs=len(runs),
            by_side=dict(by_side),
            by_weapon=dict(by_weapon),
            by_boon=dict(by_boon),
            daily_runs=daily_runs,
            users=user_summaries,
            extra_metrics=_build_extra_metrics(
                runs,
                config.users,
                daily_runs,
            ),
            fear=_build_fear_analytics(runs, config.users),
            win_score_leaderboard=_build_win_score_leaderboard(
                runs,
                config.users,
                config.analytics,
            ),
            win_score_stacked_by_user=_build_win_score_stacked_by_user(
                runs,
                config.users,
            ),
            recent_runs=_sorted_runs(runs)[:10],
        )

    return web_app


def _require_admin(web_app: FastAPI, password: str | None):
    config = _load_runtime_config(web_app)
    _validate_admin_password(config, password or "")
    return config


def _validate_admin_password(config, password: str) -> None:
    configured_password = config.admin.password
    if not configured_password or not compare_digest(
        password.strip(),
        configured_password,
    ):
        raise HTTPException(status_code=403, detail="Invalid admin password.")


def _update_config_or_400(web_app: FastAPI, updater):
    try:
        return web_app.state.store.update_config(updater)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _config_user(config, user_id: str):
    user = _config_user_or_none(config, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


def _config_user_or_none(config, user_id: str):
    return next((user for user in config.users if user.id == user_id), None)


def _generate_access_code(existing_codes: set[str]) -> str:
    while True:
        code = secrets.token_urlsafe(9)
        if code not in existing_codes:
            return code


def _load_runtime_config(web_app: FastAPI):
    try:
        return web_app.state.store.load_config()
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _run_record_from_import_dict(
    raw: dict,
    analytics: AnalyticsSettings,
) -> RunRecord:
    data = dict(raw)
    if "computed_win_score" not in data:
        fear_raw = data.get("fear", 0)
        fear_val = int(fear_raw) if fear_raw is not None else 0
        data["computed_win_score"] = compute_win_score(
            data["side"],
            fear_val,
            analytics,
        )
    return RunRecord.model_validate(data)


def _fear_for_create(payload: RunCreate) -> int:
    if "fear" not in payload.model_fields_set or payload.fear is None:
        return 0
    return payload.fear


def _fear_for_owner_update(payload: RunCreate, existing_run: RunRecord) -> int:
    if "fear" not in payload.model_fields_set:
        return existing_run.fear
    return 0 if payload.fear is None else payload.fear


def _validate_options(
    payload: RunCreate | AdminRunUpdate,
    weapons: list[str],
    boons: list[str],
) -> None:
    if payload.weapon and weapons and payload.weapon not in weapons:
        raise HTTPException(status_code=400, detail="Unknown weapon.")

    unknown_boons = [
        boon for boon in payload.boons if boons and boon not in boons
    ]
    if unknown_boons:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown boon: {', '.join(unknown_boons)}",
        )


def _sorted_runs(runs: list[RunRecord]) -> list[RunRecord]:
    return sorted(runs, key=lambda run: run.created_at, reverse=True)


def _build_daily_runs(
    runs: list[RunRecord],
    users,
    date_range_days: int,
) -> list[DateBucket]:
    today = datetime.now(UTC).date()
    start_date = today - timedelta(days=date_range_days - 1)
    runs_by_date = _runs_by_date(runs)
    cumulative_total = 0
    cumulative_by_user = {user.id: 0 for user in users}
    cumulative_topside_by_user = {user.id: 0 for user in users}
    cumulative_bottomside_by_user = {user.id: 0 for user in users}
    buckets = []

    for offset in range(date_range_days):
        bucket_date = start_date + timedelta(days=offset)
        bucket_runs = runs_by_date.get(bucket_date, [])
        by_user = {
            user.id: sum(run.user_id == user.id for run in bucket_runs)
            for user in users
        }
        by_user_topside = {
            user.id: sum(
                run.user_id == user.id and run.side == "topside"
                for run in bucket_runs
            )
            for user in users
        }
        by_user_bottomside = {
            user.id: sum(
                run.user_id == user.id and run.side == "bottomside"
                for run in bucket_runs
            )
            for user in users
        }
        for user in users:
            cumulative_by_user[user.id] += by_user[user.id]
            cumulative_topside_by_user[user.id] += by_user_topside[user.id]
            cumulative_bottomside_by_user[user.id] += by_user_bottomside[
                user.id
            ]
        topside = sum(run.side == "topside" for run in bucket_runs)
        bottomside = sum(run.side == "bottomside" for run in bucket_runs)
        total = len(bucket_runs)
        cumulative_total += total
        buckets.append(
            DateBucket(
                date=bucket_date.isoformat(),
                total=total,
                topside=topside,
                bottomside=bottomside,
                cumulative_total=cumulative_total,
                by_user=by_user,
                by_user_topside=dict(cumulative_topside_by_user),
                by_user_bottomside=dict(cumulative_bottomside_by_user),
                by_user_cumulative=dict(cumulative_by_user),
            )
        )

    return buckets


def _build_extra_metrics(
    runs: list[RunRecord],
    users,
    daily_runs: list[DateBucket],
) -> ExtraAnalytics:
    totals_by_user = Counter(run.user_id for run in runs)
    leader = None
    if totals_by_user:
        leader_id, leader_total = totals_by_user.most_common(1)[0]
        leader_user = next(
            (user for user in users if user.id == leader_id), None
        )
        if leader_user:
            leader = UserMetric(
                user_id=leader_user.id,
                display_name=leader_user.display_name,
                total=leader_total,
            )

    recent_by_user = Counter()
    for bucket in daily_runs:
        recent_by_user.update(bucket.by_user)

    recent_momentum = [
        UserMetric(
            user_id=user.id,
            display_name=user.display_name,
            total=recent_by_user[user.id],
        )
        for user in users
    ]

    user_stats = []
    for user in users:
        user_runs = [run for run in runs if run.user_id == user.id]
        total = len(user_runs)
        topside = sum(run.side == "topside" for run in user_runs)
        bottomside = sum(run.side == "bottomside" for run in user_runs)
        user_stats.append(
            UserExtraAnalytics(
                user_id=user.id,
                display_name=user.display_name,
                recent_total=recent_by_user[user.id],
                weapon_variety=len(
                    {run.weapon for run in user_runs if run.weapon}
                ),
                boon_variety=len(
                    {boon for run in user_runs for boon in run.boons}
                ),
                topside_percent=round((topside / total) * 100, 1)
                if total
                else 0,
                bottomside_percent=round((bottomside / total) * 100, 1)
                if total
                else 0,
            )
        )

    return ExtraAnalytics(
        current_leader=leader,
        recent_momentum=recent_momentum,
        user_stats=user_stats,
    )


def _build_fear_analytics(
    runs: list[RunRecord],
    users: list[ConfigUser],
) -> FearAnalytics:
    n = len(runs)
    if n == 0:
        empty_rows = [
            FearUserRow(
                user_id=user.id,
                display_name=user.display_name,
                run_count=0,
                avg_fear=0.0,
                max_fear=0,
            )
            for user in users
        ]
        return FearAnalytics(
            avg_fear=0.0,
            max_fear=0,
            max_fear_user_id=None,
            max_fear_display_name=None,
            runs_with_fear_positive=0,
            pct_runs_fear_positive=0.0,
            avg_fear_topside=0.0,
            avg_fear_bottomside=0.0,
            max_fear_topside=0,
            max_fear_bottomside=0,
            fear_buckets={"0": 0, "1-25": 0, "26-50": 0, "51-99": 0},
            by_user=empty_rows,
            highest_avg_fear_user=None,
            highest_max_fear_user=None,
        )

    total_fear = sum(run.fear for run in runs)
    avg_fear = round(total_fear / n, 2)
    max_run = max(runs, key=lambda r: (r.fear, r.id))
    runs_positive = sum(1 for run in runs if run.fear > 0)
    pct_positive = round(100 * runs_positive / n, 1)

    top_runs = [r for r in runs if r.side == "topside"]
    bot_runs = [r for r in runs if r.side == "bottomside"]
    avg_top = (
        round(sum(r.fear for r in top_runs) / len(top_runs), 2) if top_runs else 0.0
    )
    avg_bot = (
        round(sum(r.fear for r in bot_runs) / len(bot_runs), 2) if bot_runs else 0.0
    )
    max_top = max((r.fear for r in top_runs), default=0)
    max_bot = max((r.fear for r in bot_runs), default=0)

    buckets = {"0": 0, "1-25": 0, "26-50": 0, "51-99": 0}
    for run in runs:
        f = run.fear
        if f == 0:
            buckets["0"] += 1
        elif f <= 25:
            buckets["1-25"] += 1
        elif f <= 50:
            buckets["26-50"] += 1
        else:
            buckets["51-99"] += 1

    by_user_rows: list[FearUserRow] = []
    for user in users:
        user_runs = [r for r in runs if r.user_id == user.id]
        cnt = len(user_runs)
        if cnt == 0:
            by_user_rows.append(
                FearUserRow(
                    user_id=user.id,
                    display_name=user.display_name,
                    run_count=0,
                    avg_fear=0.0,
                    max_fear=0,
                )
            )
        else:
            ut = sum(r.fear for r in user_runs)
            by_user_rows.append(
                FearUserRow(
                    user_id=user.id,
                    display_name=user.display_name,
                    run_count=cnt,
                    avg_fear=round(ut / cnt, 2),
                    max_fear=max(r.fear for r in user_runs),
                )
            )

    eligible = [row for row in by_user_rows if row.run_count > 0]
    highest_avg = (
        max(
            eligible,
            key=lambda row: (row.avg_fear, row.run_count, row.display_name),
        )
        if eligible
        else None
    )
    highest_max = (
        max(
            eligible,
            key=lambda row: (row.max_fear, row.avg_fear, row.display_name),
        )
        if eligible
        else None
    )

    max_owner = next(
        (u for u in users if u.id == max_run.user_id),
        None,
    )
    max_fear_user_id = max_run.user_id
    max_fear_display_name = (
        max_owner.display_name if max_owner else max_run.user_id
    )

    return FearAnalytics(
        avg_fear=avg_fear,
        max_fear=max_run.fear,
        max_fear_user_id=max_fear_user_id,
        max_fear_display_name=max_fear_display_name,
        runs_with_fear_positive=runs_positive,
        pct_runs_fear_positive=pct_positive,
        avg_fear_topside=avg_top,
        avg_fear_bottomside=avg_bot,
        max_fear_topside=max_top,
        max_fear_bottomside=max_bot,
        fear_buckets=buckets,
        by_user=by_user_rows,
        highest_avg_fear_user=highest_avg,
        highest_max_fear_user=highest_max,
    )


def _run_display_points(run: RunRecord) -> int:
    return display_points(run.computed_win_score)


def _build_win_score_stacked_by_user(
    runs: list[RunRecord],
    users: list[ConfigUser],
) -> list[UserWinScoreStackedRow]:
    """Cumulative display points by side per user (all runs; ignores date range)."""
    rows: list[UserWinScoreStackedRow] = []
    for user in users:
        user_runs = [r for r in runs if r.user_id == user.id]
        topside = sum(
            _run_display_points(r) for r in user_runs if r.side == "topside"
        )
        bottomside = sum(
            _run_display_points(r) for r in user_runs if r.side == "bottomside"
        )
        rows.append(
            UserWinScoreStackedRow(
                user_id=user.id,
                display_name=user.display_name,
                topside_display_points=topside,
                bottomside_display_points=bottomside,
            )
        )
    rows.sort(
        key=lambda r: (
            -(r.topside_display_points + r.bottomside_display_points),
            r.display_name,
        )
    )
    return rows


def _best_run_by_display_points_then_time(
    runs: list[RunRecord],
) -> RunRecord | None:
    """Highest display points; ties broken by earlier `created_at`."""
    if not runs:
        return None
    return sorted(
        runs,
        key=lambda r: (-_run_display_points(r), r.created_at),
    )[0]


def _bucket_display_points(d: int) -> str:
    if d < 130:
        return "<130"
    if d <= 169:
        return "130-169"
    if d <= 209:
        return "170-209"
    return "210+"


def _build_win_score_leaderboard(
    runs: list[RunRecord],
    users: list[ConfigUser],
    settings: AnalyticsSettings,
) -> WinScoreLeaderboardAnalytics:
    common_opts = dict(
        settings=WinScoreLeaderboardSettings(
            fear_weight=float(settings.fear_weight),
            run_amount_topside=float(settings.run_amount_topside),
            run_amount_bottomside=float(settings.run_amount_bottomside),
        ),
    )

    n = len(runs)
    if n == 0:
        empty_rows = [
            WinScoreLeaderboardUserRow(
                user_id=user.id,
                display_name=user.display_name,
                run_count=0,
                avg_display_points=0.0,
                max_display_points=0,
                display_points_total=0,
            )
            for user in users
        ]
        return WinScoreLeaderboardAnalytics(
            **common_opts,
            grand_total_display_points=0,
            avg_score=0.0,
            max_single_display_points=0,
            max_score_user_id=None,
            max_score_display_name=None,
            avg_score_topside=0.0,
            avg_score_bottomside=0.0,
            max_score_topside=0,
            max_score_bottomside=0,
            score_buckets={
                "<130": 0,
                "130-169": 0,
                "170-209": 0,
                "210+": 0,
            },
            by_user=empty_rows,
            highest_avg_score_user=None,
            highest_max_score_user=None,
        )

    dp_vals = [_run_display_points(r) for r in runs]
    grand = sum(dp_vals)
    avg_score = round(grand / n, 2)

    best_run = sorted(
        runs,
        key=lambda r: (-_run_display_points(r), r.created_at),
    )[0]
    max_single = _run_display_points(best_run)
    max_owner = next(
        (u for u in users if u.id == best_run.user_id),
        None,
    )

    top_runs = [r for r in runs if r.side == "topside"]
    bot_runs = [r for r in runs if r.side == "bottomside"]
    avg_top = (
        round(sum(_run_display_points(r) for r in top_runs) / len(top_runs), 2)
        if top_runs
        else 0.0
    )
    avg_bot = (
        round(sum(_run_display_points(r) for r in bot_runs) / len(bot_runs), 2)
        if bot_runs
        else 0.0
    )

    best_top = _best_run_by_display_points_then_time(top_runs)
    best_bot = _best_run_by_display_points_then_time(bot_runs)
    max_top = _run_display_points(best_top) if best_top is not None else 0
    max_bot = _run_display_points(best_bot) if best_bot is not None else 0

    buckets = {"<130": 0, "130-169": 0, "170-209": 0, "210+": 0}
    for d in dp_vals:
        buckets[_bucket_display_points(d)] += 1

    rows: list[WinScoreLeaderboardUserRow] = []
    for user in users:
        user_runs = [r for r in runs if r.user_id == user.id]
        cnt = len(user_runs)
        if cnt == 0:
            rows.append(
                WinScoreLeaderboardUserRow(
                    user_id=user.id,
                    display_name=user.display_name,
                    run_count=0,
                    avg_display_points=0.0,
                    max_display_points=0,
                    display_points_total=0,
                )
            )
        else:
            u_pts = [_run_display_points(r) for r in user_runs]
            rows.append(
                WinScoreLeaderboardUserRow(
                    user_id=user.id,
                    display_name=user.display_name,
                    run_count=cnt,
                    avg_display_points=round(sum(u_pts) / cnt, 2),
                    max_display_points=max(u_pts),
                    display_points_total=sum(u_pts),
                )
            )

    rows.sort(key=lambda r: (-r.display_points_total, r.display_name))

    eligible = [row for row in rows if row.run_count > 0]
    highest_avg = (
        max(
            eligible,
            key=lambda row: (
                row.avg_display_points,
                row.run_count,
                row.display_name,
            ),
        )
        if eligible
        else None
    )
    highest_max = (
        max(
            eligible,
            key=lambda row: (
                row.max_display_points,
                row.avg_display_points,
                row.display_name,
            ),
        )
        if eligible
        else None
    )

    return WinScoreLeaderboardAnalytics(
        **common_opts,
        grand_total_display_points=grand,
        avg_score=avg_score,
        max_single_display_points=max_single,
        max_score_user_id=best_run.user_id,
        max_score_display_name=(
            max_owner.display_name if max_owner else best_run.user_id
        ),
        avg_score_topside=avg_top,
        avg_score_bottomside=avg_bot,
        max_score_topside=max_top,
        max_score_bottomside=max_bot,
        score_buckets=buckets,
        by_user=rows,
        highest_avg_score_user=highest_avg,
        highest_max_score_user=highest_max,
    )


def _runs_by_date(runs: list[RunRecord]) -> dict[date, list[RunRecord]]:
    grouped: dict[date, list[RunRecord]] = {}
    for run in runs:
        run_date = _parse_created_at(run.created_at).date()
        grouped.setdefault(run_date, []).append(run)
    return grouped


def _parse_created_at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _first_counter_key(counter: Counter) -> str | None:
    most_common = counter.most_common(1)
    return most_common[0][0] if most_common else None


def _utc_now() -> str:
    return (
        datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


app = create_app()

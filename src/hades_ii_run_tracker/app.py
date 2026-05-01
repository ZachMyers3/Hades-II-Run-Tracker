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

from .config import load_config, public_config, update_config
from .models import (
    AdminConfigUpdate,
    AdminLogin,
    AdminRunUpdate,
    AdminUser,
    AdminUserCreate,
    AdminUserUpdate,
    Analytics,
    ConfigUser,
    DateBucket,
    ExtraAnalytics,
    RunCreate,
    RunRecord,
    UserAnalytics,
    UserExtraAnalytics,
    UserMetric,
)
from .storage import JsonRunStore


STATIC_DIR = Path(__file__).parent / "static"


def create_app(
    config_path: Path | str | None = None,
    data_path: Path | str | None = None,
) -> FastAPI:
    web_app = FastAPI(title="Hades II Run Tracker")
    web_app.state.config_path = Path(config_path) if config_path else None
    web_app.state.store = JsonRunStore(Path(data_path) if data_path else None)

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
            return config

        config = _update_config_or_400(web_app, edit_config)
        return AdminConfigUpdate(
            weapons=config.weapons,
            boons=config.boons,
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
        run = RunRecord(
            id=str(uuid4()),
            user_id=user.id,
            side=payload.side,
            weapon=payload.weapon,
            boons=payload.boons,
            notes=payload.notes,
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
        updated_run = RunRecord(
            id=existing_run.id,
            user_id=existing_run.user_id,
            side=payload.side,
            weapon=payload.weapon,
            boons=payload.boons,
            notes=payload.notes,
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
        return update_config(updater, web_app.state.config_path)
    except HTTPException:
        raise
    except ValueError as exc:
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
        return load_config(web_app.state.config_path)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _validate_options(
    payload: RunCreate,
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

import os
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import load_config, public_config
from .models import (
    Analytics,
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

    @web_app.get("/api/config/public")
    def get_public_config():
        return public_config(_load_runtime_config(web_app))

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
            existing_run = next((run for run in runs if run.id == run_id), None)
            if existing_run is None:
                raise HTTPException(status_code=404, detail="Run not found.")

            user = config.user_for_code(x_access_code or "")
            if user is None or user.id != existing_run.user_id:
                raise HTTPException(status_code=403, detail="Invalid access code.")

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

    unknown_boons = [boon for boon in payload.boons if boons and boon not in boons]
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
            cumulative_bottomside_by_user[user.id] += by_user_bottomside[user.id]
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
        leader_user = next((user for user in users if user.id == leader_id), None)
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
                weapon_variety=len({run.weapon for run in user_runs if run.weapon}),
                boon_variety=len({boon for run in user_runs for boon in run.boons}),
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
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


app = create_app()

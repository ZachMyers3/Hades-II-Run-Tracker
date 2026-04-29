import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import load_config, public_config
from .models import Analytics, RunCreate, RunRecord, UserAnalytics
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

    @web_app.delete("/api/runs/{run_id}", status_code=204)
    def delete_run(
        run_id: str,
        x_admin_code: str | None = Header(default=None),
    ) -> None:
        admin_code = os.getenv("ADMIN_CODE")
        if not admin_code or x_admin_code != admin_code:
            raise HTTPException(status_code=403, detail="Invalid admin code.")

        deleted = web_app.state.store.delete_run(run_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Run not found.")

    @web_app.get("/api/analytics", response_model=Analytics)
    def get_analytics() -> Analytics:
        config = _load_runtime_config(web_app)
        runs = web_app.state.store.list_runs()
        by_side = Counter(run.side for run in runs)
        by_weapon = Counter(run.weapon for run in runs if run.weapon)
        by_boon = Counter(boon for run in runs for boon in run.boons)

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
            total_runs=len(runs),
            by_side=dict(by_side),
            by_weapon=dict(by_weapon),
            by_boon=dict(by_boon),
            users=user_summaries,
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


def _first_counter_key(counter: Counter) -> str | None:
    most_common = counter.most_common(1)
    return most_common[0][0] if most_common else None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


app = create_app()

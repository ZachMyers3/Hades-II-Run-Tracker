# Hades II Run Tracker

A small self-hosted website for tracking successful Hades II runs with
friends. It uses a FastAPI backend, **SQLite** (via SQLAlchemy) for
persistence, and a plain HTML/CSS/JS frontend.

There is no account system. You manage users and access codes in the admin
dashboard (or seed from JSON on first start), and anyone with a configured
code can submit a victory.

## Features

- Track topside and bottomside victories per friend.
- Optionally record weapon, primary boons, notes, and Fear (0–99).
- Show side-by-side friend cards, line charts, bar charts, and lightweight analytics.
- Persist data in a single SQLite database file (with optional first-run import
  from legacy `config.json` + `runs.json`).
- Run locally with Uvicorn or as a Docker container.

## Configuration and storage

### SQLite database

All application state (users, access codes, weapons, boons, analytics
defaults, admin password, and runs) lives in one SQLite file. Set:

- `HADES_DATABASE_URL` — SQLAlchemy URL, default `sqlite:///data/hades.sqlite`
  (relative paths are resolved from the process working directory).

On **first start**, if the database is empty **and** a legacy JSON config file
exists at `HADES_CONFIG_PATH`, the app imports that file and, if present,
`HADES_DATA_PATH` as `runs.json` into the database. After that, JSON files are
not used for normal operation.

Optional one-time escape hatch if you start with an empty database and no
JSON to import: set `HADES_ADMIN_PASSWORD` so the first admin login works, then
use `/admin` or `POST /api/admin/import`.

### Schema migrations (Alembic)

The app runs **Alembic** `upgrade head` on startup against `HADES_DATABASE_URL`.
Migration scripts and `alembic.ini` live under
[`src/hades_ii_run_tracker/`](src/hades_ii_run_tracker/) next to the package code
so they ship with the install.

If you have an **older SQLite file** that was created before Alembic was added
and has no `alembic_version` table, the first startup **stamps** the baseline
revision and then applies pending migrations (for example adding optional run
fields).

To run migrations manually (from the repo root, with `PYTHONPATH=src` or inside
the Poetry environment):

```powershell
poetry run alembic -c src/hades_ii_run_tracker/alembic.ini upgrade head
```

### Runs: Fear (optional)

Each run may include an optional **Fear** integer from **0** through **99**
(`null` when unset). It is accepted on `POST /api/runs` and `PUT /api/runs/{id}`
(with the runner’s access code) and can be edited on **Admin → Runs** without
an access code. Export/import JSON includes `fear` when present.

### Legacy JSON shape (bootstrap and import)

Copy the example config to seed a new install (Docker does this for
`/app/config/config.json`):

```bash
cp config.example.json config.json
```

`HADES_CONFIG_PATH` defaults to `config.example.json` in development when not
set. `HADES_DATA_PATH` defaults to `data/runs.json` and is only read during the
one-time empty-database bootstrap.

```json
{
  "users": [
    {
      "id": "zach",
      "display_name": "Zach",
      "access_code": "moonshot"
    }
  ],
  "weapons": [
    {
      "name": "Witch's Staff",
      "image_url": "/static/assets/weapons/witch-staff.png"
    }
  ],
  "boons": [
    {
      "name": "Aphrodite",
      "image_url": "/static/assets/boons/aphrodite.png"
    }
  ],
  "analytics": {
    "date_range_days": 7
  },
  "admin": {
    "password": "change-me"
  }
}
```

For a bare-bones config, `weapons` and `boons` can still be simple string
arrays. Use objects when you want cached local images or source attribution.
The analytics date range controls the default number of days shown in the
runs-over-time chart. Users can temporarily change that range in the web UI.

### Migrating older JSON-only installs

1. On the old app, open `/admin` and use **Export Backup** (or call
   `GET /api/admin/export`) to download JSON with `config` and `runs`.
2. Deploy the new version with a fresh or empty `HADES_DATABASE_URL` file.
3. Log into `/admin` and use **Import Backup…** to upload that JSON (or call
   `POST /api/admin/import` with the same payload). If the database already has
   data, confirm the replace prompt so the server sends `confirm_replace: true`.

The import API accepts the same JSON shape as export.

## Analytics

The dashboard includes:

- A line chart for per-user daily wins, topside wins, bottomside wins, and
  cumulative wins over the selected date range.
- Bar charts for victories by realm, weapon, and boon.
- Quick stats for current leader, recent momentum, weapon variety, boon
  variety, and realm split.

## Running Locally

```powershell
poetry install
$env:HADES_DATABASE_URL = "sqlite:///data/hades.sqlite"
$env:HADES_CONFIG_PATH = "config.json"
$env:HADES_DATA_PATH = "data/runs.json"
poetry run uvicorn hades_ii_run_tracker.app:app --reload
```

Open [http://localhost:8000](http://localhost:8000).

## Docker

Build the image:

```bash
docker build -t hades-ii-run-tracker .
```

Run with a mounted config file and data directory:

```bash
docker run --rm -p 8000:8000 \
  -e PUID="$(id -u)" \
  -e PGID="$(id -g)" \
  -v ./config.json:/app/config/config.json \
  -v ./data:/app/data \
  hades-ii-run-tracker
```

On PowerShell:

```powershell
docker run --rm -p 8000:8000 `
  -e PUID=1000 `
  -e PGID=1000 `
  -v ${PWD}/config.json:/app/config/config.json `
  -v ${PWD}/data:/app/data `
  hades-ii-run-tracker
```

SQLite in Docker uses an **absolute** path: `sqlite:////app/data/hades.sqlite`
(four slashes). `sqlite:///app/data/...` is treated as relative to the process
working directory and becomes `/app/app/data/...` when `WORKDIR` is `/app`.

Mount `/app/data` so `hades.sqlite` (and any legacy `runs.json` used only for
first-run bootstrap) persist. Mount `config.json` if you rely on automatic
import from JSON when the database file is new and empty. Back up the SQLite
file and export JSON backups from `/admin` if you care about the history.

The image **must start as root** (the default): the entrypoint runs `chown` on
`/app/config` and `/app/data`, then starts the app with **`setpriv`** (from
`util-linux`) as `PUID:PGID` — same role as `gosu`, without passwd-based edge cases.
Set **`HADES_ENTRYPOINT_DEBUG=1`** to log the intended UID/GID before the drop.
If you set **`user:`** in Compose, **Kubernetes `runAsUser`**, or anything that
makes the process non-root from the first exec, that step never runs — `PUID` /
`PGID` are ignored and you may see permission errors on the mounts. Remove
`user:` / `runAsUser` so the entrypoint can run as root, or `chown` the host
`./data` (and config file) to match the UID the container uses.

With **`PUID=0` and `PGID=0`**, the entrypoint skips `setpriv` and the app runs as
root inside the container (simplest for permission debugging, weaker isolation).

## Admin Dashboard

Open `/admin` and enter the configured `admin.password`. Admin access is kept in
browser session storage, so closing the tab clears it.

The admin dashboard can:

- Add, edit, delete, and rotate access codes for users.
- Block user deletion when that user still has logged runs.
- Edit, delete, or reassign runs without needing the runner's access code.
- Edit weapons, boons, image URLs, source URLs, and the default analytics range.
- Export a JSON backup containing config and runs.
- Import a JSON backup to migrate or restore (with confirmation when replacing
  existing data).

Deleting a mistaken run can also be done with `ADMIN_CODE` and curl:

```bash
curl -X DELETE \
  -H "X-Admin-Code: your-admin-code" \
  http://localhost:8000/api/runs/RUN_ID
```

## Theme And Assets

The app serves cached local copies of the configured boon and weapon icons from
`src/hades_ii_run_tracker/static/assets/`. The example config includes
`source_url` values pointing back to the Hades Wiki file pages for attribution.
If you add or replace assets, place them under `static/assets/` and update the
matching `image_url` in your config.

## Running Tests

```bash
poetry run pytest
```

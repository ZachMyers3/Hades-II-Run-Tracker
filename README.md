# Hades II Run Tracker

A small self-hosted website for tracking successful Hades II runs with
friends. It uses a FastAPI backend, flat JSON storage, and a plain
HTML/CSS/JS frontend.

There is no account system. You manage users and access codes in a config
file, and anyone with a configured code can submit a victory.

## Features

- Track topside and bottomside victories per friend.
- Optionally record weapon, primary boons, and notes.
- Show side-by-side friend cards and lightweight analytics.
- Persist data in a single JSON file.
- Run locally with Uvicorn or as a Docker container.

## Configuration

Copy the example config and edit users/access codes:

```bash
cp config.example.json config.json
```

The app reads config from `HADES_CONFIG_PATH`, defaulting to
`config.example.json` during local development.

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
  ]
}
```

The data file path is controlled by `HADES_DATA_PATH`, defaulting to
`data/runs.json`.

For a bare-bones config, `weapons` and `boons` can still be simple string
arrays. Use objects when you want cached local images or source attribution.

## Running Locally

```powershell
poetry install
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
  -v ./config.json:/app/config/config.json:ro \
  -v ./data:/app/data \
  hades-ii-run-tracker
```

On PowerShell:

```powershell
docker run --rm -p 8000:8000 `
  -v ${PWD}/config.json:/app/config/config.json:ro `
  -v ${PWD}/data:/app/data `
  hades-ii-run-tracker
```

Back up `data/runs.json` if you care about the history.

## Admin Cleanup

Deleting a mistaken run is intentionally minimal. Set `ADMIN_CODE` and call:

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

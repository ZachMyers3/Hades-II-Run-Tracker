import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from hades_ii_run_tracker.app import create_app
from hades_ii_run_tracker.storage import JsonRunStore


def test_public_config_omits_access_codes(tmp_path):
    client = make_client(tmp_path)

    response = client.get("/api/config/public")

    assert response.status_code == 200
    payload = response.json()
    assert payload["users"] == [
        {"id": "zach", "display_name": "Zach"},
        {"id": "meg", "display_name": "Meg"},
    ]
    assert payload["weapons"][0] == {
        "name": "Sister Blades",
        "image_url": "/static/assets/weapons/sister-blades.png",
        "source_url": None,
    }
    assert "access_code" not in json.dumps(payload)


def test_valid_access_code_creates_run(tmp_path):
    client = make_client(tmp_path)

    response = client.post(
        "/api/runs",
        json={
            "access_code": "moonshot",
            "side": "topside",
            "weapon": "Sister Blades",
            "boons": ["Aphrodite", "Apollo"],
            "notes": "Knife night.",
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["user_id"] == "zach"
    assert created["side"] == "topside"
    assert created["weapon"] == "Sister Blades"

    runs = client.get("/api/runs").json()
    assert len(runs) == 1
    assert runs[0]["id"] == created["id"]


def test_invalid_access_code_is_rejected(tmp_path):
    client = make_client(tmp_path)

    response = client.post(
        "/api/runs",
        json={"access_code": "wrong", "side": "bottomside"},
    )

    assert response.status_code == 403
    assert client.get("/api/runs").json() == []


def test_analytics_counts_runs(tmp_path):
    client = make_client(tmp_path)
    client.post(
        "/api/runs",
        json={
            "access_code": "moonshot",
            "side": "topside",
            "weapon": "Sister Blades",
            "boons": ["Apollo"],
        },
    )
    client.post(
        "/api/runs",
        json={
            "access_code": "fury",
            "side": "bottomside",
            "weapon": "Moonstone Axe",
            "boons": ["Apollo", "Zeus"],
        },
    )

    response = client.get("/api/analytics")

    assert response.status_code == 200
    analytics = response.json()
    assert analytics["date_range_days"] == 7
    assert analytics["total_runs"] == 2
    assert analytics["by_side"] == {"topside": 1, "bottomside": 1}
    assert analytics["by_weapon"]["Sister Blades"] == 1
    assert analytics["by_boon"]["Apollo"] == 2
    assert len(analytics["daily_runs"]) == 7
    assert analytics["users"][0]["total"] == 1
    assert analytics["users"][1]["bottomside"] == 1
    assert analytics["extra_metrics"]["current_leader"]["total"] == 1


def test_custom_analytics_config_changes_default_bucket_count(tmp_path):
    config = sample_config()
    config["analytics"] = {"date_range_days": 3}
    client = make_client(tmp_path, config=config)

    response = client.get("/api/analytics")

    assert response.status_code == 200
    analytics = response.json()
    assert analytics["date_range_days"] == 3
    assert len(analytics["daily_runs"]) == 3


def test_analytics_query_parameter_overrides_default_bucket_count(tmp_path):
    client = make_client(tmp_path)

    response = client.get("/api/analytics?date_range_days=2")

    assert response.status_code == 200
    analytics = response.json()
    assert analytics["date_range_days"] == 2
    assert len(analytics["daily_runs"]) == 2


def test_daily_buckets_include_empty_days_and_counts(tmp_path):
    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)
    client = make_client(
        tmp_path,
        runs=[
            sample_run(
                "run-1",
                "zach",
                "topside",
                created_at=f"{yesterday.isoformat()}T12:00:00Z",
            ),
            sample_run(
                "run-2",
                "meg",
                "bottomside",
                created_at=f"{today.isoformat()}T12:00:00Z",
            ),
            sample_run(
                "run-3",
                "meg",
                "bottomside",
                created_at=f"{today.isoformat()}T13:00:00Z",
            ),
        ],
    )

    response = client.get("/api/analytics?date_range_days=3")

    assert response.status_code == 200
    buckets = response.json()["daily_runs"]
    assert [bucket["total"] for bucket in buckets] == [0, 1, 2]
    assert buckets[0]["by_user"] == {"zach": 0, "meg": 0}
    assert buckets[0]["by_user_topside"] == {"zach": 0, "meg": 0}
    assert buckets[0]["by_user_bottomside"] == {"zach": 0, "meg": 0}
    assert buckets[0]["by_user_cumulative"] == {"zach": 0, "meg": 0}
    assert buckets[1]["topside"] == 1
    assert buckets[1]["by_user_topside"] == {"zach": 1, "meg": 0}
    assert buckets[1]["by_user_bottomside"] == {"zach": 0, "meg": 0}
    assert buckets[1]["by_user_cumulative"] == {"zach": 1, "meg": 0}
    assert buckets[2]["bottomside"] == 2
    assert buckets[2]["by_user_topside"] == {"zach": 0, "meg": 0}
    assert buckets[2]["by_user_bottomside"] == {"zach": 0, "meg": 2}
    assert buckets[2]["by_user_cumulative"] == {"zach": 1, "meg": 2}
    assert [bucket["cumulative_total"] for bucket in buckets] == [0, 1, 3]


def test_json_storage_initializes_when_missing(tmp_path):
    store = JsonRunStore(tmp_path / "missing" / "runs.json")

    assert store.list_runs() == []


def make_client(tmp_path, config=None, runs=None) -> TestClient:
    config_path = tmp_path / "config.json"
    data_path = tmp_path / "runs.json"
    config_path.write_text(json.dumps(config or sample_config()), encoding="utf-8")
    if runs is not None:
        data_path.write_text(json.dumps({"runs": runs}), encoding="utf-8")
    return TestClient(create_app(config_path=config_path, data_path=data_path))


def sample_config() -> dict:
    return {
        "users": [
            {
                "id": "zach",
                "display_name": "Zach",
                "access_code": "moonshot",
            },
            {
                "id": "meg",
                "display_name": "Meg",
                "access_code": "fury",
            },
        ],
        "weapons": [
            {
                "name": "Sister Blades",
                "image_url": "/static/assets/weapons/sister-blades.png",
            },
            {"name": "Moonstone Axe"},
        ],
        "boons": [
            {"name": "Aphrodite"},
            {
                "name": "Apollo",
                "image_url": "/static/assets/boons/apollo.png",
            },
            {"name": "Zeus"},
        ],
    }


def sample_run(
    run_id: str,
    user_id: str,
    side: str,
    created_at: str,
) -> dict:
    return {
        "id": run_id,
        "user_id": user_id,
        "side": side,
        "weapon": "Sister Blades",
        "boons": ["Apollo"],
        "notes": None,
        "created_at": created_at,
    }

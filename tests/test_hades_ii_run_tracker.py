import json

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
    assert analytics["total_runs"] == 2
    assert analytics["by_side"] == {"topside": 1, "bottomside": 1}
    assert analytics["by_weapon"]["Sister Blades"] == 1
    assert analytics["by_boon"]["Apollo"] == 2
    assert analytics["users"][0]["total"] == 1
    assert analytics["users"][1]["bottomside"] == 1


def test_json_storage_initializes_when_missing(tmp_path):
    store = JsonRunStore(tmp_path / "missing" / "runs.json")

    assert store.list_runs() == []


def make_client(tmp_path) -> TestClient:
    config_path = tmp_path / "config.json"
    data_path = tmp_path / "runs.json"
    config_path.write_text(json.dumps(sample_config()), encoding="utf-8")
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

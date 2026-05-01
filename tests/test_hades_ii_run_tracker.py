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
    assert "admin" not in json.dumps(payload)
    assert "letmein" not in json.dumps(payload)


def test_admin_login_accepts_configured_password(tmp_path):
    client = make_client(tmp_path)

    response = client.post(
        "/api/admin/login",
        json={"password": "letmein"},
    )

    assert response.status_code == 200
    assert response.json() == {"authenticated": True}


def test_admin_login_rejects_invalid_password(tmp_path):
    client = make_client(tmp_path)

    response = client.post(
        "/api/admin/login",
        json={"password": "wrong"},
    )

    assert response.status_code == 403


def test_admin_user_list_requires_password(tmp_path):
    client = make_client(tmp_path)

    response = client.get("/api/admin/users")

    assert response.status_code == 403


def test_admin_user_list_includes_access_codes_and_run_counts(tmp_path):
    client = make_client(
        tmp_path,
        runs=[
            sample_run(
                "run-1",
                "zach",
                "topside",
                created_at="2026-04-29T12:00:00Z",
            )
        ],
    )

    response = client.get("/api/admin/users", headers=admin_headers())

    assert response.status_code == 200
    users = response.json()
    assert users[0] == {
        "id": "zach",
        "display_name": "Zach",
        "access_code": "moonshot",
        "run_count": 1,
    }


def test_admin_can_create_user_and_persist_to_config(tmp_path):
    client = make_client(tmp_path)

    response = client.post(
        "/api/admin/users",
        headers=admin_headers(),
        json={
            "id": "than",
            "display_name": "Than",
            "access_code": "death",
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] == "than"
    config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert config["users"][2] == {
        "id": "than",
        "display_name": "Than",
        "access_code": "death",
    }


def test_admin_create_user_rejects_duplicate_ids_and_codes(tmp_path):
    client = make_client(tmp_path)

    duplicate_id = client.post(
        "/api/admin/users",
        headers=admin_headers(),
        json={
            "id": "zach",
            "display_name": "Other Zach",
            "access_code": "other",
        },
    )
    duplicate_code = client.post(
        "/api/admin/users",
        headers=admin_headers(),
        json={
            "id": "other",
            "display_name": "Other",
            "access_code": "moonshot",
        },
    )

    assert duplicate_id.status_code == 400
    assert duplicate_code.status_code == 400


def test_admin_can_update_user(tmp_path):
    client = make_client(tmp_path)

    response = client.put(
        "/api/admin/users/zach",
        headers=admin_headers(),
        json={"display_name": "Zagreus", "access_code": "blood"},
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "Zagreus"
    config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert config["users"][0]["display_name"] == "Zagreus"
    assert config["users"][0]["access_code"] == "blood"


def test_admin_can_rotate_user_access_code(tmp_path):
    client = make_client(tmp_path)

    response = client.post(
        "/api/admin/users/zach/rotate-code",
        headers=admin_headers(),
    )

    assert response.status_code == 200
    rotated = response.json()
    assert rotated["access_code"] != "moonshot"
    config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert config["users"][0]["access_code"] == rotated["access_code"]


def test_admin_can_delete_user_without_runs(tmp_path):
    client = make_client(tmp_path)

    response = client.delete("/api/admin/users/meg", headers=admin_headers())

    assert response.status_code == 204
    config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert [user["id"] for user in config["users"]] == ["zach"]


def test_admin_delete_user_is_blocked_when_runs_exist(tmp_path):
    client = make_client(
        tmp_path,
        runs=[
            sample_run(
                "run-1",
                "meg",
                "bottomside",
                created_at="2026-04-29T12:00:00Z",
            )
        ],
    )

    response = client.delete("/api/admin/users/meg", headers=admin_headers())

    assert response.status_code == 409
    config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert [user["id"] for user in config["users"]] == ["zach", "meg"]


def test_admin_can_edit_and_reassign_run(tmp_path):
    client = make_client(
        tmp_path,
        runs=[
            sample_run(
                "run-1",
                "zach",
                "topside",
                created_at="2026-04-29T12:00:00Z",
            )
        ],
    )

    response = client.put(
        "/api/admin/runs/run-1",
        headers=admin_headers(),
        json={
            "user_id": "meg",
            "side": "bottomside",
            "weapon": "Moonstone Axe",
            "boons": ["Zeus"],
            "notes": "Admin cleanup.",
        },
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["user_id"] == "meg"
    assert updated["side"] == "bottomside"
    assert updated["weapon"] == "Moonstone Axe"
    assert updated["created_at"] == "2026-04-29T12:00:00Z"


def test_admin_can_delete_run(tmp_path):
    client = make_client(
        tmp_path,
        runs=[
            sample_run(
                "run-1",
                "zach",
                "topside",
                created_at="2026-04-29T12:00:00Z",
            )
        ],
    )

    response = client.delete("/api/admin/runs/run-1", headers=admin_headers())

    assert response.status_code == 204
    assert client.get("/api/runs").json() == []


def test_admin_can_update_options_and_analytics(tmp_path):
    client = make_client(tmp_path)

    response = client.put(
        "/api/admin/config",
        headers=admin_headers(),
        json={
            "weapons": [
                {
                    "name": "Black Coat",
                    "image_url": "/static/assets/weapons/black-coat.png",
                }
            ],
            "boons": [{"name": "Hera"}],
            "analytics": {"date_range_days": 14},
        },
    )

    assert response.status_code == 200
    config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert config["weapons"] == [
        {
            "name": "Black Coat",
            "image_url": "/static/assets/weapons/black-coat.png",
            "source_url": None,
        }
    ]
    assert config["analytics"] == {"date_range_days": 14}


def test_admin_export_includes_config_and_runs(tmp_path):
    client = make_client(
        tmp_path,
        runs=[
            sample_run(
                "run-1",
                "zach",
                "topside",
                created_at="2026-04-29T12:00:00Z",
            )
        ],
    )

    response = client.get("/api/admin/export", headers=admin_headers())

    assert response.status_code == 200
    backup = response.json()
    assert backup["config"]["admin"]["password"] == "letmein"
    assert backup["runs"][0]["id"] == "run-1"


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


def test_valid_owner_access_code_updates_run(tmp_path):
    client = make_client(
        tmp_path,
        runs=[
            sample_run(
                "run-1",
                "zach",
                "topside",
                created_at="2026-04-29T12:00:00Z",
            )
        ],
    )

    response = client.put(
        "/api/runs/run-1",
        json={
            "access_code": "moonshot",
            "side": "bottomside",
            "weapon": "Moonstone Axe",
            "boons": ["Zeus"],
            "notes": "Corrected details.",
        },
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["id"] == "run-1"
    assert updated["user_id"] == "zach"
    assert updated["side"] == "bottomside"
    assert updated["weapon"] == "Moonstone Axe"
    assert updated["boons"] == ["Zeus"]
    assert updated["notes"] == "Corrected details."
    assert updated["created_at"] == "2026-04-29T12:00:00Z"


def test_wrong_access_code_does_not_update_run(tmp_path):
    client = make_client(
        tmp_path,
        runs=[
            sample_run(
                "run-1",
                "zach",
                "topside",
                created_at="2026-04-29T12:00:00Z",
            )
        ],
    )

    response = client.put(
        "/api/runs/run-1",
        json={
            "access_code": "fury",
            "side": "bottomside",
            "weapon": "Moonstone Axe",
            "boons": ["Zeus"],
            "notes": "Should not save.",
        },
    )

    assert response.status_code == 403
    saved_run = client.get("/api/runs").json()[0]
    assert saved_run["side"] == "topside"
    assert saved_run["weapon"] == "Sister Blades"
    assert saved_run["boons"] == ["Apollo"]
    assert saved_run["notes"] is None


def test_valid_owner_access_code_deletes_run(tmp_path):
    client = make_client(
        tmp_path,
        runs=[
            sample_run(
                "run-1",
                "zach",
                "topside",
                created_at="2026-04-29T12:00:00Z",
            )
        ],
    )

    response = client.delete(
        "/api/runs/run-1",
        headers={"X-Access-Code": "moonshot"},
    )

    assert response.status_code == 204
    assert client.get("/api/runs").json() == []


def test_wrong_access_code_does_not_delete_run(tmp_path):
    client = make_client(
        tmp_path,
        runs=[
            sample_run(
                "run-1",
                "zach",
                "topside",
                created_at="2026-04-29T12:00:00Z",
            )
        ],
    )

    response = client.delete(
        "/api/runs/run-1",
        headers={"X-Access-Code": "fury"},
    )

    assert response.status_code == 403
    assert len(client.get("/api/runs").json()) == 1


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
    assert buckets[2]["by_user_topside"] == {"zach": 1, "meg": 0}
    assert buckets[2]["by_user_bottomside"] == {"zach": 0, "meg": 2}
    assert buckets[2]["by_user_cumulative"] == {"zach": 1, "meg": 2}
    assert [bucket["cumulative_total"] for bucket in buckets] == [0, 1, 3]


def test_json_storage_initializes_when_missing(tmp_path):
    store = JsonRunStore(tmp_path / "missing" / "runs.json")

    assert store.list_runs() == []


def make_client(tmp_path, config=None, runs=None) -> TestClient:
    config_path = tmp_path / "config.json"
    data_path = tmp_path / "runs.json"
    config_path.write_text(
        json.dumps(config or sample_config()), encoding="utf-8"
    )
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
        "admin": {"password": "letmein"},
    }


def admin_headers() -> dict[str, str]:
    return {"X-Admin-Password": "letmein"}


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

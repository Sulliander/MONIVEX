import time
from sqlalchemy import func, select
from app.models import CheckResult, Monitor, User, WorkerLease
from app.monitoring.vault import decrypt


def create(client, kind="heartbeat", **values):
    return client.post("/api/monitors", json={"name": "test", "kind": kind, **values})


def test_permissions_cover_all_network_operations(logged_in, database):
    monitor = create(logged_in).json()
    with database() as db:
        db.scalar(select(User)).role = "viewer"
        db.commit()
    assert logged_in.get("/api/monitors").status_code == 200
    assert create(logged_in).status_code == 403
    assert logged_in.post(f"/api/monitors/{monitor['id']}/test").status_code == 403
    assert (
        logged_in.patch(
            f"/api/monitors/{monitor['id']}/pause", json={"paused": True}
        ).status_code
        == 403
    )


def test_targets_are_validated_before_creation(logged_in, monkeypatch):
    assert (
        create(
            logged_in, "tcp", config={"host": "169.254.169.254", "port": 80}
        ).status_code
        == 422
    )
    from app.config import get_settings

    monkeypatch.setenv("MONIVEX_ALLOWED_NETWORKS", "")
    get_settings.cache_clear()
    assert (
        create(logged_in, "tcp", config={"host": "127.0.0.1", "port": 80}).status_code
        == 422
    )
    get_settings.cache_clear()


def test_heartbeat_token_is_once_only_and_hashed(logged_in, database):
    response = create(logged_in)
    assert response.status_code == 201
    row = response.json()
    token = row["heartbeat_token"]
    mid = row["id"]
    assert token not in logged_in.get("/api/monitors").text
    with database() as db:
        monitor = db.get(Monitor, mid)
        assert monitor.heartbeat_hash != token and len(monitor.heartbeat_hash) == 64
    assert (
        logged_in.post(
            f"/api/heartbeats/{mid}", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 404
    )
    # Machine endpoint requires neither browser session nor Origin/CSRF.
    logged_in.cookies.clear()
    logged_in.headers.clear()
    assert (
        logged_in.post(
            f"/api/heartbeats/{mid}", headers={"Authorization": "Bearer " + token}
        ).status_code
        == 204
    )
    with database() as db:
        assert db.get(Monitor, mid).heartbeat_at is not None


def test_secrets_encrypted_and_never_returned(logged_in, database):
    secret = "unit-test-private-value"
    response = create(
        logged_in,
        "http",
        config={"url": "http://127.0.0.1:65534/"},
        secrets={"bearer": secret, "headers": {"X-Private": secret}},
    )
    assert response.status_code == 201
    assert secret not in response.text
    assert secret not in logged_in.get("/api/monitors").text
    with database() as db:
        row = db.get(Monitor, response.json()["id"])
        assert secret not in row.credentials
        assert decrypt(row.credentials)["bearer"] == secret


def test_manual_test_never_mutates_production_state(logged_in, database):
    response = create(
        logged_in, "tcp", timeout=0.1, config={"host": "127.0.0.1", "port": 65534}
    )
    assert response.status_code == 201
    mid = response.json()["id"]
    result = logged_in.post(f"/api/monitors/{mid}/test")
    assert result.status_code == 200
    assert result.json()["status"] in {"UP", "DOWN"}
    with database() as db:
        assert db.get(Monitor, mid).state == "UNKNOWN"
        assert db.get(Monitor, mid).last_checked_at is None
        assert db.scalar(select(func.count()).select_from(CheckResult)) == 0
    assert (
        logged_in.patch(f"/api/monitors/{mid}/pause", json={"paused": True}).json()[
            "state"
        ]
        == "PAUSED"
    )
    assert (
        logged_in.patch(f"/api/monitors/{mid}/pause", json={"paused": False}).json()[
            "state"
        ]
        == "UNKNOWN"
    )


def test_dashboard_staleness_and_history_limits(logged_in, database):
    mid = create(logged_in).json()["id"]
    now = time.time()
    with database() as db:
        monitor = db.get(Monitor, mid)
        monitor.state = "UP"
        monitor.last_checked_at = now
        db.add(WorkerLease(id=1, owner="test", last_cycle_at=now, expires_at=now + 30))
        db.commit()
    data = logged_in.get("/api/dashboard").json()
    assert data["worker_status"] == "running" and data["monitors"][0]["state"] == "UP"
    with database() as db:
        db.get(WorkerLease, 1).last_cycle_at = now - 100
        db.commit()
    data = logged_in.get("/api/dashboard").json()
    assert data["monitors"][0]["state"] == "UNKNOWN"
    assert logged_in.get(f"/api/monitors/{mid}/results?limit=1001").status_code == 422


def test_upgrade_preserves_existing_owner_and_session(logged_in):
    from alembic import command
    from alembic.config import Config

    command.downgrade(Config("alembic.ini"), "0001")
    assert logged_in.get("/api/auth/me").status_code == 200
    command.upgrade(Config("alembic.ini"), "head")
    assert logged_in.get("/api/auth/me").json()["role"] == "owner"
    assert logged_in.get("/api/setup/status").json()["initialized"]
    assert logged_in.get("/api/monitors").json() == []


def test_manual_limit_returns_429_before_connection(logged_in, monkeypatch):
    import threading
    from app.monitoring import routes

    response = create(logged_in, "tcp", config={"host": "127.0.0.1", "port": 65534})
    mid = response.json()["id"]
    slots = threading.BoundedSemaphore(1)
    slots.acquire()
    monkeypatch.setattr(routes, "manual_slots", slots)
    try:
        assert logged_in.post(f"/api/monitors/{mid}/test").status_code == 429
    finally:
        slots.release()

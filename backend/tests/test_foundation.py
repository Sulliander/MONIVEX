import time
from concurrent.futures import ThreadPoolExecutor
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from app.models import AuditEvent, Installation, Session, User
from app.security import digest


def test_setup_requires_secret_and_origin(client, payload):
    assert client.get("/api/setup/status").json() == {"initialized": False}
    assert client.post("/api/setup", json=payload).status_code == 403
    assert (
        client.post(
            "/api/setup",
            json=payload,
            headers={"Origin": "https://other.invalid", "X-Setup-Token": "s" * 48},
        ).status_code
        == 403
    )
    assert client.get("/api/auth/me").status_code == 401


def test_single_initialization(initialized, payload, database):
    assert initialized.get("/api/setup/status").json()["initialized"]
    assert (
        initialized.post(
            "/api/setup", json=payload, headers={"X-Setup-Token": "s" * 48}
        ).status_code
        == 409
    )
    with database() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(User)).password_hash.startswith("$argon2id$")
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_parallel_initialization(client, payload, database):
    def create(_):
        return client.post(
            "/api/setup", json=payload, headers={"X-Setup-Token": "s" * 48}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(create, range(2))) == [201, 409]
    with database() as db:
        assert db.scalar(select(func.count()).select_from(Installation)) == 1
        assert db.scalar(select(func.count()).select_from(User)) == 1


def test_validation_redacts_secrets(client, payload):
    payload["password"] = "short"
    response = client.post(
        "/api/setup", json=payload, headers={"X-Setup-Token": "s" * 48}
    )
    assert response.status_code == 422
    assert "short" not in response.text
    payload["password"] = "long-enough-password"
    payload["timezone"] = "Unknown/Invalid"
    assert client.post("/api/setup", json=payload).status_code == 422


def test_login_session_and_csrf(logged_in, database):
    assert logged_in.get("/api/auth/me").json()["role"] == "owner"
    assert logged_in.get("/api/installation").json()["timezone"] == "Europe/Warsaw"
    assert logged_in.get("/api/dashboard").json()["worker_status"] == "stale"
    cookie = logged_in.cookies.get("monivex_session")
    with database() as db:
        assert db.get(Session, digest(cookie)) is not None
        assert db.get(Session, cookie) is None
    assert (
        logged_in.post("/api/auth/logout", headers={"X-CSRF-Token": "bad"}).status_code
        == 403
    )
    assert (
        logged_in.post(
            "/api/auth/logout", headers={"Origin": "https://other.invalid"}
        ).status_code
        == 403
    )
    assert logged_in.post("/api/auth/logout").status_code == 204
    logged_in.cookies.set("monivex_session", cookie, path="/api")
    assert logged_in.get("/api/auth/me").status_code == 401


def test_login_errors_and_limit(initialized, payload):
    for _ in range(10):
        assert (
            initialized.post(
                "/api/auth/login", json={"username": "missing", "password": "wrong"}
            ).status_code
            == 401
        )
    assert initialized.post("/api/auth/login", json=payload).status_code == 429


def test_cookie_policy(initialized, payload, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("MONIVEX_COOKIE_SECURE", "true")
    get_settings.cache_clear()
    response = initialized.post("/api/auth/login", json=payload)
    cookie = response.headers["set-cookie"]
    for expected in ["HttpOnly", "Secure", "SameSite=strict", "Path=/api"]:
        assert expected in cookie
    assert "no-store" == response.headers["cache-control"]
    get_settings.cache_clear()


def test_expired_session(logged_in, database):
    with database() as db:
        row = db.scalar(select(Session))
        row.expires_at = int(time.time()) - 1
        db.commit()
    assert logged_in.get("/api/auth/me").status_code == 401


def test_password_change_revokes_sessions(logged_in, payload, database):
    assert (
        logged_in.post(
            "/api/auth/password",
            json={"current_password": "wrong", "new_password": "new-long-password"},
        ).status_code
        == 400
    )
    assert (
        logged_in.post(
            "/api/auth/password",
            json={
                "current_password": payload["password"],
                "new_password": "new-long-password",
            },
        ).status_code
        == 204
    )
    assert logged_in.get("/api/auth/me").status_code == 401
    assert logged_in.post("/api/auth/login", json=payload).status_code == 401
    payload["password"] = "new-long-password"
    assert logged_in.post("/api/auth/login", json=payload).status_code == 200
    with database() as db:
        assert db.scalar(select(func.count()).select_from(Session)) == 1


def test_logout_all(logged_in):
    assert logged_in.post("/api/auth/logout-all").status_code == 204
    assert logged_in.get("/api/auth/me").status_code == 401


def test_migrations_repeat_and_schema(client, database):
    command.upgrade(Config("alembic.ini"), "head")
    assert client.get("/api/health/ready").status_code == 200
    with database() as db:
        assert db.connection().exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert db.connection().exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    command.downgrade(Config("alembic.ini"), "base")
    command.upgrade(Config("alembic.ini"), "head")
    assert client.get("/api/health/ready").status_code == 200

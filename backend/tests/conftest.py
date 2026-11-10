import os
import tempfile
import time
from types import SimpleNamespace
from pathlib import Path
import pytest

# Import the app only after configuration. Each test gets its own migrated database.
os.environ["MONIVEX_DATABASE_URL"] = "sqlite:///" + str(
    Path(tempfile.gettempdir()) / "monivex-test-placeholder.db"
)
os.environ["MONIVEX_SETUP_TOKEN"] = "s" * 48
os.environ["MONIVEX_COOKIE_SECURE"] = "false"
os.environ["MONIVEX_PUBLIC_ORIGIN"] = "http://testserver"
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from app.config import get_settings
from app.db import get_db, make_engine
from app.main import app


@pytest.fixture
def database(tmp_path):
    os.environ["MONIVEX_DATABASE_URL"] = "sqlite:///" + str(tmp_path / "test.db")
    os.environ["MONIVEX_ALLOWED_NETWORKS"] = "127.0.0.0/8,::1/128"
    from cryptography.fernet import Fernet

    os.environ["MONIVEX_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = make_engine(get_settings().database_url)
    factory = sessionmaker(engine, expire_on_commit=False)

    def override():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override
    yield factory
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def client(database):
    with TestClient(app, headers={"Origin": "http://testserver"}) as client:
        yield client


@pytest.fixture
def payload():
    return {
        "username": "owner",
        "password": "a-long-password-123!",
        "installation_name": "MONIVEX test",
        "timezone": "Europe/Warsaw",
    }


@pytest.fixture
def initialized(client, payload):
    assert (
        client.post(
            "/api/setup", json=payload, headers={"X-Setup-Token": "s" * 48}
        ).status_code
        == 201
    )
    return client


@pytest.fixture
def logged_in(initialized, payload):
    result = initialized.post(
        "/api/auth/login", json={k: payload[k] for k in ["username", "password"]}
    )
    assert result.status_code == 200
    initialized.headers["X-CSRF-Token"] = result.json()["csrf_token"]
    return initialized


@pytest.fixture
def clock(monkeypatch):
    now = [int(time.time())]
    fake = SimpleNamespace(time=lambda: now[0])
    monkeypatch.setattr("app.auth.routes.time", fake)
    monkeypatch.setattr("app.auth.totp.time", fake)
    monkeypatch.setattr("app.security.time", fake)
    return now

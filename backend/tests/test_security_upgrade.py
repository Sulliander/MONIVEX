"""Verify an actual 0.3 schema upgrade and a fresh API process on persisted state."""

import json
import os
import subprocess
import sys
import time
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from app.auth.totp import hotp
from app.models import Session
from app.security import digest
from test_account_security import enable, login


def test_upgrade_keeps_old_cookie_csrf_accounts_monitors_and_history(
    client, database, payload
):
    config = Config("alembic.ini")
    command.downgrade(config, "0003")
    from app.security import hasher

    with database() as db:
        c = db.connection()
        c.exec_driver_sql(
            "INSERT INTO installation (id,name,timezone,created_at) VALUES (1,'Existing','Europe/Warsaw',1)"
        )
        c.exec_driver_sql(
            "INSERT INTO users (id,username,password_hash,role,created_at) VALUES (1,?,?, 'owner',1)",
            (payload["username"], hasher.hash(payload["password"])),
        )
        c.exec_driver_sql(
            "INSERT INTO sessions (token_hash,user_id,csrf_hash,expires_at) VALUES (?,1,?,?)",
            (digest("old-cookie"), digest("old-csrf"), int(time.time()) + 3600),
        )
        c.exec_driver_sql(
            "INSERT INTO monitors (id,name,kind,config,interval,timeout,failure_threshold,recovery_threshold,paused,state,failure_count,recovery_count,next_check_at,created_at,revision,priority) VALUES (1,'Existing','heartbeat','{}',60,5,1,1,0,'UP',0,0,1,1,1,'normal')"
        )
        c.exec_driver_sql(
            "INSERT INTO check_results (id,monitor_id,checked_at,status,state,duration_ms,message) VALUES (1,1,1,'UP','UP',1,'Existing history')"
        )
        c.exec_driver_sql(
            "INSERT INTO incidents (id,monitor_id,started_at,ended_at,cause,resolution) VALUES (1,1,1,2,'Existing incident','recovered')"
        )
        db.commit()
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    client.cookies.set("monivex_session", "old-cookie", path="/api")
    client.headers["X-CSRF-Token"] = "old-csrf"
    assert client.get("/api/auth/me").json()["username"] == payload["username"]
    sessions = client.get("/api/auth/sessions").json()
    assert (
        len(sessions) == 1 and sessions[0]["id"] and sessions[0]["created_at"] is None
    )
    assert client.get("/api/monitors").json()[0]["name"] == "Existing"
    with database() as db:
        c = db.connection()
        assert (
            c.exec_driver_sql("SELECT message FROM check_results WHERE id=1").scalar()
            == "Existing history"
        )
        assert (
            c.exec_driver_sql("SELECT cause FROM incidents WHERE id=1").scalar()
            == "Existing incident"
        )
        assert not c.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    assert client.post("/api/auth/logout").status_code == 204


def test_new_api_process_keeps_challenge_and_recovery_state(
    logged_in, payload, database, clock
):
    # The child gets no dependency overrides or shared Python objects.
    _, codes = enable(logged_in, payload, clock)
    login(logged_in, payload)
    challenge = logged_in.cookies.get("monivex_login")
    script = """
import json,sys
from fastapi.testclient import TestClient
from app.main import app
value=json.load(sys.stdin)
with TestClient(app, headers={"Origin":"http://testserver"}) as client:
    client.cookies.set("monivex_login",value["challenge"],path="/api/auth")
    assert client.get("/api/auth/me").status_code == 401
    result=client.post("/api/auth/login/verify",json={"code":value["code"]})
    assert result.status_code == 200
    assert client.get("/api/auth/security").json()["recovery_codes_remaining"] == 9
    assert client.get("/api/auth/me").json()["two_factor_enabled"]
print("restart-ok")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps({"challenge": challenge, "code": codes[0]}),
        text=True,
        capture_output=True,
        env=os.environ.copy(),
        timeout=30,
    )
    assert result.returncode == 0, (
        "Nowy proces API nie odtworzył stanu uwierzytelniania."
    )
    assert result.stdout.strip() == "restart-ok"
    with database() as db:
        assert len(db.scalars(select(Session)).all()) == 1


def test_totp_replay_guard_persists_in_new_process(logged_in, payload, database, clock):
    secret, _ = enable(logged_in, payload, clock)
    login(logged_in, payload)
    code = hotp(secret, clock[0] // 30)
    assert (
        logged_in.post("/api/auth/login/verify", json={"code": code}).status_code == 200
    )
    login(logged_in, payload)
    script = """
import json,sys
from fastapi.testclient import TestClient
from app.main import app
value=json.load(sys.stdin)
with TestClient(app,headers={"Origin":"http://testserver"}) as client:
    client.cookies.set("monivex_login",value["challenge"],path="/api/auth")
    assert client.post("/api/auth/login/verify",json={"code":value["code"]}).status_code == 400
    assert client.get("/api/auth/me").status_code == 401
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        input=json.dumps(
            {"challenge": logged_in.cookies.get("monivex_login"), "code": code}
        ),
        text=True,
        capture_output=True,
        env=os.environ.copy(),
        timeout=30,
    )
    assert result.returncode == 0, (
        "Ochrona przed ponownym użyciem TOTP nie przetrwała restartu API."
    )

import base64
import time
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from app.auth.totp import hotp, matching_step, unseal
from app.main import app
from app.models import (
    AuditEvent,
    Installation,
    LoginChallenge,
    RecoveryCode,
    Session,
    User,
)
from app.security import digest, hasher


def enable(client, payload, clock):
    setup = client.post(
        "/api/auth/2fa/setup", json={"current_password": payload["password"]}
    )
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    qr = base64.b64decode(setup.json()["qr_data_url"].split(",")[1])
    assert b"<svg" in qr
    result = client.post(
        "/api/auth/2fa/enable",
        json={
            "current_password": payload["password"],
            "code": hotp(secret, clock[0] // 30),
        },
    )
    assert result.status_code == 200, result.text
    client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
    clock[0] += 30
    return secret, result.json()["recovery_codes"]


def login(client, payload):
    return client.post(
        "/api/auth/login",
        json={"username": payload["username"], "password": payload["password"]},
    )


def test_rfc_totp_vectors_and_replay_window():
    secret = base64.b32encode(b"12345678901234567890").decode()
    for timestamp, expected in [
        (59, "94287082"),
        (1111111109, "07081804"),
        (1111111111, "14050471"),
        (1234567890, "89005924"),
        (2000000000, "69279037"),
        (20000000000, "65353130"),
    ]:
        assert hotp(secret, timestamp // 30, digits=8) == expected
    code = hotp(secret, 100)
    assert matching_step(secret, code, now=3000) == 100
    assert matching_step(secret, code, last_step=100, now=3000) is None
    assert matching_step(secret, code, now=3030) == 100
    assert matching_step(secret, code, now=3060) is None
    assert matching_step(secret, "１２３４５６", now=3000) is None


def test_enrollment_confirmation_encryption_and_redaction(
    logged_in, payload, database, clock
):
    old_cookie = logged_in.cookies.get("monivex_session")
    setup = logged_in.post(
        "/api/auth/2fa/setup", json={"current_password": payload["password"]}
    ).json()
    with database() as db:
        user = db.scalar(select(User))
        assert not user.totp_secret
        assert setup["secret"] not in user.totp_pending_secret
        assert unseal(user.totp_pending_secret) == setup["secret"]
    assert not logged_in.get("/api/auth/security").json()["two_factor_enabled"]
    result = logged_in.post(
        "/api/auth/2fa/enable",
        json={"current_password": payload["password"], "code": "invalid"},
    )
    assert result.status_code == 400
    result = logged_in.post(
        "/api/auth/2fa/enable",
        json={
            "current_password": payload["password"],
            "code": hotp(setup["secret"], clock[0] // 30),
        },
    )
    assert result.status_code == 200
    codes = result.json()["recovery_codes"]
    assert len(codes) == len(set(codes)) == 10
    with database() as db:
        assert db.get(Session, digest(old_cookie)) is None
        user = db.scalar(select(User))
        assert user.totp_secret != setup["secret"]
        assert user.totp_pending_secret is None
        rows = db.scalars(select(RecoveryCode)).all()
        assert len(rows) == 10
        assert all(
            row.code_hash not in codes and len(row.code_hash) == 64 for row in rows
        )
        assert not any(
            setup["secret"] in event.action for event in db.scalars(select(AuditEvent))
        )
    for url in [
        "/api/auth/me",
        "/api/auth/security",
        "/api/auth/events",
        "/api/auth/sessions",
    ]:
        response = logged_in.get(url)
        assert setup["secret"] not in response.text
        assert all(code not in response.text for code in codes)
    assert logged_in.cookies.get("monivex_session") != old_cookie


def test_password_only_cannot_create_full_2fa_session(
    logged_in, payload, database, clock
):
    secret, _ = enable(logged_in, payload, clock)
    result = login(logged_in, payload)
    assert result.json() == {"two_factor_required": True}
    assert "csrf_token" not in result.json()
    assert logged_in.get("/api/auth/me").status_code == 401
    with database() as db:
        assert db.scalar(select(func.count()).select_from(Session)) == 0
        assert db.scalar(select(func.count()).select_from(LoginChallenge)) == 1
    response = logged_in.post(
        "/api/auth/login/verify", json={"code": hotp(secret, clock[0] // 30)}
    )
    assert response.status_code == 200
    assert logged_in.get("/api/auth/me").status_code == 200
    assert (
        logged_in.post(
            "/api/auth/login/verify", json={"code": hotp(secret, clock[0] // 30)}
        ).status_code
        == 401
    )


def test_parallel_totp_accepts_once(logged_in, payload, clock):
    secret, _ = enable(logged_in, payload, clock)
    clients = [
        TestClient(app, headers={"Origin": "http://testserver"}) for _ in range(2)
    ]
    for client in clients:
        assert login(client, payload).json()["two_factor_required"]
    code = hotp(secret, clock[0] // 30)
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(
            pool.map(
                lambda c: c.post(
                    "/api/auth/login/verify", json={"code": code}
                ).status_code,
                clients,
            )
        )
    assert sorted(statuses) == [200, 400]
    for client in clients:
        client.close()


def test_recovery_single_use_and_revokes_other_sessions(
    logged_in, payload, database, clock
):
    _, codes = enable(logged_in, payload, clock)
    old_cookie = logged_in.cookies.get("monivex_session")
    client = TestClient(app, headers={"Origin": "http://testserver"})
    login(client, payload)
    result = client.post("/api/auth/login/verify", json={"code": codes[0].upper()})
    assert result.status_code == 200
    assert logged_in.get("/api/auth/me").status_code == 401
    with database() as db:
        assert db.get(Session, digest(old_cookie)) is None
        assert db.scalar(select(func.count()).select_from(RecoveryCode)) == 9
    login(client, payload)
    assert (
        client.post("/api/auth/login/verify", json={"code": codes[0]}).status_code
        == 400
    )
    client.close()


def test_parallel_recovery_accepts_once(logged_in, payload, clock, database):
    _, codes = enable(logged_in, payload, clock)
    clients = [
        TestClient(app, headers={"Origin": "http://testserver"}) for _ in range(2)
    ]
    for client in clients:
        login(client, payload)
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(
            pool.map(
                lambda c: c.post(
                    "/api/auth/login/verify", json={"code": codes[0]}
                ).status_code,
                clients,
            )
        )
    assert sorted(statuses) == [200, 401]  # Recovery also cancels all other challenges.
    with database() as db:
        assert db.scalar(select(func.count()).select_from(RecoveryCode)) == 9
    for client in clients:
        client.close()


def test_challenge_expiry_cancel_and_attempt_limit(logged_in, payload, clock, database):
    enable(logged_in, payload, clock)
    login(logged_in, payload)
    clock[0] += 301
    assert (
        logged_in.post("/api/auth/login/verify", json={"code": "123456"}).status_code
        == 401
    )
    login(logged_in, payload)
    for _ in range(5):
        assert (
            logged_in.post("/api/auth/login/verify", json={"code": "bad"}).status_code
            == 400
        )
    assert (
        logged_in.post("/api/auth/login/verify", json={"code": "bad"}).status_code
        == 401
    )
    login(logged_in, payload)
    assert logged_in.post("/api/auth/login/cancel").status_code == 204
    with database() as db:
        assert db.scalar(select(func.count()).select_from(LoginChallenge)) == 0
    assert logged_in.get("/api/auth/me").status_code == 401


def test_setup_expires_and_old_secret_is_invalid(logged_in, payload, clock):
    first = logged_in.post(
        "/api/auth/2fa/setup", json={"current_password": payload["password"]}
    ).json()["secret"]
    second = logged_in.post(
        "/api/auth/2fa/setup", json={"current_password": payload["password"]}
    ).json()["secret"]
    assert first != second
    assert (
        logged_in.post(
            "/api/auth/2fa/enable",
            json={
                "current_password": payload["password"],
                "code": hotp(first, clock[0] // 30),
            },
        ).status_code
        == 400
    )
    clock[0] += 601
    assert (
        logged_in.post(
            "/api/auth/2fa/enable",
            json={
                "current_password": payload["password"],
                "code": hotp(second, clock[0] // 30),
            },
        ).status_code
        == 409
    )


def test_regeneration_requires_fresh_factors_and_rotates_session(
    logged_in, payload, database, clock
):
    secret, old_codes = enable(logged_in, payload, clock)
    old_cookie = logged_in.cookies.get("monivex_session")
    assert (
        logged_in.post(
            "/api/auth/2fa/recovery-codes",
            json={"current_password": "wrong", "code": old_codes[0]},
        ).status_code
        == 400
    )
    assert (
        logged_in.post(
            "/api/auth/2fa/recovery-codes",
            json={"current_password": payload["password"]},
        ).status_code
        == 400
    )
    result = logged_in.post(
        "/api/auth/2fa/recovery-codes",
        json={
            "current_password": payload["password"],
            "code": hotp(secret, clock[0] // 30),
        },
    )
    assert result.status_code == 200
    assert set(old_codes).isdisjoint(result.json()["recovery_codes"])
    logged_in.headers["X-CSRF-Token"] = result.json()["csrf_token"]
    with database() as db:
        assert db.get(Session, digest(old_cookie)) is None
        assert db.scalar(select(func.count()).select_from(RecoveryCode)) == 10
    assert (
        logged_in.post(
            "/api/auth/2fa/disable",
            json={
                "current_password": payload["password"],
                "code": hotp(secret, clock[0] // 30),
            },
        ).status_code
        == 400
    )
    assert (
        logged_in.post(
            "/api/auth/2fa/disable",
            json={"current_password": payload["password"], "code": old_codes[0]},
        ).status_code
        == 400
    )


def test_disable_requires_password_and_factor(logged_in, payload, database, clock):
    _, codes = enable(logged_in, payload, clock)
    assert (
        logged_in.post(
            "/api/auth/2fa/disable", json={"current_password": payload["password"]}
        ).status_code
        == 400
    )
    result = logged_in.post(
        "/api/auth/2fa/disable",
        json={"current_password": payload["password"], "code": codes[0]},
    )
    assert result.status_code == 200
    logged_in.headers["X-CSRF-Token"] = result.json()["csrf_token"]
    assert not logged_in.get("/api/auth/security").json()["two_factor_enabled"]
    with database() as db:
        user = db.scalar(select(User))
        assert user.totp_secret is None
        assert db.scalar(select(func.count()).select_from(RecoveryCode)) == 0
    assert login(logged_in, payload).json()["two_factor_required"] is False


def test_password_change_requires_factor_and_invalidates_challenges(
    logged_in, payload, database, clock
):
    _, codes = enable(logged_in, payload, clock)
    other = TestClient(app, headers={"Origin": "http://testserver"})
    login(other, payload)
    data = {
        "current_password": payload["password"],
        "new_password": "new-long-password",
    }
    assert logged_in.post("/api/auth/password", json=data).status_code == 400
    assert (
        logged_in.post(
            "/api/auth/password", json={**data, "code": codes[0]}
        ).status_code
        == 204
    )
    assert logged_in.get("/api/auth/me").status_code == 401
    assert (
        other.post("/api/auth/login/verify", json={"code": codes[1]}).status_code == 401
    )
    with database() as db:
        assert db.scalar(select(func.count()).select_from(Session)) == 0
        assert db.scalar(select(User)).totp_secret is not None
    other.close()


def test_policy_requires_owner_enrollment_and_does_not_lock_out_admin(
    logged_in, payload, database, clock
):
    data = {"current_password": payload["password"], "require_admin_totp": True}
    assert logged_in.put("/api/auth/policy", json=data).status_code == 409
    _, codes = enable(logged_in, payload, clock)
    with database() as db:
        db.add(
            User(
                username="admin",
                password_hash=hasher.hash(payload["password"]),
                role="administrator",
                created_at=clock[0],
            )
        )
        db.commit()
    other = TestClient(app, headers={"Origin": "http://testserver"})
    result = login(other, {**payload, "username": "admin"})
    other.headers["X-CSRF-Token"] = result.json()["csrf_token"]
    assert other.get("/api/dashboard").status_code == 200
    assert (
        logged_in.put("/api/auth/policy", json={**data, "code": codes[0]}).status_code
        == 200
    )
    assert other.get("/api/auth/me").json()["setup_required"] is True
    assert other.get("/api/dashboard").status_code == 403
    assert other.get("/api/monitors").status_code == 403
    assert other.get("/api/auth/security").status_code == 200
    assert (
        other.put(
            "/api/auth/policy", json={**data, "require_admin_totp": False}
        ).status_code
        == 403
    )
    enable(other, payload, clock)
    assert other.get("/api/dashboard").status_code == 200
    assert (
        logged_in.post(
            "/api/auth/2fa/disable",
            json={"current_password": payload["password"], "code": codes[1]},
        ).status_code
        == 409
    )
    other.close()
    with database() as db:
        assert db.get(Installation, 1).require_admin_totp is True


def test_session_list_own_ids_events_and_csrf_bootstrap(logged_in, payload, database):
    second = TestClient(app, headers={"Origin": "http://testserver"})
    login(second, payload)
    rows = logged_in.get("/api/auth/sessions").json()
    assert len(rows) == 2
    assert sum(row["current"] for row in rows) == 1
    assert all("token_hash" not in row and "csrf_hash" not in row for row in rows)
    other = next(row for row in rows if not row["current"])
    assert logged_in.delete("/api/auth/sessions/" + other["id"]).status_code == 204
    assert second.get("/api/auth/me").status_code == 401
    response = logged_in.post("/api/auth/csrf", headers={"X-CSRF-Token": ""})
    assert response.status_code == 200
    assert (
        logged_in.post(
            "/api/auth/csrf", headers={"Origin": "https://evil.invalid"}
        ).status_code
        == 403
    )
    assert logged_in.post("/api/auth/csrf").json() == response.json()
    with database() as db:
        stranger = User(
            username="stranger",
            password_hash=hasher.hash(payload["password"]),
            role="operator",
            created_at=int(time.time()),
        )
        db.add(stranger)
        db.flush()
        foreign_session = Session(
            user_id=stranger.id,
            token_hash=digest("other"),
            csrf_hash=digest("csrf"),
            expires_at=int(time.time()) + 300,
        )
        db.add(foreign_session)
        db.add(
            AuditEvent(
                user_id=stranger.id, action="foreign.event", created_at=int(time.time())
            )
        )
        db.commit()
        foreign_id = foreign_session.id
    assert logged_in.delete("/api/auth/sessions/" + foreign_id).status_code == 404
    assert "foreign.event" not in logged_in.get("/api/auth/events").text
    page = logged_in.get("/api/auth/events?limit=1").json()
    older = logged_in.get(
        "/api/auth/events?limit=1&before=" + str(page["next_before"])
    ).json()
    assert older["items"][0]["id"] < page["items"][0]["id"]
    second.close()


def test_account_rate_limit_across_client_addresses(initialized, payload, monkeypatch):
    import app.auth.routes as routes

    count = [0]

    def address(request):
        count[0] += 1
        return f"192.0.2.{count[0]}"

    monkeypatch.setattr(routes, "client_ip", address)
    for _ in range(10):
        assert (
            initialized.post(
                "/api/auth/login",
                json={"username": payload["username"], "password": "wrong"},
            ).status_code
            == 401
        )
    response = login(initialized, payload)
    assert response.status_code == 429
    assert 1 <= int(response.headers["retry-after"]) <= 900


def test_2fa_requires_origin_and_csrf(logged_in, payload, clock):
    _, codes = enable(logged_in, payload, clock)
    data = {"current_password": payload["password"], "code": codes[0]}
    for endpoint in ["/2fa/disable", "/2fa/recovery-codes", "/password"]:
        body = {**data, "new_password": "new-long-password"}
        assert (
            logged_in.post(
                "/api/auth" + endpoint, json=body, headers={"X-CSRF-Token": "bad"}
            ).status_code
            == 403
        )
        assert (
            logged_in.post(
                "/api/auth" + endpoint,
                json=body,
                headers={"Origin": "https://evil.invalid"},
            ).status_code
            == 403
        )
    login(logged_in, payload)
    assert (
        logged_in.post(
            "/api/auth/login/verify",
            json={"code": codes[0]},
            headers={"Origin": "https://evil.invalid"},
        ).status_code
        == 403
    )


def test_wrong_encryption_key_fails_closed_without_exposing_secret(
    logged_in, payload, clock, monkeypatch
):
    from cryptography.fernet import Fernet
    from app.config import get_settings

    secret, _ = enable(logged_in, payload, clock)
    login(logged_in, payload)
    monkeypatch.setenv("MONIVEX_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()
    response = logged_in.post(
        "/api/auth/login/verify", json={"code": hotp(secret, clock[0] // 30)}
    )
    assert response.status_code == 503
    assert secret not in response.text
    assert logged_in.get("/api/auth/me").status_code == 401


def test_factor_account_limit_survives_new_challenges(logged_in, payload, clock):
    enable(logged_in, payload, clock)
    for _ in range(2):
        login(logged_in, payload)
        for _ in range(5):
            assert (
                logged_in.post(
                    "/api/auth/login/verify", json={"code": "bad"}
                ).status_code
                == 400
            )
    login(logged_in, payload)
    result = logged_in.post("/api/auth/login/verify", json={"code": "bad"})
    assert result.status_code == 429 and result.headers["retry-after"]
    assert logged_in.get("/api/auth/me").status_code == 401


def test_missing_encryption_key_does_not_activate_2fa(
    logged_in, payload, database, monkeypatch
):
    from app.config import get_settings

    monkeypatch.setenv("MONIVEX_ENCRYPTION_KEY", "")
    get_settings.cache_clear()
    response = logged_in.post(
        "/api/auth/2fa/setup", json={"current_password": payload["password"]}
    )
    assert response.status_code == 503
    with database() as db:
        user = db.scalar(select(User))
        assert user.totp_secret is None and user.totp_pending_secret is None
    assert "secret" not in response.json()


def test_logout_all_also_invalidates_pending_factor(logged_in, payload, clock):
    _, codes = enable(logged_in, payload, clock)
    other = TestClient(app, headers={"Origin": "http://testserver"})
    login(other, payload)
    assert logged_in.post("/api/auth/logout-all").status_code == 204
    assert (
        other.post("/api/auth/login/verify", json={"code": codes[0]}).status_code == 401
    )
    other.close()


def test_security_events_exclude_inventory_changes(logged_in, database):
    with database() as db:
        db.add(
            AuditEvent(
                user_id=1, action="resource.created", created_at=int(time.time())
            )
        )
        db.commit()
    assert "resource.created" not in logged_in.get("/api/auth/events").text
    assert "auth.login" in logged_in.get("/api/auth/events").text

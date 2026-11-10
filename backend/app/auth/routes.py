import base64
import io
import secrets
import time
from urllib.parse import urlencode, quote
import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, or_
from ..config import get_settings
from ..db import get_db
from ..models import (
    AuditEvent,
    Installation,
    LoginChallenge,
    RecoveryCode,
    Session,
    User,
)
from ..schemas import LoginInput, PasswordInput
from ..security import (
    CHALLENGE_COOKIE,
    COOKIE,
    DUMMY_HASH,
    client_ip,
    current_session,
    current_user,
    digest,
    hasher,
    limit_attempt,
    needs_totp_setup,
    require_origin,
    verify,
    write_lock,
)
from .totp import matching_step, new_secret, seal, unseal

router = APIRouter(prefix="/api/auth", tags=["Bezpieczeństwo konta"])


class FactorInput(BaseModel):
    code: str = Field(min_length=1, max_length=80)


class ReauthInput(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    code: str = Field(default="", max_length=80)


class PolicyInput(ReauthInput):
    require_admin_totp: bool


class ChangePasswordInput(PasswordInput):
    code: str = Field(default="", max_length=80)


def audit(db, action, user_id=None):
    # Fixed action names only. No password, factor, IP headers or secret payloads.
    db.add(AuditEvent(action=action, user_id=user_id, created_at=int(time.time())))


def revoke(db, user_id):
    db.execute(delete(Session).where(Session.user_id == user_id))
    db.execute(delete(LoginChallenge).where(LoginChallenge.user_id == user_id))


def set_cookie(response, name, token, path, seconds):
    response.set_cookie(
        name,
        token,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="strict",
        max_age=seconds,
        path=path,
    )


def clear_challenge(response):
    response.delete_cookie(
        CHALLENGE_COOKIE,
        path="/api/auth",
        secure=get_settings().cookie_secure,
        httponly=True,
        samesite="strict",
    )


def clear_session(response):
    response.delete_cookie(
        COOKIE,
        path="/api",
        secure=get_settings().cookie_secure,
        httponly=True,
        samesite="strict",
    )


def create_session(db, user, request, response):
    now = int(time.time())
    token = secrets.token_urlsafe(32)
    csrf = digest("csrf:" + token)
    db.execute(delete(Session).where(Session.expires_at <= now))
    db.add(
        Session(
            token_hash=digest(token),
            id=secrets.token_hex(16),
            csrf_hash=digest(csrf),
            user_id=user.id,
            created_at=now,
            expires_at=now + get_settings().session_hours * 3600,
            client_ip=client_ip(request),
            user_agent=request.headers.get("user-agent", "")[:200],
        )
    )
    set_cookie(response, COOKIE, token, "/api", get_settings().session_hours * 3600)
    clear_challenge(response)
    return {"csrf_token": csrf, "two_factor_required": False}


def factor(db, user, code, allow_recovery=True):
    if not user.totp_secret:
        return True
    step = matching_step(unseal(user.totp_secret), code, user.totp_last_step)
    if step is not None:
        user.totp_last_step = step
        return True
    if allow_recovery:
        normalized = code.replace("-", "").replace(" ", "").lower()
        result = db.execute(
            delete(RecoveryCode).where(
                RecoveryCode.user_id == user.id,
                RecoveryCode.code_hash == digest(f"{user.id}:{normalized}"),
            )
        )
        if result.rowcount:
            audit(db, "auth.recovery_used", user.id)
            return True
    return False


def reauthenticate(db, request, session, payload):
    user_id = session.user_id
    limit_attempt(db, "reauth:" + str(user_id))
    write_lock(db)
    # Recheck after obtaining the write lock: another request may have revoked us.
    row = db.get(Session, digest(request.cookies.get(COOKIE, "")))
    if not row or row.expires_at <= int(time.time()):
        raise HTTPException(401, "Sesja wygasła. Zaloguj się ponownie.")
    user = db.get(User, user_id)
    if not verify(payload.current_password, user.password_hash) or not factor(
        db, user, payload.code
    ):
        audit(db, "auth.reauthentication_failed", user_id)
        db.commit()
        raise HTTPException(400, "Nieprawidłowe hasło lub kod uwierzytelniający.")
    return user


def generate_codes(db, user):
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    codes = []
    for _ in range(10):
        raw = secrets.token_hex(
            16
        )  # 128 bits of entropy; SHA-256 is safe for random codes.
        db.add(RecoveryCode(user_id=user.id, code_hash=digest(f"{user.id}:{raw}")))
        codes.append("-".join(raw[i : i + 4] for i in range(0, 32, 4)))
    return codes


@router.post("/login", dependencies=[Depends(require_origin)])
def login(
    payload: LoginInput, request: Request, response: Response, db=Depends(get_db)
):
    limit_attempt(db, "login:" + client_ip(request))
    limit_attempt(db, "account:" + payload.username.lower())
    write_lock(db)
    user = db.scalar(select(User).where(User.username == payload.username))
    if (
        not verify(payload.password, user.password_hash if user else DUMMY_HASH)
        or not user
    ):
        audit(db, "auth.login_failed", user.id if user else None)
        db.commit()
        raise HTTPException(401, "Nieprawidłowy login lub hasło.")
    # A previous full cookie must not survive a new, partial authentication.
    db.execute(
        delete(Session).where(
            Session.token_hash == digest(request.cookies.get(COOKIE, ""))
        )
    )
    db.execute(
        delete(LoginChallenge).where(
            LoginChallenge.token_hash
            == digest(request.cookies.get(CHALLENGE_COOKIE, ""))
        )
    )
    db.execute(
        delete(LoginChallenge).where(LoginChallenge.expires_at <= int(time.time()))
    )
    if user.totp_secret:
        token = secrets.token_urlsafe(32)
        db.add(
            LoginChallenge(
                token_hash=digest(token),
                user_id=user.id,
                expires_at=int(time.time()) + 300,
            )
        )
        clear_session(response)
        set_cookie(response, CHALLENGE_COOKIE, token, "/api/auth", 300)
        db.commit()
        return {"two_factor_required": True}
    result = create_session(db, user, request, response)
    audit(db, "auth.login", user.id)
    db.commit()
    return result


@router.post("/login/verify", dependencies=[Depends(require_origin)])
def login_verify(
    payload: FactorInput, request: Request, response: Response, db=Depends(get_db)
):
    limit_attempt(db, "factor-ip:" + client_ip(request), maximum=30)
    write_lock(db)
    challenge = db.get(
        LoginChallenge, digest(request.cookies.get(CHALLENGE_COOKIE, ""))
    )
    if (
        not challenge
        or challenge.expires_at <= int(time.time())
        or challenge.attempts >= 5
    ):
        if challenge:
            db.delete(challenge)
            db.commit()
        raise HTTPException(401, "Etap weryfikacji wygasł. Zaloguj się ponownie.")
    user_id = challenge.user_id
    db.commit()
    limit_attempt(db, "factor-account:" + str(user_id))
    write_lock(db)
    challenge = db.get(
        LoginChallenge, digest(request.cookies.get(CHALLENGE_COOKIE, ""))
    )
    if (
        not challenge
        or challenge.expires_at <= int(time.time())
        or challenge.attempts >= 5
    ):
        raise HTTPException(401, "Etap weryfikacji wygasł. Zaloguj się ponownie.")
    user = db.get(User, user_id)
    challenge.attempts += 1
    codes_before = db.scalar(
        select(func.count())
        .select_from(RecoveryCode)
        .where(RecoveryCode.user_id == user.id)
    )
    if not factor(db, user, payload.code):
        audit(db, "auth.factor_failed", user.id)
        if challenge.attempts >= 5:
            db.delete(challenge)
        db.commit()
        raise HTTPException(
            400,
            "Nieprawidłowy lub już użyty kod. Po pięciu błędach rozpocznij logowanie ponownie.",
        )
    codes_after = db.scalar(
        select(func.count())
        .select_from(RecoveryCode)
        .where(RecoveryCode.user_id == user.id)
    )
    if codes_after < codes_before:
        revoke(db, user.id)
    else:
        db.delete(challenge)
    result = create_session(db, user, request, response)
    audit(db, "auth.login_2fa", user.id)
    db.commit()
    return result


@router.get("/me")
def me(user=Depends(current_user), db=Depends(get_db)):
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "two_factor_enabled": bool(user.totp_secret),
        "setup_required": needs_totp_setup(db, user),
    }


@router.post("/csrf", dependencies=[Depends(require_origin)])
def csrf(request: Request, session=Depends(current_session), db=Depends(get_db)):
    token = digest("csrf:" + request.cookies[COOKIE])
    session.csrf_hash = digest(token)
    db.commit()
    return {"csrf_token": token}


@router.post("/logout", status_code=204)
def logout(response: Response, session=Depends(current_session), db=Depends(get_db)):
    audit(db, "auth.logout", session.user_id)
    db.delete(session)
    db.commit()
    clear_session(response)
    clear_challenge(response)


@router.post("/logout-all", status_code=204)
def logout_all(
    response: Response, session=Depends(current_session), db=Depends(get_db)
):
    user_id = session.user_id
    write_lock(db)
    revoke(db, user_id)
    audit(db, "auth.logout_all", user_id)
    db.commit()
    clear_session(response)
    clear_challenge(response)


@router.post("/password", status_code=204)
def password(
    payload: ChangePasswordInput,
    request: Request,
    response: Response,
    session=Depends(current_session),
    db=Depends(get_db),
):
    user = reauthenticate(db, request, session, payload)
    user.password_hash = hasher.hash(payload.new_password)
    user.totp_pending_secret = None
    user.totp_pending_expires = None
    revoke(db, user.id)
    audit(db, "auth.password_changed", user.id)
    db.commit()
    clear_session(response)
    clear_challenge(response)


@router.get("/security")
def security(user=Depends(current_user), db=Depends(get_db)):
    return {
        "two_factor_enabled": bool(user.totp_secret),
        "recovery_codes_remaining": db.scalar(
            select(func.count())
            .select_from(RecoveryCode)
            .where(RecoveryCode.user_id == user.id)
        ),
        "require_admin_totp": db.get(Installation, 1).require_admin_totp,
        "can_manage_policy": user.role == "owner",
        "setup_required": needs_totp_setup(db, user),
    }


@router.post("/2fa/setup")
def setup_factor(
    payload: ReauthInput,
    request: Request,
    session=Depends(current_session),
    db=Depends(get_db),
):
    user = reauthenticate(db, request, session, payload)
    if user.totp_secret:
        raise HTTPException(409, "2FA jest już aktywne.")
    secret = new_secret()
    user.totp_pending_secret = seal(secret)
    user.totp_pending_expires = int(time.time()) + 600
    uri = (
        "otpauth://totp/"
        + quote("MONIVEX:" + user.username, safe="")
        + "?"
        + urlencode(
            {
                "secret": secret,
                "issuer": "MONIVEX",
                "algorithm": "SHA1",
                "digits": 6,
                "period": 30,
            }
        )
    )
    image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage)
    output = io.BytesIO()
    image.save(output)
    audit(db, "auth.2fa_setup_started", user.id)
    db.commit()
    # Provisioning is the only response that reveals a new, still inactive secret.
    return {
        "secret": secret,
        "qr_data_url": "data:image/svg+xml;base64,"
        + base64.b64encode(output.getvalue()).decode(),
        "expires_in": 600,
    }


@router.post("/2fa/enable")
def enable_factor(
    payload: ReauthInput,
    request: Request,
    response: Response,
    session=Depends(current_session),
    db=Depends(get_db),
):
    user = reauthenticate(db, request, session, payload)
    if (
        user.totp_secret
        or not user.totp_pending_secret
        or user.totp_pending_expires <= int(time.time())
    ):
        raise HTTPException(
            409,
            "Konfiguracja 2FA wygasła lub została zakończona. Rozpocznij ją ponownie.",
        )
    step = matching_step(unseal(user.totp_pending_secret), payload.code)
    if step is None:
        audit(db, "auth.2fa_confirmation_failed", user.id)
        db.commit()
        raise HTTPException(
            400, "Nieprawidłowy kod. Sprawdź czas w telefonie i spróbuj ponownie."
        )
    user.totp_secret = user.totp_pending_secret
    user.totp_pending_secret = None
    user.totp_pending_expires = None
    user.totp_last_step = step
    codes = generate_codes(db, user)
    revoke(db, user.id)
    result = create_session(db, user, request, response)
    audit(db, "auth.2fa_enabled", user.id)
    db.commit()
    return {**result, "recovery_codes": codes}


@router.post("/2fa/disable")
def disable_factor(
    payload: ReauthInput,
    request: Request,
    response: Response,
    session=Depends(current_session),
    db=Depends(get_db),
):
    user = reauthenticate(db, request, session, payload)
    if needs_totp_policy(db, user):
        raise HTTPException(
            409,
            "Instalacja wymaga 2FA dla administratorów. Najpierw zmień politykę instalacji.",
        )
    user.totp_secret = user.totp_pending_secret = None
    user.totp_pending_expires = None
    user.totp_last_step = -1
    db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    revoke(db, user.id)
    result = create_session(db, user, request, response)
    audit(db, "auth.2fa_disabled", user.id)
    db.commit()
    return result


def needs_totp_policy(db, user):
    return db.get(Installation, 1).require_admin_totp and user.role in {
        "owner",
        "administrator",
    }


@router.post("/2fa/recovery-codes")
def recovery_codes(
    payload: ReauthInput,
    request: Request,
    response: Response,
    session=Depends(current_session),
    db=Depends(get_db),
):
    user = reauthenticate(db, request, session, payload)
    if not user.totp_secret:
        raise HTTPException(409, "Najpierw aktywuj 2FA.")
    codes = generate_codes(db, user)
    revoke(db, user.id)
    result = create_session(db, user, request, response)
    audit(db, "auth.recovery_regenerated", user.id)
    db.commit()
    return {**result, "recovery_codes": codes}


@router.put("/policy")
def policy(
    payload: PolicyInput,
    request: Request,
    session=Depends(current_session),
    db=Depends(get_db),
):
    # Role check before consuming any authentication factor.
    if db.get(User, session.user_id).role != "owner":
        raise HTTPException(
            403, "Tylko właściciel może zmieniać politykę bezpieczeństwa."
        )
    user = reauthenticate(db, request, session, payload)
    if payload.require_admin_totp and not user.totp_secret:
        raise HTTPException(
            409, "Najpierw aktywuj 2FA na własnym koncie i zachowaj kody odzyskiwania."
        )
    db.get(Installation, 1).require_admin_totp = payload.require_admin_totp
    audit(
        db,
        "auth.policy_enabled" if payload.require_admin_totp else "auth.policy_disabled",
        user.id,
    )
    db.commit()
    return {"require_admin_totp": payload.require_admin_totp}


@router.get("/sessions")
def sessions(session=Depends(current_session), db=Depends(get_db)):
    rows = db.scalars(
        select(Session)
        .where(
            Session.user_id == session.user_id, Session.expires_at > int(time.time())
        )
        .order_by(Session.created_at.desc())
    ).all()
    return [
        {
            "id": row.id,
            "current": row.token_hash == session.token_hash,
            "created_at": row.created_at or None,
            "expires_at": row.expires_at,
            "client_ip": row.client_ip,
            "user_agent": row.user_agent,
        }
        for row in rows
    ]


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(
    session_id: str,
    response: Response,
    session=Depends(current_session),
    db=Depends(get_db),
):
    row = db.scalar(
        select(Session).where(
            Session.id == session_id, Session.user_id == session.user_id
        )
    )
    if not row:
        raise HTTPException(404, "Nie znaleziono sesji.")
    if row.token_hash == session.token_hash:
        clear_session(response)
    audit(db, "auth.session_revoked", session.user_id)
    db.delete(row)
    db.commit()


@router.get("/events")
def events(
    limit: int = Query(default=50, ge=1, le=100),
    before: int | None = None,
    user=Depends(current_user),
    db=Depends(get_db),
):
    query = select(AuditEvent).where(
        AuditEvent.user_id == user.id,
        or_(
            AuditEvent.action.like("auth.%"),
            AuditEvent.action == "installation.initialized",
        ),
    )
    if before is not None:
        query = query.where(AuditEvent.id < before)
    rows = db.scalars(query.order_by(AuditEvent.id.desc()).limit(limit)).all()
    return {
        "items": [
            {"id": row.id, "action": row.action, "created_at": row.created_at}
            for row in rows
        ],
        "next_before": rows[-1].id if len(rows) == limit else None,
    }


@router.post("/login/cancel", status_code=204, dependencies=[Depends(require_origin)])
def cancel_login(request: Request, response: Response, db=Depends(get_db)):
    db.execute(
        delete(LoginChallenge).where(
            LoginChallenge.token_hash
            == digest(request.cookies.get(CHALLENGE_COOKIE, ""))
        )
    )
    db.commit()
    clear_challenge(response)

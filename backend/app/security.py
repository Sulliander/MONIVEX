import hashlib
import ipaddress
import secrets
import time
from urllib.parse import urlsplit
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select
from .config import get_settings
from .db import get_db
from .models import Session, User, LoginLimit, Installation

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))
COOKIE = "monivex_session"
CHALLENGE_COOKIE = "monivex_login"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def verify(password, hashed):
    try:
        return hasher.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False


def validate_public_settings():
    settings = get_settings()
    try:
        proxies = [
            ipaddress.ip_network(p.strip())
            for p in settings.trusted_proxies.split(",")
            if p.strip()
        ]
        if any(p.prefixlen == 0 for p in proxies):
            raise ValueError()
    except ValueError:
        raise RuntimeError(
            "Zaufane proxy muszą być konkretnymi adresami lub ograniczonymi podsieciami CIDR."
        ) from None
    if settings.public_profile:
        origin = urlsplit(settings.public_origin)
        if (
            origin.scheme != "https"
            or not origin.hostname
            or origin.username
            or origin.password
            or origin.path
            or origin.query
            or origin.fragment
            or not settings.cookie_secure
            or not settings.encryption_key
            or not proxies
        ):
            raise RuntimeError(
                "Profil publiczny wymaga origin HTTPS bez ścieżki, Secure cookies, klucza szyfrowania i zaufanego proxy."
            )


def client_ip(request: Request):
    peer = request.client.host if request.client else "unknown"
    try:
        address = ipaddress.ip_address(peer)
        trusted = any(
            address in ipaddress.ip_network(p.strip())
            for p in get_settings().trusted_proxies.split(",")
            if p.strip()
        )
        if trusted:
            # Only the configured immediate proxy may supply ONE normalized address.
            return str(
                ipaddress.ip_address(request.headers.get("x-monivex-client-ip", ""))
            )
    except ValueError:
        pass
    return peer


def require_origin(request: Request):
    if request.headers.get("origin") != get_settings().public_origin:
        raise HTTPException(403, "Niedozwolone źródło żądania.")


def write_lock(db):
    # End dependency reads, then serialize security transitions across API processes.
    db.commit()
    if db.bind.dialect.name == "sqlite":
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    db.expire_all()


def limit_attempt(db, key, maximum=10):
    write_lock(db)
    now = int(time.time())
    db.execute(delete(LoginLimit).where(LoginLimit.window_start <= now - 900))
    row = db.get(LoginLimit, digest(key))
    if row and row.attempts >= maximum:
        remaining = max(1, row.window_start + 900 - now)
        db.rollback()
        raise HTTPException(
            429,
            "Zbyt wiele prób. Spróbuj ponownie po zakończeniu blokady.",
            headers={"Retry-After": str(remaining)},
        )
    if row:
        row.attempts += 1
    else:
        db.add(LoginLimit(key=digest(key), attempts=1, window_start=now))
    db.commit()


def needs_totp_setup(db, user):
    installation = db.get(Installation, 1)
    return bool(
        installation
        and installation.require_admin_totp
        and user.role in {"owner", "administrator"}
        and not user.totp_secret
    )


def current_session(request: Request, db=Depends(get_db)):
    token = request.cookies.get(COOKIE, "")
    row = db.get(Session, digest(token)) if token else None
    if not row or row.expires_at <= int(time.time()):
        raise HTTPException(
            401, "Sesja wygasła lub została zakończona. Zaloguj się ponownie."
        )
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_origin(request)
        if request.url.path != "/api/auth/csrf" and not secrets.compare_digest(
            row.csrf_hash, digest(request.headers.get("x-csrf-token", ""))
        ):
            raise HTTPException(
                403, "Nieprawidłowy token bezpieczeństwa. Zaloguj się ponownie."
            )
    user = db.get(User, row.user_id)
    if not user:
        raise HTTPException(401, "Sesja wygasła.")
    if needs_totp_setup(db, user) and not (
        request.url.path.startswith("/api/auth/")
        or request.url.path == "/api/installation"
    ):
        raise HTTPException(
            403, "Skonfiguruj 2FA w ustawieniach konta, aby uzyskać dostęp do panelu."
        )
    return row


def current_user(session=Depends(current_session), db=Depends(get_db)):
    return db.scalar(select(User).where(User.id == session.user_id))


def editor(user=Depends(current_user)):
    if user.role not in {"owner", "administrator", "operator"}:
        raise HTTPException(403, "Brak uprawnień do zarządzania monitoringiem.")
    return user

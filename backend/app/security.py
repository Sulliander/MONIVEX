import hashlib
import secrets
import time
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import delete, select
from .config import get_settings
from .db import get_db
from .models import Session, User, LoginLimit

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))
COOKIE = "monivex_session"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def verify(password, hashed):
    try:
        return hasher.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False


def require_origin(request: Request):
    if request.headers.get("origin") != get_settings().public_origin:
        raise HTTPException(403, "Niedozwolone źródło żądania.")


def limit_attempt(db, key):
    # SQLite serializes this short transaction across all API processes.
    if db.bind.dialect.name == "sqlite":
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    now = int(time.time())
    db.execute(delete(LoginLimit).where(LoginLimit.window_start < now - 900))
    row = db.get(LoginLimit, digest(key))
    if row and row.attempts >= 10:
        db.rollback()
        raise HTTPException(429, "Zbyt wiele prób. Spróbuj ponownie za 15 minut.")
    if row:
        row.attempts += 1
    else:
        db.add(LoginLimit(key=digest(key), attempts=1, window_start=now))
    db.commit()


def current_session(request: Request, db=Depends(get_db)):
    token = request.cookies.get(COOKIE, "")
    row = db.get(Session, digest(token)) if token else None
    if not row or row.expires_at <= int(time.time()):
        raise HTTPException(401, "Zaloguj się, aby kontynuować.")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_origin(request)
        if not secrets.compare_digest(
            row.csrf_hash, digest(request.headers.get("x-csrf-token", ""))
        ):
            raise HTTPException(
                403, "Nieprawidłowy token bezpieczeństwa. Zaloguj się ponownie."
            )
    return row


def current_user(session=Depends(current_session), db=Depends(get_db)):
    user = db.scalar(select(User).where(User.id == session.user_id))
    if not user:
        raise HTTPException(401, "Sesja wygasła.")
    return user

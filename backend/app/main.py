import secrets
import time
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from .monitoring.routes import router as monitoring_router
from .infrastructure.routes import router as infrastructure_router
from .monitoring.management import router as management_router
from .config import get_settings
from .db import get_db
from .models import AuditEvent, Installation, Session, User
from .schemas import LoginInput, PasswordInput, SetupInput
from .security import (
    COOKIE,
    DUMMY_HASH,
    current_session,
    current_user,
    digest,
    hasher,
    limit_attempt,
    require_origin,
    verify,
)


@asynccontextmanager
async def lifespan(app):
    settings = get_settings()
    if settings.setup_token and len(settings.setup_token) < 32:
        raise RuntimeError("Sekret inicjalizacyjny musi mieć co najmniej 32 znaki.")
    from .monitoring.policy import Policy
    from .monitoring.vault import cipher

    Policy()
    if settings.encryption_key:
        cipher()
    yield


app = FastAPI(title="MONIVEX API", version="0.3.0", lifespan=lifespan)


@app.middleware("http")
async def headers(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.exception_handler(StarletteHTTPException)
async def http_error(request, exc):
    detail = {404: "Nie znaleziono zasobu.", 405: "Niedozwolona metoda żądania."}.get(
        exc.status_code, exc.detail
    )
    return JSONResponse(
        status_code=exc.status_code, content={"detail": detail}, headers=exc.headers
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Never echo input: it may contain passwords or the setup secret.
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Sprawdź dane formularza i wymagane pola. Hasło wymaga minimum 12 znaków, a login 3–64 liter, cyfr lub znaków _ . - ."
        },
    )


@app.exception_handler(OperationalError)
async def database_error(request, exc):
    return JSONResponse(
        status_code=503, content={"detail": "Baza danych jest chwilowo niedostępna."}
    )


def audit(db, action, user_id=None):
    db.add(AuditEvent(action=action, user_id=user_id, created_at=int(time.time())))


@app.get("/api/health/ready")
def ready(db=Depends(get_db)):
    db.execute(text("SELECT id FROM installation LIMIT 1"))
    return {"status": "ok", "version": "0.3.0"}


@app.get("/api/setup/status")
def setup_status(db=Depends(get_db)):
    return {"initialized": db.get(Installation, 1) is not None}


@app.post("/api/setup", status_code=201, dependencies=[Depends(require_origin)])
def setup(payload: SetupInput, request: Request, db=Depends(get_db)):
    settings = get_settings()
    limit_attempt(db, "setup:" + (request.client.host if request.client else "unknown"))
    if not settings.setup_token or not secrets.compare_digest(
        request.headers.get("x-setup-token", ""), settings.setup_token
    ):
        raise HTTPException(403, "Nieprawidłowy sekret inicjalizacyjny.")
    hashed = hasher.hash(payload.password)
    try:
        # Singleton primary key is the cross-process initialization lock.
        db.add(
            Installation(
                id=1,
                name=payload.installation_name,
                timezone=payload.timezone,
                created_at=int(time.time()),
            )
        )
        db.flush()
        user = User(
            username=payload.username,
            password_hash=hashed,
            role="owner",
            created_at=int(time.time()),
        )
        db.add(user)
        db.flush()
        audit(db, "installation.initialized", user.id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Instalacja została już skonfigurowana.")
    return {"detail": "Konfiguracja zakończona. Zaloguj się."}


@app.post("/api/auth/login", dependencies=[Depends(require_origin)])
def login(
    payload: LoginInput, request: Request, response: Response, db=Depends(get_db)
):
    limit_attempt(db, "login:" + (request.client.host if request.client else "unknown"))
    user = db.scalar(select(User).where(User.username == payload.username))
    valid = verify(payload.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid:
        audit(db, "auth.login_failed")
        db.commit()
        raise HTTPException(401, "Nieprawidłowy login lub hasło.")
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    now = int(time.time())
    db.execute(delete(Session).where(Session.expires_at <= now))
    db.add(
        Session(
            token_hash=digest(token),
            csrf_hash=digest(csrf),
            user_id=user.id,
            expires_at=now + get_settings().session_hours * 3600,
        )
    )
    audit(db, "auth.login", user.id)
    db.commit()
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="strict",
        max_age=get_settings().session_hours * 3600,
        path="/api",
    )
    return {"csrf_token": csrf}


@app.get("/api/auth/me")
def me(user=Depends(current_user)):
    return {"id": user.id, "username": user.username, "role": user.role}


@app.post("/api/auth/logout", status_code=204)
def logout(response: Response, session=Depends(current_session), db=Depends(get_db)):
    audit(db, "auth.logout", session.user_id)
    db.delete(session)
    db.commit()
    response.delete_cookie(COOKIE, path="/api")


@app.post("/api/auth/logout-all", status_code=204)
def logout_all(response: Response, user=Depends(current_user), db=Depends(get_db)):
    db.execute(delete(Session).where(Session.user_id == user.id))
    audit(db, "auth.logout_all", user.id)
    db.commit()
    response.delete_cookie(COOKIE, path="/api")


@app.post("/api/auth/password", status_code=204)
def password(
    payload: PasswordInput,
    response: Response,
    request: Request,
    user=Depends(current_user),
    db=Depends(get_db),
):
    # current_user already opened a read transaction; end it before the limit transaction.
    user_id = user.id
    db.commit()
    limit_attempt(db, "password:" + str(user_id))
    user = db.get(User, user_id)
    if not verify(payload.current_password, user.password_hash):
        raise HTTPException(400, "Obecne hasło jest nieprawidłowe.")
    user.password_hash = hasher.hash(payload.new_password)
    db.execute(delete(Session).where(Session.user_id == user.id))
    audit(db, "auth.password_changed", user.id)
    db.commit()
    response.delete_cookie(COOKIE, path="/api")


@app.get("/api/installation")
def installation(user=Depends(current_user), db=Depends(get_db)):
    row = db.get(Installation, 1)
    return {
        "name": row.name,
        "timezone": row.timezone,
        "language": "pl",
        "version": "0.3.0",
    }


app.include_router(management_router)
app.include_router(monitoring_router)
app.include_router(infrastructure_router)

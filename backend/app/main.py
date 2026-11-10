import secrets
import time
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from .monitoring.routes import router as monitoring_router
from .infrastructure.routes import router as infrastructure_router
from .monitoring.management import router as management_router
from .config import get_settings
from .db import get_db
from .models import AuditEvent, Installation, User
from .schemas import SetupInput
from .security import (
    current_user,
    hasher,
    limit_attempt,
    require_origin,
    client_ip,
    validate_public_settings,
)
from .auth.routes import router as auth_router


@asynccontextmanager
async def lifespan(app):
    settings = get_settings()
    validate_public_settings()
    if settings.setup_token and len(settings.setup_token) < 32:
        raise RuntimeError("Sekret inicjalizacyjny musi mieć co najmniej 32 znaki.")
    from .monitoring.policy import Policy
    from .monitoring.vault import cipher

    Policy()
    if settings.encryption_key:
        cipher()
    yield


app = FastAPI(
    title="MONIVEX API",
    version="0.4.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


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
    return {"status": "ok", "version": "0.4.0"}


@app.get("/api/setup/status")
def setup_status(db=Depends(get_db)):
    return {"initialized": db.get(Installation, 1) is not None}


@app.post("/api/setup", status_code=201, dependencies=[Depends(require_origin)])
def setup(payload: SetupInput, request: Request, db=Depends(get_db)):
    settings = get_settings()
    limit_attempt(db, "setup:" + client_ip(request))
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


@app.get("/api/installation")
def installation(user=Depends(current_user), db=Depends(get_db)):
    row = db.get(Installation, 1)
    return {
        "name": row.name,
        "timezone": row.timezone,
        "language": "pl",
        "version": "0.4.0",
    }


app.include_router(management_router)
app.include_router(monitoring_router)
app.include_router(infrastructure_router)

app.include_router(auth_router)

import secrets
import threading
import time
from dataclasses import asdict
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select, update, or_
from ..config import get_settings
from ..db import get_db
from ..models import AuditEvent, CheckResult, Incident, Monitor
from ..security import current_user, digest, limit_attempt
from .checks import run_check
from .engine import present_monitor, worker_status
from .policy import PolicyError, validate_target
from .schemas import MonitorInput
from .vault import VaultError, decrypt, encrypt

router = APIRouter(prefix="/api")
manual_slots = threading.BoundedSemaphore(get_settings().manual_concurrency)


def editor(user=Depends(current_user)):
    if user.role not in {"owner", "administrator", "operator"}:
        raise HTTPException(403, "Brak uprawnień do zarządzania monitoringiem.")
    return user


def monitor_or_404(db, monitor_id):
    row = db.get(Monitor, monitor_id)
    if not row:
        raise HTTPException(404, "Nie znaleziono monitora.")
    return row


@router.get("/monitors")
def monitors(user=Depends(current_user), db=Depends(get_db)):
    healthy = worker_status(db)["status"] == "running"
    return [
        present_monitor(m, healthy)
        for m in db.scalars(select(Monitor).order_by(Monitor.id).limit(1000))
    ]


@router.post("/monitors", status_code=201)
async def create_monitor(
    payload: MonitorInput, user=Depends(editor), db=Depends(get_db)
):
    user_id = user.id
    db.commit()
    limit_attempt(db, "monitor_create:" + str(user_id))
    try:
        await validate_target(payload)
        encrypted = encrypt(payload.secrets.reveal())
    except (PolicyError, VaultError) as exc:
        raise HTTPException(422, str(exc)) from None
    except (OSError, TimeoutError):
        raise HTTPException(422, "Nie można zweryfikować adresu celu.") from None
    now = time.time()
    token = secrets.token_urlsafe(32) if payload.kind == "heartbeat" else None
    row = Monitor(
        name=payload.name,
        kind=payload.kind,
        config=payload.config.model_dump(),
        credentials=encrypted,
        interval=payload.interval,
        timeout=payload.timeout,
        failure_threshold=payload.failure_threshold,
        recovery_threshold=payload.recovery_threshold,
        paused=False,
        state="UNKNOWN",
        failure_count=0,
        recovery_count=0,
        next_check_at=now,
        last_checked_at=None,
        heartbeat_at=None,
        heartbeat_hash=digest(token) if token else None,
        created_at=now,
        revision=1,
    )
    db.add(row)
    db.add(AuditEvent(user_id=user_id, action="monitor.created", created_at=int(now)))
    db.commit()
    result = present_monitor(row, False)
    if token:
        result["heartbeat_token"] = token
    return result


class PauseInput(BaseModel):
    paused: bool


@router.patch("/monitors/{monitor_id}/pause")
def pause_monitor(
    monitor_id: int, payload: PauseInput, user=Depends(editor), db=Depends(get_db)
):
    row = monitor_or_404(db, monitor_id)
    # Atomic revision increment fences an in-flight result, including concurrent changes.
    db.execute(
        update(Monitor)
        .where(Monitor.id == monitor_id)
        .values(
            paused=payload.paused,
            state="PAUSED" if payload.paused else "UNKNOWN",
            failure_count=0,
            recovery_count=0,
            revision=Monitor.revision + 1,
            next_check_at=time.time(),
        )
    )
    db.add(
        AuditEvent(
            user_id=user.id,
            action="monitor.paused" if payload.paused else "monitor.resumed",
            created_at=int(time.time()),
        )
    )
    db.commit()
    db.refresh(row)
    return present_monitor(row, False)


@router.post("/monitors/{monitor_id}/test")
async def manual_test(monitor_id: int, user=Depends(editor), db=Depends(get_db)):
    row = monitor_or_404(db, monitor_id)
    if row.kind == "heartbeat":
        raise HTTPException(
            422, "Heartbeat jest sprawdzany na podstawie odebranych sygnałów."
        )
    user_id = user.id
    db.commit()
    limit_attempt(db, "manual_test:" + str(user_id))
    if not manual_slots.acquire(blocking=False):
        raise HTTPException(429, "Trwa zbyt wiele ręcznych testów.")
    try:
        try:
            credentials = decrypt(row.credentials)
        except VaultError as exc:
            raise HTTPException(503, str(exc)) from None
        outcome = await run_check(
            row.kind, row.config, credentials, timeout=row.timeout
        )
    finally:
        manual_slots.release()
    db.add(
        AuditEvent(
            user_id=user_id, action="monitor.manual_test", created_at=int(time.time())
        )
    )
    db.commit()
    return asdict(outcome)


@router.get("/monitors/{monitor_id}/results")
def results(
    monitor_id: int, limit: int = 100, user=Depends(current_user), db=Depends(get_db)
):
    monitor_or_404(db, monitor_id)
    if not 1 <= limit <= 1000:
        raise HTTPException(422, "Limit musi wynosić 1–1000.")
    rows = db.scalars(
        select(CheckResult)
        .where(CheckResult.monitor_id == monitor_id)
        .order_by(CheckResult.id.desc())
        .limit(limit)
    )
    return [
        {
            "id": r.id,
            "checked_at": r.checked_at,
            "status": r.status,
            "state": r.state,
            "duration_ms": r.duration_ms,
            "message": r.message,
        }
        for r in rows
    ]


@router.get("/health/worker")
def worker_health(user=Depends(current_user), db=Depends(get_db)):
    return worker_status(db)


@router.post("/heartbeats/{monitor_id}", status_code=204)
def heartbeat(
    monitor_id: int, request: Request, response: Response, db=Depends(get_db)
):
    row = db.get(Monitor, monitor_id)
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else ""
    if (
        not row
        or row.kind != "heartbeat"
        or not row.heartbeat_hash
        or not secrets.compare_digest(row.heartbeat_hash, digest(token))
    ):
        raise HTTPException(404, "Nie znaleziono heartbeat.")
    now = time.time()
    # Coalesce high-frequency valid signals into at most one write per second.
    if row.heartbeat_at is None or now - row.heartbeat_at >= 1:
        db.execute(
            update(Monitor)
            .where(
                Monitor.id == monitor_id,
                or_(Monitor.heartbeat_at.is_(None), Monitor.heartbeat_at < now - 1),
            )
            .values(heartbeat_at=now, next_check_at=now)
        )
        db.commit()
    response.headers["Cache-Control"] = "no-store"


@router.get("/dashboard")
def dashboard(user=Depends(current_user), db=Depends(get_db)):
    worker = worker_status(db)
    rows = [
        present_monitor(m, worker["status"] == "running")
        for m in db.scalars(select(Monitor).order_by(Monitor.id).limit(1000))
    ]
    active = db.scalars(
        select(Incident)
        .where(Incident.ended_at.is_(None))
        .order_by(Incident.started_at.desc())
        .limit(100)
    )
    return {
        "monitoring_available": True,
        "worker_status": worker["status"],
        "last_cycle_at": worker["last_cycle_at"],
        "monitors": rows,
        "incidents": [
            {
                "id": i.id,
                "monitor_id": i.monitor_id,
                "started_at": i.started_at,
                "cause": i.cause,
            }
            for i in active
        ],
    }

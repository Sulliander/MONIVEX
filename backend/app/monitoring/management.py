import time
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy import case, func, or_, select
from ..db import get_db
from ..models import (
    AuditEvent,
    Incident,
    Monitor,
    Resource,
    monitor_tags,
    resource_tags,
)
from ..security import current_user, digest, editor, limit_attempt
from ..infrastructure.schemas import BulkInput
from ..infrastructure.service import (
    allocate_monitor_id,
    descendants,
    require_revision,
    require_row,
    set_tags,
    tag_map,
    validate_links,
)
from .engine import begin_write, present_monitor, worker_status
from .policy import PolicyError, validate_target
from .schemas import DuplicateInput, Kind, MonitorInput, MonitorUpdate
from .vault import VaultError, encrypt
import secrets

router = APIRouter(prefix="/api/monitors")


def writing(db):
    db.commit()
    begin_write(db)


def audit(db, user_id, action):
    db.add(AuditEvent(user_id=user_id, action=action, created_at=int(time.time())))


def public_monitor(db, row):
    result = present_monitor(row, worker_status(db)["status"] == "running")
    result["tag_ids"] = list(
        db.scalars(
            select(monitor_tags.c.tag_id).where(monitor_tags.c.monitor_id == row.id)
        )
    )
    return result


def state_expression(healthy):
    return case(
        (Monitor.paused.is_(True), "PAUSED"),
        (
            or_(
                not healthy,
                Monitor.last_checked_at.is_(None),
                Monitor.last_checked_at + Monitor.interval + Monitor.timeout + 10
                < time.time(),
            ),
            "UNKNOWN",
        ),
        else_=Monitor.state,
    )


@router.get("/search")
def search(
    q: str = Query(default="", max_length=100),
    kind: Kind | None = None,
    state: str | None = Query(
        default=None, pattern="^(UP|DEGRADED|DOWN|PENDING|UNKNOWN|PAUSED)$"
    ),
    group_id: int | None = None,
    tag_id: int | None = None,
    resource_id: int | None = None,
    sort: str = Query(default="name", pattern="^(name|priority|state|id)$"),
    descending: bool = False,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    user=Depends(current_user),
    db=Depends(get_db),
):
    healthy = worker_status(db)["status"] == "running"
    query = select(Monitor)
    if q:
        query = query.where(Monitor.name.icontains(q, autoescape=True))
    if kind:
        query = query.where(Monitor.kind == kind)
    if state:
        query = query.where(state_expression(healthy) == state)
    if group_id is not None:
        ids = descendants(db, group_id)
        query = query.where(
            or_(
                Monitor.group_id.in_(ids),
                Monitor.resource_id.in_(
                    select(Resource.id).where(Resource.group_id.in_(ids))
                ),
            )
        )
    if tag_id is not None:
        query = query.where(
            or_(
                Monitor.id.in_(
                    select(monitor_tags.c.monitor_id).where(
                        monitor_tags.c.tag_id == tag_id
                    )
                ),
                Monitor.resource_id.in_(
                    select(resource_tags.c.resource_id).where(
                        resource_tags.c.tag_id == tag_id
                    )
                ),
            )
        )
    if resource_id is not None:
        query = query.where(Monitor.resource_id == resource_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    ordering = {
        "name": func.lower(Monitor.name),
        "priority": case(
            (Monitor.priority == "critical", 0),
            (Monitor.priority == "high", 1),
            (Monitor.priority == "normal", 2),
            else_=3,
        ),
        "state": state_expression(healthy),
        "id": Monitor.id,
    }[sort]
    rows = list(
        db.scalars(
            query.order_by(
                ordering.desc() if descending else ordering.asc(), Monitor.id
            )
            .offset(offset)
            .limit(limit)
        )
    )
    links = tag_map(db, monitor_tags, "monitor_id")
    items = []
    for row in rows:
        result = present_monitor(row, healthy)
        result["tag_ids"] = links.get(row.id, [])
        items.append(result)
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@router.post("/bulk")
def bulk(payload: BulkInput, user=Depends(editor), db=Depends(get_db)):
    user_id = user.id
    writing(db)
    rows = list(db.scalars(select(Monitor).where(Monitor.id.in_(payload.monitor_ids))))
    if len(rows) != len(payload.monitor_ids):
        raise HTTPException(
            404, "Nie znaleziono wszystkich monitorów. Nic nie zmieniono."
        )
    for row in rows:
        require_revision(row, payload.revisions[row.id])
    data = payload.model_dump(
        exclude_unset=True, exclude={"operation", "monitor_ids", "revisions"}
    )
    for row in rows:
        merged = {
            key: getattr(row, key)
            for key in [
                "name",
                "kind",
                "interval",
                "timeout",
                "failure_threshold",
                "recovery_threshold",
                "config",
                "group_id",
                "resource_id",
                "priority",
            ]
        }
        merged.update({key: value for key, value in data.items() if key != "tag_ids"})
        try:
            MonitorInput(**merged)
        except ValidationError:
            raise HTTPException(
                422,
                "Wybrane ustawienia są nieprawidłowe dla co najmniej jednego monitora. Nic nie zmieniono.",
            ) from None
        validate_links(
            db, merged["group_id"], merged["resource_id"], data.get("tag_ids", [])
        )
    now = time.time()
    for row in rows:
        if payload.operation == "delete":
            db.delete(row)
        else:
            if payload.operation in {"pause", "resume"}:
                row.paused = payload.operation == "pause"
            else:
                for key, value in data.items():
                    if key != "tag_ids":
                        setattr(row, key, value)
                if "tag_ids" in data:
                    set_tags(db, monitor_tags, "monitor_id", row.id, data["tag_ids"])
            row.state = "PAUSED" if row.paused else "UNKNOWN"
            row.failure_count = row.recovery_count = 0
            row.revision += 1
            row.next_check_at = now
        audit(db, user_id, f"monitor.bulk_{payload.operation}:{row.id}")
    db.commit()
    return {"affected": len(rows)}


@router.get("/{monitor_id}")
def detail(monitor_id: int, user=Depends(current_user), db=Depends(get_db)):
    return public_monitor(db, require_row(db, Monitor, monitor_id))


def origin(url):
    value = urlsplit(url)
    return (
        value.scheme,
        value.hostname,
        value.port or (443 if value.scheme == "https" else 80),
    )


@router.put("/{monitor_id}")
async def update_monitor(
    monitor_id: int, payload: MonitorUpdate, user=Depends(editor), db=Depends(get_db)
):
    user_id = user.id
    db.commit()
    limit_attempt(db, "monitor_update:" + str(user_id))
    try:
        await validate_target(payload)
        replacement = (
            encrypt(payload.secrets.reveal()) if payload.secrets is not None else None
        )
    except (PolicyError, VaultError) as exc:
        raise HTTPException(422, str(exc)) from None
    except (OSError, TimeoutError):
        raise HTTPException(422, "Nie można zweryfikować celu.") from None
    writing(db)
    row = require_row(db, Monitor, monitor_id)
    require_revision(row, payload.revision)
    if payload.kind != row.kind:
        raise HTTPException(
            422,
            "Typ istniejącego monitora jest stały. Utwórz nowy monitor dla innego typu.",
        )
    if (
        row.credentials
        and origin(row.config["url"]) != origin(payload.config.url)
        and payload.secrets is None
        and not payload.clear_credentials
    ):
        raise HTTPException(
            422, "Zmiana originu wymaga usunięcia albo zastąpienia zapisanych sekretów."
        )
    validate_links(db, payload.group_id, payload.resource_id, payload.tag_ids)
    new_config = payload.config.model_dump()
    changed_target = row.config != new_config
    if changed_target:
        for incident in db.scalars(
            select(Incident).where(
                Incident.monitor_id == row.id, Incident.ended_at.is_(None)
            )
        ):
            incident.ended_at = time.time()
            incident.resolution = "configuration_changed"
    for key in [
        "name",
        "interval",
        "timeout",
        "failure_threshold",
        "recovery_threshold",
        "group_id",
        "resource_id",
        "priority",
    ]:
        setattr(row, key, getattr(payload, key))
    row.config = new_config
    if payload.secrets is not None:
        row.credentials = replacement
    elif payload.clear_credentials:
        row.credentials = None
    row.revision += 1
    row.state = "PAUSED" if row.paused else "UNKNOWN"
    row.failure_count = row.recovery_count = 0
    row.next_check_at = time.time()
    set_tags(db, monitor_tags, "monitor_id", row.id, payload.tag_ids)
    audit(db, user_id, f"monitor.updated:{row.id}")
    db.commit()
    return public_monitor(db, row)


@router.post("/{monitor_id}/duplicate", status_code=201)
async def duplicate(
    monitor_id: int, payload: DuplicateInput, user=Depends(editor), db=Depends(get_db)
):
    user_id = user.id
    source = require_row(db, Monitor, monitor_id)
    require_revision(source, payload.revision)
    candidate = MonitorInput(
        name=payload.name,
        kind=source.kind,
        config=source.config,
        interval=source.interval,
        timeout=source.timeout,
        failure_threshold=source.failure_threshold,
        recovery_threshold=source.recovery_threshold,
    )
    db.commit()
    limit_attempt(db, "monitor_create:" + str(user_id))
    try:
        await validate_target(candidate)
    except PolicyError as exc:
        raise HTTPException(422, str(exc)) from None
    except (OSError, TimeoutError):
        raise HTTPException(422, "Nie można zweryfikować celu.") from None
    writing(db)
    db.expire_all()
    source = require_row(db, Monitor, monitor_id)
    require_revision(source, payload.revision)
    now = time.time()
    token = secrets.token_urlsafe(32) if source.kind == "heartbeat" else None
    row = Monitor(
        id=allocate_monitor_id(db),
        name=payload.name,
        kind=source.kind,
        config=source.config,
        credentials=source.credentials if payload.copy_credentials else None,
        interval=source.interval,
        timeout=source.timeout,
        failure_threshold=source.failure_threshold,
        recovery_threshold=source.recovery_threshold,
        group_id=source.group_id,
        resource_id=source.resource_id,
        priority=source.priority,
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
    db.flush()
    ids = list(
        db.scalars(
            select(monitor_tags.c.tag_id).where(monitor_tags.c.monitor_id == source.id)
        )
    )
    set_tags(db, monitor_tags, "monitor_id", row.id, ids)
    audit(db, user_id, f"monitor.duplicated:{row.id}")
    db.commit()
    result = public_monitor(db, row)
    if token:
        result["heartbeat_token"] = token
    return result


@router.delete("/{monitor_id}", status_code=204)
def delete_monitor(
    monitor_id: int, revision: int, user=Depends(editor), db=Depends(get_db)
):
    user_id = user.id
    writing(db)
    row = require_row(db, Monitor, monitor_id)
    require_revision(row, revision)
    db.delete(row)
    audit(db, user_id, f"monitor.deleted:{monitor_id}")
    db.commit()

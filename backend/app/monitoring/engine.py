"""Short serialized transactions, lease fencing, and atomic result/state/incident writes."""

import time
from sqlalchemy import select
from ..models import Monitor, CheckResult, Incident, WorkerLease


def begin_write(db):
    if db.bind.dialect.name == "sqlite":
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")


def renew_lease(factory, owner, duration, now=None):
    now = time.time() if now is None else now
    with factory() as db:
        begin_write(db)
        lease = db.get(WorkerLease, 1)
        if lease and lease.owner != owner and lease.expires_at > now:
            return False
        if not lease:
            lease = WorkerLease(
                id=1, owner=owner, expires_at=now + duration, last_cycle_at=now
            )
            db.add(lease)
        else:
            lease.owner, lease.expires_at, lease.last_cycle_at = (
                owner,
                now + duration,
                now,
            )
        db.commit()
        return True


def transition(monitor, outcome, has_incident):
    if outcome.status == "UNKNOWN":
        monitor.failure_count = monitor.recovery_count = 0
        return "UNKNOWN"
    if outcome.status == "DOWN":
        monitor.failure_count += 1
        monitor.recovery_count = 0
        return (
            "DOWN"
            if has_incident or monitor.failure_count >= monitor.failure_threshold
            else "PENDING"
        )
    monitor.failure_count = 0
    if has_incident:
        monitor.recovery_count += 1
        if monitor.recovery_count < monitor.recovery_threshold:
            return "PENDING"
    monitor.recovery_count = 0
    return outcome.status


def save_result(factory, owner, snapshot, outcome, now=None):
    now = time.time() if now is None else now
    with factory() as db:
        begin_write(db)
        lease = db.get(WorkerLease, 1)
        monitor = db.get(Monitor, snapshot.id)
        if (
            not lease
            or lease.owner != owner
            or lease.expires_at <= now
            or not monitor
            or monitor.paused
            or monitor.last_checked_at != snapshot.last_checked_at
            or monitor.revision != snapshot.revision
        ):
            return False
        # A heartbeat arriving during the check invalidates that snapshot.
        if (
            monitor.kind == "heartbeat"
            and monitor.heartbeat_at != snapshot.heartbeat_at
        ):
            return False
        active = db.scalar(
            select(Incident).where(
                Incident.monitor_id == monitor.id, Incident.ended_at.is_(None)
            )
        )
        state = transition(monitor, outcome, active is not None)
        monitor.state = state
        monitor.last_checked_at = now
        monitor.next_check_at = now + monitor.interval
        db.add(
            CheckResult(
                monitor_id=monitor.id,
                checked_at=now,
                status=outcome.status,
                state=state,
                duration_ms=outcome.duration_ms,
                message=outcome.message,
            )
        )
        if state == "DOWN" and not active:
            db.add(
                Incident(
                    monitor_id=monitor.id,
                    started_at=now,
                    ended_at=None,
                    cause=outcome.message,
                )
            )
        elif state in {"UP", "DEGRADED"} and active:
            active.ended_at = now
        db.commit()
        return True


def worker_status(db, now=None):
    now = time.time() if now is None else now
    lease = db.get(WorkerLease, 1)
    healthy = bool(lease and lease.expires_at > now and now - lease.last_cycle_at < 10)
    return {
        "status": "running" if healthy else "stale",
        "last_cycle_at": lease.last_cycle_at if lease else None,
    }


def present_monitor(monitor, healthy, now=None):
    now = time.time() if now is None else now
    stale = (
        not healthy
        or monitor.last_checked_at is None
        or now - monitor.last_checked_at > monitor.interval + monitor.timeout + 10
    )
    state = "PAUSED" if monitor.paused else "UNKNOWN" if stale else monitor.state
    return {
        "id": monitor.id,
        "name": monitor.name,
        "kind": monitor.kind,
        "config": monitor.config,
        "has_credentials": bool(monitor.credentials),
        "interval": monitor.interval,
        "timeout": monitor.timeout,
        "failure_threshold": monitor.failure_threshold,
        "recovery_threshold": monitor.recovery_threshold,
        "state": state,
        "recorded_state": monitor.state,
        "stale": stale and not monitor.paused,
        "last_checked_at": monitor.last_checked_at,
        "next_check_at": monitor.next_check_at,
        "paused": monitor.paused,
    }

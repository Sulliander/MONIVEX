import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import func, select
from app.models import CheckResult, Incident, Monitor
from app.monitoring.checks import Outcome, run_check
from app.monitoring.engine import (
    renew_lease,
    save_result,
    present_monitor,
    worker_status,
)
from app.monitoring.schemas import CheckConfig
from app.worker import Worker


def add_monitor(factory, kind="tcp", **overrides):
    values = dict(
        name="test",
        kind=kind,
        config=CheckConfig(host="127.0.0.1").model_dump(),
        credentials=None,
        interval=10,
        timeout=1,
        failure_threshold=2,
        recovery_threshold=2,
        paused=False,
        state="UNKNOWN",
        failure_count=0,
        recovery_count=0,
        next_check_at=0,
        last_checked_at=None,
        heartbeat_at=None,
        heartbeat_hash=None,
        created_at=time.time(),
        revision=1,
    )
    values.update(overrides)
    with factory() as db:
        row = Monitor(**values)
        db.add(row)
        db.commit()
        return row


def snapshot(factory, monitor_id):
    with factory() as db:
        return db.get(Monitor, monitor_id)


def test_state_transitions_and_single_incident(database):
    m = add_monitor(database)
    assert renew_lease(database, "leader", 300)
    states = []
    for status in ["DOWN", "DOWN", "DOWN", "UP", "DOWN", "UP", "UP"]:
        assert save_result(
            database, "leader", snapshot(database, m.id), Outcome(status, 2, "Test")
        )
        states.append(snapshot(database, m.id).state)
    assert states == ["PENDING", "DOWN", "DOWN", "PENDING", "DOWN", "PENDING", "UP"]
    with database() as db:
        incidents = list(db.scalars(select(Incident)))
        assert len(incidents) == 1 and incidents[0].ended_at is not None
        assert db.scalar(select(func.count()).select_from(CheckResult)) == 7


def test_leader_fencing_replay_pause_and_revision(database):
    m = add_monitor(database)
    assert renew_lease(database, "a", 30, now=100)
    old = snapshot(database, m.id)
    assert not renew_lease(database, "b", 30, now=110)
    assert not save_result(database, "b", old, Outcome("UP", 1, "ok"), now=110)
    assert save_result(database, "a", old, Outcome("UP", 1, "ok"), now=110)
    assert not save_result(database, "a", old, Outcome("UP", 1, "ok"), now=111)
    assert renew_lease(database, "b", 30, now=131)
    assert not save_result(
        database, "a", snapshot(database, m.id), Outcome("DOWN", 1, "bad"), now=132
    )
    stale = snapshot(database, m.id)
    with database() as db:
        row = db.get(Monitor, m.id)
        row.revision += 1
        db.commit()
    assert not save_result(database, "b", stale, Outcome("UP", 1, "ok"), now=132)
    with database() as db:
        row = db.get(Monitor, m.id)
        row.paused = True
        db.commit()
    assert not save_result(
        database, "b", snapshot(database, m.id), Outcome("UP", 1, "ok"), now=132
    )


def test_two_schedulers_race(database):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda owner: renew_lease(database, owner, 30), ["one", "two"])
        )
    assert sum(results) == 1


def test_unknown_and_stale_are_never_green(database):
    m = add_monitor(database)
    assert renew_lease(database, "a", 30)
    assert save_result(database, "a", m, Outcome("UP", 1, "ok"))
    m = snapshot(database, m.id)
    assert present_monitor(m, True)["state"] == "UP"
    assert present_monitor(m, False)["state"] == "UNKNOWN"
    assert present_monitor(m, True, now=m.last_checked_at + 100)["state"] == "UNKNOWN"
    assert save_result(database, "a", m, Outcome("UNKNOWN", 1, "policy"))
    with database() as db:
        assert worker_status(db)["status"] == "running"
    m = snapshot(database, m.id)
    m.paused = True
    assert present_monitor(m, False)["state"] == "PAUSED"


def test_heartbeat_grace_expiry_and_inflight_race(database):
    now = time.time()
    c = CheckConfig(grace_seconds=0).model_dump()

    async def scenario():
        assert (
            await run_check("heartbeat", c, created_at=now, interval=10)
        ).status == "UNKNOWN"
        assert (
            await run_check("heartbeat", c, created_at=now - 20, interval=10)
        ).status == "DOWN"
        assert (
            await run_check("heartbeat", c, heartbeat_at=now, interval=10)
        ).status == "UP"

    asyncio.run(scenario())
    m = add_monitor(database, kind="heartbeat")
    assert renew_lease(database, "a", 30)
    with database() as db:
        db.get(Monitor, m.id).heartbeat_at = now
        db.commit()
    assert not save_result(database, "a", m, Outcome("DOWN", 1, "late"))


def test_worker_concurrency_and_takeover(database, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("MONIVEX_WORKER_CONCURRENCY", "2")
    get_settings.cache_clear()
    for _ in range(5):
        add_monitor(database)

    async def scenario():
        running = 0
        maximum = 0
        gate = asyncio.Event()

        async def slow(*args, **kwargs):
            nonlocal running, maximum
            running += 1
            maximum = max(maximum, running)
            await gate.wait()
            running -= 1
            return Outcome("UP", 1, "ok")

        monkeypatch.setattr("app.worker.run_check", slow)
        worker = Worker(database)
        other = Worker(database)
        assert await worker.tick()
        await asyncio.sleep(0.01)
        assert len(worker.tasks) == 2 and running == 2
        assert not await other.tick()
        assert await worker.tick()
        assert len(worker.tasks) == 2
        gate.set()
        await asyncio.gather(*worker.tasks.values())
        assert maximum == 2
        worker.release()
        assert await other.tick()
        await asyncio.gather(*other.tasks.values())
        other.release()

    asyncio.run(scenario())
    get_settings.cache_clear()

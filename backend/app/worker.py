"""Run with python -m app.worker; the API process is not required."""

import asyncio
import contextlib
import json
import logging
import secrets
import signal
import time
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from .config import get_settings
from .db import SessionLocal
from .models import Monitor, WorkerLease
from .monitoring.checks import Outcome, run_check
from .monitoring.engine import begin_write, renew_lease, save_result
from .monitoring.policy import Policy
from .monitoring.vault import VaultError, cipher, decrypt

log = logging.getLogger("monivex.worker")


class Worker:
    def __init__(self, factory=SessionLocal):
        self.factory = factory
        self.owner = secrets.token_hex(16)
        self.tasks = {}
        self.settings = get_settings()

    def due(self, limit):
        with self.factory() as db:
            return list(
                db.scalars(
                    select(Monitor)
                    .where(
                        Monitor.paused.is_(False),
                        Monitor.next_check_at <= time.time(),
                        Monitor.id.not_in(list(self.tasks)),
                    )
                    .order_by(Monitor.next_check_at, Monitor.id)
                    .limit(limit)
                )
            )

    async def check(self, monitor):
        try:
            try:
                credentials = decrypt(monitor.credentials)
            except VaultError as exc:
                outcome = Outcome("UNKNOWN", 0, str(exc))
            else:
                outcome = await run_check(
                    monitor.kind,
                    monitor.config,
                    credentials,
                    timeout=monitor.timeout,
                    heartbeat_at=monitor.heartbeat_at,
                    created_at=monitor.created_at,
                    interval=monitor.interval,
                )
            await asyncio.to_thread(
                save_result, self.factory, self.owner, monitor, outcome
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Do not log exceptions/URLs/credentials or remote response contents.
            log.error(
                json.dumps(
                    {
                        "event": "check_failed",
                        "monitor_id": monitor.id,
                        "error_type": type(exc).__name__,
                    }
                )
            )

    async def tick(self):
        for key in list(self.tasks):
            if self.tasks[key].done():
                with contextlib.suppress(asyncio.CancelledError):
                    self.tasks.pop(key).result()
        leader = await asyncio.to_thread(
            renew_lease, self.factory, self.owner, self.settings.worker_lease_seconds
        )
        if not leader:
            for task in self.tasks.values():
                task.cancel()
            return False
        capacity = self.settings.worker_concurrency - len(self.tasks)
        if capacity > 0:
            for monitor in await asyncio.to_thread(self.due, capacity):
                self.tasks[monitor.id] = asyncio.create_task(self.check(monitor))
        return True

    async def run(self, stop):
        Policy()  # Fail closed on invalid infrastructure policy.
        if self.settings.encryption_key:
            cipher()
        try:
            while not stop.is_set():
                try:
                    await self.tick()
                except SQLAlchemyError as exc:
                    log.error(
                        json.dumps(
                            {
                                "event": "database_unavailable",
                                "error_type": type(exc).__name__,
                            }
                        )
                    )
                try:
                    await asyncio.wait_for(stop.wait(), 1)
                except TimeoutError:
                    pass
        finally:
            for task in self.tasks.values():
                task.cancel()
            await asyncio.gather(*self.tasks.values(), return_exceptions=True)
            with contextlib.suppress(SQLAlchemyError):
                await asyncio.to_thread(self.release)

    def release(self):
        with self.factory() as db:
            begin_write(db)
            lease = db.get(WorkerLease, 1)
            if lease and lease.owner == self.owner:
                lease.expires_at = 0
                db.commit()


async def main():
    stop = asyncio.Event()
    for sig in [signal.SIGTERM, signal.SIGINT]:
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    await Worker().run(stop)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(main())

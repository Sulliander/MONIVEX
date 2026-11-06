"""Real worker process: networking, restart, durable history, no API needed."""

import contextlib
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from sqlalchemy import func, select
from app.models import CheckResult, Incident, Monitor
from test_monitoring_engine import add_monitor
from app.monitoring.schemas import CheckConfig


def wait_for(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError("Worker did not produce expected state")


def test_worker_process_survives_restart_without_api(database, tmp_path):
    healthy = threading.Event()
    healthy.set()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200 if healthy.is_set() else 503)
            self.end_headers()

        def log_message(self, *args):
            pass

    service = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=service.serve_forever, daemon=True)
    thread.start()
    monitor = add_monitor(
        database,
        kind="http",
        config=CheckConfig(url=f"http://127.0.0.1:{service.server_port}").model_dump(),
        interval=1,
        failure_threshold=1,
        recovery_threshold=1,
    )
    env = os.environ.copy()
    env["MONIVEX_WORKER_LEASE_SECONDS"] = "15"
    log_path = tmp_path / "worker.log"

    def start():
        return subprocess.Popen(
            [sys.executable, "-m", "app.worker"],
            env=env,
            cwd=Path(__file__).parents[1],
            stdout=log,
            stderr=subprocess.STDOUT,
        )

    def state(expected):
        with database() as db:
            return db.get(Monitor, monitor.id).state == expected

    def count():
        with database() as db:
            return db.scalar(select(func.count()).select_from(CheckResult))

    with log_path.open("w") as log:
        process = start()
        try:
            wait_for(lambda: state("UP"))
            healthy.clear()
            wait_for(lambda: state("DOWN"))
            with database() as db:
                assert db.scalar(select(func.count()).select_from(Incident)) == 1
            before = count()
            process.terminate()
            process.wait(timeout=10)
            process = start()
            wait_for(lambda: count() > before)
            with database() as db:
                assert db.scalar(select(func.count()).select_from(Incident)) == 1
            healthy.set()
            wait_for(lambda: state("UP"))
            with database() as db:
                assert db.scalar(select(Incident)).ended_at is not None
        finally:
            if process.poll() is None:
                process.terminate()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    process.wait(timeout=10)
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
            service.shutdown()
            service.server_close()
            thread.join(timeout=2)
    assert "test-secret" not in log_path.read_text()

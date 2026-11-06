"""Destructive-to-availability test: use only on a disposable Compose project."""

import argparse
import json
import os
import subprocess
import time
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(
        description="Sprawdź ciągłość workera podczas zatrzymania testowego API."
    )
    parser.add_argument("--project", required=True)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--url", default="http://localhost:18080")
    args = parser.parse_args()
    for selector in [
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_TLS",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
    ]:
        os.environ.pop(selector, None)
    compose = [
        "docker",
        "--host=unix:///var/run/docker.sock",
        "compose",
        "-p",
        args.project,
        "--env-file",
        args.env_file,
        "-f",
        "compose.yaml",
    ]
    query = """import json; from sqlalchemy import select,func; from app.db import SessionLocal; from app.models import CheckResult,WorkerLease,Monitor; db=SessionLocal(); lease=db.get(WorkerLease,1); print(json.dumps({"results":db.scalar(select(func.count()).select_from(CheckResult)),"owner":lease.owner,"monitors":db.scalar(select(func.count()).select_from(Monitor))})); db.close()"""

    def observed():
        result = subprocess.run(
            compose + ["exec", "-T", "worker", "python", "-c", query],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    before = observed()
    if before["monitors"] < 1:
        raise RuntimeError(
            "Test wymaga monitora utworzonego przez test przeglądarkowy."
        )
    try:
        subprocess.run(compose + ["stop", "api"], check=True, capture_output=True)
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            after = observed()
            if after["results"] > before["results"]:
                assert after["owner"] == before["owner"]
                break
            time.sleep(1)
        else:
            raise AssertionError("Brak nowych wyników przy zatrzymanym API.")
    finally:
        subprocess.run(compose + ["start", "api"], check=True, capture_output=True)
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            with urlopen(args.url + "/api/health/ready", timeout=2) as response:
                assert response.status == 200
            break
        except OSError:
            time.sleep(1)
    else:
        raise AssertionError("API nie wróciło po restarcie.")
    with urlopen(args.url + "/api/setup/status", timeout=3) as response:
        assert json.load(response)["initialized"]
    assert observed()["monitors"] == before["monitors"]
    print(
        "Zaliczone: worker zapisał nowe wyniki bez API; jego dzierżawa i zapisane monitory przetrwały restart API."
    )


if __name__ == "__main__":
    main()

import time
from concurrent.futures import ThreadPoolExecutor
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from app.models import CheckResult, Incident, Monitor, User, WorkerLease
from app.monitoring.checks import Outcome
from app.monitoring.engine import renew_lease, save_result
from app.monitoring.vault import decrypt
from app.infrastructure.service import aggregate
from test_monitoring_engine import add_monitor, snapshot


def monitor(client, name="Monitor", **values):
    payload = {"name": name, "kind": "heartbeat"}
    payload.update(values)
    response = client.post("/api/monitors", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_group_hierarchy_and_cycle_race(logged_in):
    a = logged_in.post("/api/groups", json={"name": "A"}).json()
    b = logged_in.post("/api/groups", json={"name": "B"}).json()
    assert logged_in.post("/api/groups", json={"name": "a"}).status_code == 409

    def move(pair):
        row, parent = pair
        return logged_in.put(
            f"/api/groups/{row['id']}",
            json={
                "name": row["name"],
                "parent_id": parent["id"],
                "revision": row["revision"],
            },
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(move, [(a, b), (b, a)])) == [200, 422]
    rows = logged_in.get("/api/groups").json()
    root = next(r for r in rows if r["parent_id"] is None)
    assert (
        logged_in.delete(
            f"/api/groups/{root['id']}?revision={root['revision']}"
        ).status_code
        == 409
    )
    assert (
        logged_in.put(
            f"/api/groups/{a['id']}", json={"name": "Stale", "revision": 999}
        ).status_code
        == 409
    )


def test_links_filters_and_safe_resource_deletion(logged_in):
    root = logged_in.post("/api/groups", json={"name": "Root"}).json()
    child = logged_in.post(
        "/api/groups", json={"name": "Child", "parent_id": root["id"]}
    ).json()
    tag = logged_in.post("/api/tags", json={"name": "Production"}).json()
    assert tag["name"] == "production"
    assert logged_in.post("/api/tags", json={"name": "PRODUCTION"}).status_code == 409
    resource = logged_in.post(
        "/api/resources",
        json={
            "name": "Host",
            "group_id": child["id"],
            "tag_ids": [tag["id"]],
            "operating_system": "Linux",
        },
    ).json()
    m = monitor(logged_in, resource_id=resource["id"])
    assert (
        logged_in.get(
            f"/api/monitors/search?group_id={root['id']}&tag_id={tag['id']}"
        ).json()["total"]
        == 1
    )
    assert logged_in.get("/api/resources").json()[0]["monitor_count"] == 1
    assert logged_in.delete(f"/api/groups/{child['id']}?revision=1").status_code == 409
    assert (
        logged_in.delete(f"/api/resources/{resource['id']}?revision=1").status_code
        == 204
    )
    detail = logged_in.get(f"/api/monitors/{m['id']}").json()
    assert detail["resource_id"] is None and detail["revision"] > m["revision"]
    assert logged_in.delete(f"/api/tags/{tag['id']}?revision=1").status_code == 204
    assert logged_in.get("/api/monitors/search").json()["total"] == 1


def test_resource_status_and_independent_monitors(logged_in, database):
    resource = logged_in.post("/api/resources", json={"name": "Host"}).json()
    a = monitor(logged_in, "A", resource_id=resource["id"])
    b = monitor(logged_in, "B", resource_id=resource["id"])
    with database() as db:
        for row in db.scalars(select(Monitor)):
            row.state = "UP" if row.id == a["id"] else "DOWN"
            row.last_checked_at = time.time()
        db.add(
            WorkerLease(
                id=1,
                owner="test",
                expires_at=time.time() + 30,
                last_cycle_at=time.time(),
            )
        )
        db.commit()
    rows = logged_in.get("/api/monitors/search").json()["items"]
    assert {r["state"] for r in rows} == {"UP", "DOWN"}
    assert logged_in.get("/api/resources").json()[0]["state"] == "DOWN"
    with database() as db:
        db.get(Monitor, b["id"]).paused = True
        db.commit()
    result = logged_in.get("/api/resources").json()[0]
    assert result["state"] == "UP" and result["paused_count"] == 1
    assert (
        aggregate([]) == "UNKNOWN"
        and aggregate(["PAUSED"]) == "PAUSED"
        and aggregate(["UP", "UNKNOWN"]) == "UNKNOWN"
    )


def test_edit_revisions_and_secret_origin(logged_in, database):
    m = monitor(
        logged_in,
        kind="http",
        config={"url": "http://127.0.0.1:12345/"},
        secrets={"bearer": "test-private"},
    )
    keys = [
        "name",
        "kind",
        "config",
        "interval",
        "timeout",
        "failure_threshold",
        "recovery_threshold",
        "priority",
        "group_id",
        "resource_id",
        "tag_ids",
        "revision",
    ]
    payload = {k: m[k] for k in keys}
    changed = {**payload, "config": {"url": "http://127.0.0.1:12346/"}}
    assert logged_in.put(f"/api/monitors/{m['id']}", json=changed).status_code == 422
    response = logged_in.put(
        f"/api/monitors/{m['id']}", json={**payload, "name": "Renamed"}
    )
    assert response.status_code == 200
    with database() as db:
        assert decrypt(db.get(Monitor, m["id"]).credentials)["bearer"] == "test-private"
    assert logged_in.put(f"/api/monitors/{m['id']}", json=payload).status_code == 409
    updated = {k: response.json()[k] for k in keys}
    updated.update(config={"url": "http://127.0.0.1:12346/"}, clear_credentials=True)
    assert logged_in.put(f"/api/monitors/{m['id']}", json=updated).status_code == 200
    with database() as db:
        assert db.get(Monitor, m["id"]).credentials is None


def test_duplicate_heartbeat_and_explicit_secret_copy(logged_in):
    m = monitor(logged_in)
    response = logged_in.post(
        f"/api/monitors/{m['id']}/duplicate",
        json={"name": "Copy", "revision": m["revision"]},
    )
    assert response.status_code == 201
    copied = response.json()
    assert copied["id"] != m["id"] and copied["heartbeat_token"] != m["heartbeat_token"]
    assert logged_in.get(f"/api/monitors/{copied['id']}/results").json() == []
    source = monitor(
        logged_in,
        "HTTP",
        kind="http",
        config={"url": "http://127.0.0.1:12345/"},
        secrets={"username": "user", "password": "private"},
    )
    clone = logged_in.post(
        f"/api/monitors/{source['id']}/duplicate",
        json={"name": "No secrets", "revision": source["revision"]},
    ).json()
    assert not clone["has_credentials"] and "private" not in str(clone)


def test_bulk_all_or_nothing_and_stale_revision(logged_in, database):
    a = monitor(logged_in, "A")
    b = monitor(logged_in, "B", interval=10, timeout=5)
    payload = {
        "monitor_ids": [a["id"], b["id"]],
        "revisions": {str(a["id"]): a["revision"], str(b["id"]): b["revision"]},
        "operation": "configure",
        "timeout": 15,
    }
    assert logged_in.post("/api/monitors/bulk", json=payload).status_code == 422
    with database() as db:
        assert all(row.timeout == 5 for row in db.scalars(select(Monitor)))
    payload.update(timeout=2, priority="critical")
    assert logged_in.post("/api/monitors/bulk", json=payload).json()["affected"] == 2
    assert logged_in.post("/api/monitors/bulk", json=payload).status_code == 409
    assert all(
        row["priority"] == "critical"
        for row in logged_in.get("/api/monitors/search").json()["items"]
    )


def test_search_literal_wildcards_pagination_and_stale(logged_in):
    for name in ["A%", "B", "C"]:
        monitor(logged_in, name)
    assert logged_in.get("/api/monitors/search?q=%25").json()["total"] == 1
    result = logged_in.get("/api/monitors/search?limit=2&offset=1&sort=name").json()
    assert result["total"] == 3 and [m["name"] for m in result["items"]] == ["B", "C"]
    assert logged_in.get("/api/monitors/search?state=UNKNOWN").json()["total"] == 3
    assert logged_in.get("/api/monitors/search?state=UP").json()["total"] == 0


def test_viewer_permissions(logged_in, database):
    m = monitor(logged_in)
    with database() as db:
        db.scalar(select(User)).role = "viewer"
        db.commit()
    for path, payload in [
        ("/api/groups", {"name": "Group"}),
        ("/api/tags", {"name": "tag"}),
        ("/api/resources", {"name": "Host"}),
        (f"/api/monitors/{m['id']}/duplicate", {"name": "Copy", "revision": 1}),
    ]:
        assert logged_in.post(path, json=payload).status_code == 403
    assert logged_in.delete(f"/api/monitors/{m['id']}?revision=1").status_code == 403
    for path in ["/api/groups", "/api/tags", "/api/resources", "/api/monitors/search"]:
        assert logged_in.get(path).status_code == 200


def test_migration_keeps_results_incidents_and_session(logged_in, database):
    m = monitor(logged_in)
    with database() as db:
        db.add(
            CheckResult(
                monitor_id=m["id"],
                checked_at=time.time(),
                status="DOWN",
                state="DOWN",
                duration_ms=1,
                message="test",
            )
        )
        db.add(
            Incident(
                monitor_id=m["id"], started_at=time.time(), ended_at=None, cause="test"
            )
        )
        db.commit()
    command.downgrade(Config("alembic.ini"), "0002")
    command.upgrade(Config("alembic.ini"), "head")
    with database() as db:
        assert db.scalar(select(func.count()).select_from(CheckResult)) == 1
        assert db.scalar(select(func.count()).select_from(Incident)) == 1
        assert db.get(Monitor, m["id"]).priority == "normal"
    assert logged_in.get("/api/auth/me").status_code == 200


def test_deleted_id_reuse_fences_old_result(database):
    old = add_monitor(database)
    assert renew_lease(database, "worker", 30)
    old = snapshot(database, old.id)
    with database() as db:
        db.delete(db.get(Monitor, old.id))
        db.commit()
    new = add_monitor(database)
    assert new.id == old.id
    assert not save_result(database, "worker", old, Outcome("UP", 1, "old"))


def test_dashboard_counts_include_monitors_beyond_first_page(logged_in, database):
    from sqlalchemy import insert
    from app.monitoring.schemas import CheckConfig

    with database() as db:
        db.execute(
            insert(Monitor),
            [
                {
                    "name": f"Monitor {i}",
                    "kind": "heartbeat",
                    "config": CheckConfig().model_dump(),
                    "interval": 60,
                    "timeout": 5,
                    "failure_threshold": 3,
                    "recovery_threshold": 2,
                    "next_check_at": time.time(),
                    "created_at": time.time(),
                }
                for i in range(1001)
            ],
        )
        db.commit()
    data = logged_in.get("/api/dashboard").json()
    assert data["counts"]["all"] == 1001 and data["counts"]["UNKNOWN"] == 1001
    assert (
        logged_in.get("/api/monitors/search?offset=1000&limit=50").json()["total"]
        == 1001
    )
    assert (
        len(logged_in.get("/api/monitors/search?offset=1000&limit=50").json()["items"])
        == 1
    )


def test_configuration_change_records_resolution_and_fences_old_result(
    logged_in, database
):
    m = monitor(
        logged_in,
        kind="http",
        config={"url": "http://127.0.0.1:12345/"},
        failure_threshold=1,
    )
    assert renew_lease(database, "worker", 30)
    assert save_result(
        database, "worker", snapshot(database, m["id"]), Outcome("DOWN", 1, "test")
    )
    stale = snapshot(database, m["id"])
    body = {
        key: m[key]
        for key in [
            "name",
            "kind",
            "interval",
            "timeout",
            "failure_threshold",
            "recovery_threshold",
            "revision",
            "priority",
        ]
    }
    body["config"] = {"url": "http://127.0.0.1:12346/"}
    assert logged_in.put(f"/api/monitors/{m['id']}", json=body).status_code == 200
    assert not save_result(database, "worker", stale, Outcome("UP", 1, "old"))
    with database() as db:
        incident = db.scalar(select(Incident))
        assert (
            incident.ended_at is not None
            and incident.resolution == "configuration_changed"
        )


def test_api_ids_are_not_reused_after_deletion(logged_in):
    first = monitor(logged_in)
    assert (
        logged_in.delete(
            f"/api/monitors/{first['id']}?revision={first['revision']}"
        ).status_code
        == 204
    )
    second = monitor(logged_in)
    assert second["id"] > first["id"]
    assert (
        logged_in.delete(
            f"/api/monitors/{first['id']}?revision={first['revision']}"
        ).status_code
        == 404
    )
    for path in ["groups", "tags", "resources"]:
        a = logged_in.post("/api/" + path, json={"name": "test"}).json()
        assert (
            logged_in.delete(
                f"/api/{path}/{a['id']}?revision={a['revision']}"
            ).status_code
            == 204
        )
        b = logged_in.post("/api/" + path, json={"name": "test"}).json()
        assert b["id"] > a["id"]

import time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from ..db import get_db
from ..models import AuditEvent, Group, Monitor, Resource, Tag, resource_tags
from ..security import current_user, editor
from ..monitoring.engine import begin_write, present_monitor, worker_status
from .schemas import GroupInput, ResourceInput, TagInput
from .service import (
    aggregate,
    require_revision,
    require_row,
    set_tags,
    tag_map,
    validate_links,
)

router = APIRouter(prefix="/api")


def writing(db):
    db.commit()
    begin_write(db)


def audit(db, user_id, action):
    db.add(AuditEvent(user_id=user_id, action=action, created_at=int(time.time())))


def commit(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            409, "Nazwa jest już używana albo element jest nadal powiązany."
        ) from None


def group_json(row):
    return {
        "id": row.id,
        "name": row.name,
        "parent_id": row.parent_id,
        "revision": row.revision,
    }


@router.get("/groups")
def groups(user=Depends(current_user), db=Depends(get_db)):
    return [
        group_json(row)
        for row in db.scalars(select(Group).order_by(Group.name, Group.id))
    ]


@router.post("/groups", status_code=201)
def create_group(payload: GroupInput, user=Depends(editor), db=Depends(get_db)):
    user_id = user.id
    writing(db)
    if payload.parent_id is not None:
        require_row(db, Group, payload.parent_id)
    row = Group(name=payload.name, parent_id=payload.parent_id, revision=1)
    db.add(row)
    audit(db, user_id, "group.created")
    commit(db)
    return group_json(row)


@router.put("/groups/{row_id}")
def update_group(
    row_id: int, payload: GroupInput, user=Depends(editor), db=Depends(get_db)
):
    user_id = user.id
    writing(db)
    row = require_row(db, Group, row_id)
    require_revision(row, payload.revision)
    ancestor = payload.parent_id
    seen = set()
    while ancestor is not None:
        if ancestor == row_id or ancestor in seen:
            raise HTTPException(422, "Grupa nie może tworzyć cyklu w hierarchii.")
        seen.add(ancestor)
        ancestor = require_row(db, Group, ancestor).parent_id
    row.name = payload.name
    row.parent_id = payload.parent_id
    row.revision += 1
    audit(db, user_id, "group.updated")
    commit(db)
    return group_json(row)


@router.delete("/groups/{row_id}", status_code=204)
def delete_group(row_id: int, revision: int, user=Depends(editor), db=Depends(get_db)):
    user_id = user.id
    writing(db)
    row = require_row(db, Group, row_id)
    require_revision(row, revision)
    if any(
        db.scalar(select(func.count()).select_from(model).where(column == row_id))
        for model, column in [
            (Group, Group.parent_id),
            (Resource, Resource.group_id),
            (Monitor, Monitor.group_id),
        ]
    ):
        raise HTTPException(
            409, "Najpierw przenieś podgrupy, urządzenia i monitory z tej grupy."
        )
    db.delete(row)
    audit(db, user_id, "group.deleted")
    commit(db)


@router.get("/tags")
def tags(user=Depends(current_user), db=Depends(get_db)):
    return [
        {"id": row.id, "name": row.name, "revision": row.revision}
        for row in db.scalars(select(Tag).order_by(Tag.name))
    ]


@router.post("/tags", status_code=201)
def create_tag(payload: TagInput, user=Depends(editor), db=Depends(get_db)):
    user_id = user.id
    writing(db)
    row = Tag(name=payload.name.lower(), revision=1)
    db.add(row)
    audit(db, user_id, "tag.created")
    commit(db)
    return {"id": row.id, "name": row.name, "revision": row.revision}


@router.put("/tags/{row_id}")
def update_tag(
    row_id: int, payload: TagInput, user=Depends(editor), db=Depends(get_db)
):
    user_id = user.id
    writing(db)
    row = require_row(db, Tag, row_id)
    require_revision(row, payload.revision)
    row.name = payload.name.lower()
    row.revision += 1
    audit(db, user_id, "tag.updated")
    commit(db)
    return {"id": row.id, "name": row.name, "revision": row.revision}


@router.delete("/tags/{row_id}", status_code=204)
def delete_tag(row_id: int, revision: int, user=Depends(editor), db=Depends(get_db)):
    user_id = user.id
    writing(db)
    row = require_row(db, Tag, row_id)
    require_revision(row, revision)
    db.delete(row)
    audit(db, user_id, "tag.deleted")
    commit(db)


def resource_json(row, tag_ids, states):
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "address": row.address,
        "kind": row.kind,
        "operating_system": row.operating_system,
        "environment": row.environment,
        "group_id": row.group_id,
        "tag_ids": tag_ids,
        "revision": row.revision,
        "state": aggregate(states),
        "monitor_count": len(states),
        "paused_count": states.count("PAUSED"),
    }


@router.get("/resources")
def resources(user=Depends(current_user), db=Depends(get_db)):
    healthy = worker_status(db)["status"] == "running"
    states = {}
    links = tag_map(db, resource_tags, "resource_id")
    for monitor in db.scalars(select(Monitor).where(Monitor.resource_id.is_not(None))):
        states.setdefault(monitor.resource_id, []).append(
            present_monitor(monitor, healthy)["state"]
        )
    return [
        resource_json(row, links.get(row.id, []), states.get(row.id, []))
        for row in db.scalars(select(Resource).order_by(Resource.name, Resource.id))
    ]


@router.post("/resources", status_code=201)
def create_resource(payload: ResourceInput, user=Depends(editor), db=Depends(get_db)):
    user_id = user.id
    writing(db)
    validate_links(db, payload.group_id, tag_ids=payload.tag_ids)
    row = Resource(**payload.model_dump(exclude={"tag_ids", "revision"}), revision=1)
    db.add(row)
    db.flush()
    set_tags(db, resource_tags, "resource_id", row.id, payload.tag_ids)
    audit(db, user_id, "resource.created")
    commit(db)
    return resource_json(row, payload.tag_ids, [])


@router.put("/resources/{row_id}")
def update_resource(
    row_id: int, payload: ResourceInput, user=Depends(editor), db=Depends(get_db)
):
    user_id = user.id
    writing(db)
    row = require_row(db, Resource, row_id)
    require_revision(row, payload.revision)
    validate_links(db, payload.group_id, tag_ids=payload.tag_ids)
    for key, value in payload.model_dump(exclude={"tag_ids", "revision"}).items():
        setattr(row, key, value)
    row.revision += 1
    set_tags(db, resource_tags, "resource_id", row.id, payload.tag_ids)
    audit(db, user_id, "resource.updated")
    commit(db)
    return {"id": row.id, "revision": row.revision}


@router.delete("/resources/{row_id}", status_code=204)
def delete_resource(
    row_id: int, revision: int, user=Depends(editor), db=Depends(get_db)
):
    user_id = user.id
    writing(db)
    row = require_row(db, Resource, row_id)
    require_revision(row, revision)
    # Detach only; monitoring and its history continue. Invalidate cached editor revisions.
    from sqlalchemy import update

    db.execute(
        update(Monitor)
        .where(Monitor.resource_id == row_id)
        .values(resource_id=None, revision=Monitor.revision + 1)
    )
    db.execute(delete(Resource).where(Resource.id == row_id))
    audit(db, user_id, "resource.deleted")
    commit(db)

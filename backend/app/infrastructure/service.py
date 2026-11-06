from fastapi import HTTPException
from sqlalchemy import delete, insert, select, func
from ..models import Group, Resource, Tag, Monitor, IdCounter


def require_row(db, model, row_id):
    row = db.get(model, row_id)
    if not row:
        raise HTTPException(404, "Nie znaleziono elementu.")
    return row


def require_revision(row, revision):
    if revision is None or revision != row.revision:
        raise HTTPException(
            409, "Dane zmieniły się w międzyczasie. Odśwież widok i spróbuj ponownie."
        )


def validate_links(db, group_id=None, resource_id=None, tag_ids=()):
    if group_id is not None:
        require_row(db, Group, group_id)
    if resource_id is not None:
        require_row(db, Resource, resource_id)
    if len(set(tag_ids)) != len(tag_ids):
        raise HTTPException(422, "Tagi nie mogą się powtarzać.")
    if tag_ids and set(db.scalars(select(Tag.id).where(Tag.id.in_(tag_ids)))) != set(
        tag_ids
    ):
        raise HTTPException(422, "Nie znaleziono wybranego tagu.")


def set_tags(db, table, column, row_id, ids):
    db.execute(delete(table).where(table.c[column] == row_id))
    if ids:
        db.execute(
            insert(table), [{column: row_id, "tag_id": tag_id} for tag_id in ids]
        )


def tag_map(db, table, column):
    result = {}
    for entity_id, tag_id in db.execute(select(table.c[column], table.c.tag_id)):
        result.setdefault(entity_id, []).append(tag_id)
    return result


def descendants(db, group_id):
    require_row(db, Group, group_id)
    children = {}
    for row_id, parent_id in db.execute(select(Group.id, Group.parent_id)):
        children.setdefault(parent_id, []).append(row_id)
    found = {group_id}
    pending = [group_id]
    while pending:
        for child in children.get(pending.pop(), []):
            if child not in found:
                found.add(child)
                pending.append(child)
    return found


def aggregate(states):
    if not states:
        return "UNKNOWN"
    active = [state for state in states if state != "PAUSED"]
    if not active:
        return "PAUSED"
    return next(
        state
        for state in ["DOWN", "PENDING", "DEGRADED", "UNKNOWN", "UP"]
        if state in active
    )


def allocate_monitor_id(db):
    # Caller holds BEGIN IMMEDIATE on SQLite. Never recycle a deleted API identifier.
    counter = db.scalar(
        select(IdCounter).where(IdCounter.name == "monitor").with_for_update()
    )
    if counter is None:
        raise HTTPException(503, "Baza wymaga zakończenia migracji.")
    next_id = max(counter.next_id, (db.scalar(select(func.max(Monitor.id))) or 0) + 1)
    counter.next_id = next_id + 1
    return next_id

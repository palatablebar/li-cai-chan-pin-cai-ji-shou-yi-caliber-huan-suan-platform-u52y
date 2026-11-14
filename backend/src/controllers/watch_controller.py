"""关注清单控制器。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, watch_service


def list_watches(db: Session, **filters) -> dict:
    return watch_service.list_watches(db, **filters)


def create_watch(db: Session, payload: dict, principal: dict, request: Request) -> dict:
    watch = watch_service.create(db, payload)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="watch.create",
        entity="watch",
        entity_id=watch.id,
        detail={"product_id": watch.product_id, "kind": watch.kind, "due_on": watch.due_on.isoformat()},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return watch_service.serialize(watch)


def update_watch(db: Session, watch_id: int, payload: dict, principal: dict, request: Request) -> dict:
    watch = watch_service.get_watch(db, watch_id)
    watch_service.update(db, watch, payload)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="watch.update",
        entity="watch",
        entity_id=watch.id,
        detail={"status": watch.status, "fields": sorted(payload.keys())},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return watch_service.serialize(watch)

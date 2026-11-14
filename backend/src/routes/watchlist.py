from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import WATCH_WRITE_ROLES
from src.controllers import watch_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.schemas.watch import WatchIn, WatchPatch
from src.utils.pagination import page_params

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("")
def list_watches(
    kind: str | None = None,
    status: str | None = None,
    due_within: int | None = Query(None, ge=0, le=365),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return watch_controller.list_watches(
        db, kind=kind, status=status, due_within=due_within, limit=page.limit, offset=page.offset
    )


@router.post("", status_code=201)
def create_watch(
    payload: WatchIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*WATCH_WRITE_ROLES)),
) -> dict:
    return watch_controller.create_watch(db, payload.model_dump(), principal, request)


@router.patch("/{watch_id}")
def update_watch(
    watch_id: int,
    payload: WatchPatch,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*WATCH_WRITE_ROLES)),
) -> dict:
    return watch_controller.update_watch(db, watch_id, payload.model_dump(exclude_unset=True), principal, request)

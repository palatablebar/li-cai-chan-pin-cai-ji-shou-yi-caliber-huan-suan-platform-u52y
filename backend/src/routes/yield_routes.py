"""收益口径路由：/api/yield-runs 与 /api/yield-views（含复核）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import REVIEW_ROLES, RUN_CREATE_ROLES
from src.controllers import yield_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.schemas.yield_schema import ViewReviewIn, YieldRunIn
from src.utils.pagination import page_params

router = APIRouter(tags=["yield"])


@router.get("/yield-runs")
def list_runs(
    status: str | None = None,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return yield_controller.list_runs(db, status=status, limit=page.limit, offset=page.offset)


@router.get("/yield-runs/{run_id}")
def get_run(
    run_id: int,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    return yield_controller.get_run(db, run_id)


@router.post("/yield-runs", status_code=201)
def create_run(
    payload: YieldRunIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*RUN_CREATE_ROLES)),
) -> dict:
    return yield_controller.create_run(db, payload.model_dump(), principal, request)


@router.get("/yield-views/groups")
def list_groups(
    run_id: int | None = None,
    top_n: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    return yield_controller.groups(db, run_id, top_n)


@router.get("/yield-views")
def list_views(
    run_id: int | None = None,
    method: str | None = None,
    status: str | None = None,
    risk_level: str | None = None,
    group: str | None = None,
    q: str | None = None,
    ranked_only: bool = Query(False),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return yield_controller.list_views(
        db,
        principal,
        run_id=run_id,
        method=method,
        status=status,
        risk_level=risk_level,
        group=group,
        q=q,
        ranked_only=ranked_only,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/yield-views/{view_id}")
def get_view(
    view_id: int,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    return yield_controller.get_view(db, view_id)


@router.patch("/yield-views/{view_id}/review")
def review_view(
    view_id: int,
    payload: ViewReviewIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*REVIEW_ROLES)),
) -> dict:
    return yield_controller.review(db, view_id, payload.model_dump(), principal, request)

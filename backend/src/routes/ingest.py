from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import INGEST_CONFIRM_ROLES, INGEST_WRITE_ROLES
from src.controllers import ingest_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.schemas.ingest import IngestBatchIn, IngestConfirmIn, IngestRecordPatch
from src.utils.pagination import page_params

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.get("/batches")
def list_batches(
    institution: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return ingest_controller.list_batches(db, institution=institution, limit=page.limit, offset=page.offset)


@router.post("/batches")
def submit_batch(
    payload: IngestBatchIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*INGEST_WRITE_ROLES)),
) -> dict:
    """接收一批机构记录；同一（机构, batch_key）重试幂等，不新增、不丢失、不改写已确认。"""
    return ingest_controller.submit_batch(
        db,
        {
            "institution": payload.institution,
            "batch_key": payload.batch_key,
            "note": payload.note,
            "rows": [row.model_dump() for row in payload.rows],
        },
        principal,
        request,
    )


@router.get("/batches/{batch_id}")
def get_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    return ingest_controller.batch_detail(db, batch_id)


@router.get("/records")
def list_records(
    batch_id: int | None = None,
    status: str | None = None,
    institution: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return ingest_controller.list_records(
        db,
        batch_id=batch_id,
        status=status,
        institution=institution,
        limit=page.limit,
        offset=page.offset,
    )


@router.patch("/records/{record_id}")
def complete_record(
    record_id: int,
    payload: IngestRecordPatch,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*INGEST_WRITE_ROLES)),
) -> dict:
    fields = {key: value for key, value in payload.model_dump(exclude_unset=True).items() if value is not None}
    return ingest_controller.complete_record(db, record_id, fields, principal, request)


@router.post("/records/{record_id}/confirm")
def confirm_record(
    record_id: int,
    payload: IngestConfirmIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*INGEST_CONFIRM_ROLES)),
) -> dict:
    return ingest_controller.confirm_record(db, record_id, payload.model_dump(), principal, request)

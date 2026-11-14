from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import QUOTE_IMPORT_ROLES
from src.controllers import quote_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.schemas.quote import QuoteImportIn, QuoteIn
from src.utils.pagination import page_params

router = APIRouter(prefix="/quotes", tags=["quotes"])


@router.get("")
def list_quotes(
    product_id: int | None = None,
    quote_date: str | None = None,
    missing: bool = Query(False, description="只看四项口径全缺的报价"),
    limit: int = Query(60, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return quote_controller.list_quotes(
        db,
        product_id=product_id,
        quote_date=quote_date,
        method_missing=missing,
        limit=page.limit,
        offset=page.offset,
    )


@router.post("", status_code=201)
def create_quote(
    payload: QuoteIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*QUOTE_IMPORT_ROLES)),
) -> dict:
    return quote_controller.create_quote(db, payload.model_dump(), principal, request)


@router.post("/import")
def import_quotes(
    payload: QuoteImportIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*QUOTE_IMPORT_ROLES)),
) -> dict:
    return quote_controller.import_quotes(db, [row.model_dump() for row in payload.rows], principal, request)

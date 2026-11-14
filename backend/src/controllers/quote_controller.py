"""报价控制器：单条补录与批量导入（自然键 conflict -> 409）。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, quote_service


def list_quotes(db: Session, **filters) -> dict:
    return quote_service.list_quotes(db, **filters)


def create_quote(db: Session, payload: dict, principal: dict, request: Request) -> dict:
    quote = quote_service.create(db, payload, source="manual")
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="quote.import",
        entity="quote",
        entity_id=quote.id,
        detail={"product_id": quote.product_id, "quote_date": quote.quote_date.isoformat()},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return quote_service.serialize(quote)


def import_quotes(db: Session, rows: list[dict], principal: dict, request: Request) -> dict:
    result = quote_service.import_rows(db, rows, source="import")
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="quote.import",
        entity="quote",
        entity_id=None,
        detail=result,
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return result

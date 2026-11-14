"""导出控制器：CSV 响应 + 审计（导出是管理员专属权限）。"""
from __future__ import annotations

from fastapi import Request, Response
from sqlalchemy.orm import Session

from src.services import audit_service, export_service
from src.utils.csv_export import csv_response_headers


def views_csv(db: Session, run_id: int | None, principal: dict, request: Request) -> Response:
    content = export_service.views_csv(db, run_id)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="export.views",
        entity="yield_view",
        entity_id=run_id,
        detail={"bytes": len(content), "run_id": run_id},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers=csv_response_headers("views.csv"),
    )


def quotes_csv(db: Session, principal: dict, request: Request) -> Response:
    content = export_service.quotes_csv(db)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="export.quotes",
        entity="quote",
        entity_id=None,
        detail={"bytes": len(content)},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers=csv_response_headers("quotes.csv"),
    )


def runs_csv(db: Session, principal: dict, request: Request) -> Response:
    content = export_service.runs_csv(db)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="export.views",
        entity="yield_run",
        entity_id=None,
        detail={"bytes": len(content), "kind": "runs"},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers=csv_response_headers("runs.csv"),
    )

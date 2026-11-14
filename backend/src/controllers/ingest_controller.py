"""机构采集控制器：提交批次 / 补齐 / 确认写操作记领域审计。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.models.product import Product
from src.services import audit_service, ingest_service


def list_batches(db: Session, **filters) -> dict:
    return ingest_service.list_batches(db, **filters)


def submit_batch(db: Session, payload: dict, principal: dict, request: Request) -> dict:
    result = ingest_service.submit_batch(
        db,
        institution=payload["institution"],
        batch_key=payload["batch_key"],
        rows=payload["rows"],
        operator_email=principal["email"],
        note=payload.get("note"),
    )
    batch = result["batch"]
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="ingest.submit",
        entity="ingest_batch",
        entity_id=batch["id"],
        detail={
            "batch_no": batch["batch_no"],
            "institution": batch["institution"],
            "batch_key": batch["batch_key"],
            "reused": result["reused"],
            "created": result["created"],
            "updated": result["updated"],
            "kept_confirmed": result["kept_confirmed"],
            "counts": batch["counts"],
            "rejected": len(result["rejected"]),
        },
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return result


def batch_detail(db: Session, batch_id: int) -> dict:
    return ingest_service.batch_detail(db, batch_id)


def list_records(db: Session, **filters) -> dict:
    return ingest_service.list_records(db, **filters)


def complete_record(db: Session, record_id: int, fields: dict, principal: dict, request: Request) -> dict:
    record = ingest_service.complete_record(db, record_id, fields)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="ingest.complete",
        entity="source_record",
        entity_id=record.id,
        detail={
            "institution": record.institution,
            "inst_code": record.inst_code,
            "fields": sorted(fields.keys()),
            "status": record.status,
            "missing": record.missing_fields or [],
        },
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return ingest_service.serialize_record(record, product=db.get(Product, record.product_id) if record.product_id else None)


def confirm_record(db: Session, record_id: int, payload: dict, principal: dict, request: Request) -> dict:
    record = ingest_service.confirm_record(
        db,
        record_id,
        reviewer=principal["email"],
        note=payload.get("note"),
        resolution=payload.get("resolution"),
    )
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="ingest.confirm",
        entity="source_record",
        entity_id=record.id,
        detail={
            "institution": record.institution,
            "inst_code": record.inst_code,
            "product_id": record.product_id,
            "resolution": payload.get("resolution"),
        },
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return ingest_service.serialize_record(record, product=db.get(Product, record.product_id) if record.product_id else None)

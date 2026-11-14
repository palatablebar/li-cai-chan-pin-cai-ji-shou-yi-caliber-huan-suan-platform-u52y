"""产品主档控制器：写操作记领域审计；只读角色隐藏费率明细。"""
from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from src.services import audit_service, product_service


def _hide_fee(principal: dict) -> bool:
    return principal.get("role") == "viewer"


def list_products(db: Session, principal: dict, **filters) -> dict:
    return product_service.list_products(db, hide_fee=_hide_fee(principal), **filters)


def get_product(db: Session, product_id: int, principal: dict) -> dict:
    return product_service.detail(db, product_id, hide_fee=_hide_fee(principal))


def create_product(db: Session, payload: dict, principal: dict, request: Request) -> dict:
    product = product_service.create(db, payload)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="product.create",
        entity="product",
        entity_id=product.id,
        detail={"code": product.code, "name": product.name, "risk_level": product.risk_level},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return product_service.serialize(product)


def update_product(db: Session, product_id: int, payload: dict, principal: dict, request: Request) -> dict:
    product = product_service.get_product(db, product_id)
    product_service.update(db, product, payload)
    audit_service.record(
        db,
        actor_email=principal["email"],
        actor_role=principal["role"],
        action="product.update",
        entity="product",
        entity_id=product.id,
        detail={"fields": sorted(payload.keys())},
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return product_service.serialize(product)

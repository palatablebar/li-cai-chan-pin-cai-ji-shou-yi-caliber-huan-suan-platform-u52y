from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.constants.roles import PRODUCT_WRITE_ROLES
from src.controllers import product_controller
from src.middlewares.rbac import READ_ROLES, require_roles
from src.schemas.product import ProductIn, ProductPatch
from src.services import product_service
from src.utils.pagination import page_params

router = APIRouter(prefix="/products", tags=["products"])


@router.get("")
def list_products(
    q: str | None = None,
    type: str | None = None,
    risk_level: str | None = None,
    bucket: str | None = None,
    issuer: str | None = None,
    active: bool | None = None,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    page = page_params(limit, offset)
    return product_controller.list_products(
        db,
        principal,
        q=q,
        type=type,
        risk_level=risk_level,
        bucket=bucket,
        issuer=issuer,
        active=active,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/issuers")
def list_issuers(
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    return {"items": product_service.issuers(db)}


@router.get("/{product_id}")
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*READ_ROLES)),
) -> dict:
    return product_controller.get_product(db, product_id, principal)


@router.post("", status_code=201)
def create_product(
    payload: ProductIn,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*PRODUCT_WRITE_ROLES)),
) -> dict:
    return product_controller.create_product(db, payload.model_dump(), principal, request)


@router.patch("/{product_id}")
def update_product(
    product_id: int,
    payload: ProductPatch,
    request: Request,
    db: Session = Depends(get_db),
    principal: dict = Depends(require_roles(*PRODUCT_WRITE_ROLES)),
) -> dict:
    return product_controller.update_product(
        db, product_id, payload.model_dump(exclude_unset=True), principal, request
    )

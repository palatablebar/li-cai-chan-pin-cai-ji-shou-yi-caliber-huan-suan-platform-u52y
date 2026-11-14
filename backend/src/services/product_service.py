"""产品主档服务：筛选、详情（含最近报价与最近一次口径结果）、维护。"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from src.constants.enums import (
    PRODUCT_TYPE_LABELS,
    RISK_LEVEL_LABELS,
    TERM_BUCKET_LABELS,
)
from src.models.product import Product
from src.models.quote import Quote
from src.models.yield_run import YieldRun
from src.models.yield_view import YieldView
from src.services.yield_math import term_bucket
from src.utils.errors import AppError, not_found
from src.utils.timeutil import iso_date, iso_utc

BUCKET_FILTERS = {
    "le30": (Product.term_days <= 30),
    "d31_180": (Product.term_days >= 31) & (Product.term_days <= 180),
    "d181_365": (Product.term_days >= 181) & (Product.term_days <= 365),
    "gt365": (Product.term_days > 365),
}


def serialize(product: Product, *, hide_fee: bool = False) -> dict:
    bucket = term_bucket(product.term_days)
    return {
        "id": product.id,
        "code": product.code,
        "name": product.name,
        "issuer": product.issuer,
        "type": product.type,
        "type_label": PRODUCT_TYPE_LABELS.get(product.type, product.type),
        "risk_level": product.risk_level,
        "risk_label": RISK_LEVEL_LABELS.get(product.risk_level, product.risk_level),
        "min_amount": round(float(product.min_amount or 0), 2),
        "min_amount_wan": round((float(product.min_amount or 0) / 10000.0), 2),
        "term_days": product.term_days,
        "term_bucket": bucket,
        "term_bucket_label": TERM_BUCKET_LABELS.get(bucket, bucket),
        "fee_rate": None if hide_fee else round(float(product.fee_rate or 0), 4),
        "fee_hidden": hide_fee,
        "active": product.active,
        "note": product.note,
        "created_at": iso_utc(product.created_at),
        "updated_at": iso_utc(product.updated_at),
    }


def list_products(
    db: Session,
    *,
    q: str | None = None,
    type: str | None = None,
    risk_level: str | None = None,
    bucket: str | None = None,
    issuer: str | None = None,
    active: bool | None = None,
    limit: int = 20,
    offset: int = 0,
    hide_fee: bool = False,
) -> dict:
    stmt = select(Product)
    count_stmt = select(func.count()).select_from(Product)
    conditions = []
    if q:
        like = f"%{q.strip()}%"
        conditions.append(or_(Product.name.ilike(like), Product.code.ilike(like), Product.issuer.ilike(like)))
    if type:
        conditions.append(Product.type == type)
    if risk_level:
        conditions.append(Product.risk_level == risk_level)
    if issuer:
        conditions.append(Product.issuer == issuer)
    if bucket and bucket in BUCKET_FILTERS:
        conditions.append(BUCKET_FILTERS[bucket])
    if active is not None:
        conditions.append(Product.active.is_(active))
    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(Product.risk_level, Product.code).limit(limit).offset(offset)).all()
    return {
        "items": [serialize(row, hide_fee=hide_fee) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def issuers(db: Session) -> list[str]:
    return list(db.scalars(select(Product.issuer).distinct().order_by(Product.issuer)).all())


def get_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise not_found("product", product_id)
    return product


def latest_quote(db: Session, product_id: int) -> Quote | None:
    return db.scalar(select(Quote).where(Quote.product_id == product_id).order_by(Quote.quote_date.desc()).limit(1))


def latest_view(db: Session, product_id: int) -> tuple[YieldView, YieldRun] | None:
    row = db.execute(
        select(YieldView, YieldRun)
        .join(YieldRun, YieldRun.id == YieldView.run_id)
        .where(YieldView.product_id == product_id)
        .order_by(YieldView.run_id.desc())
        .limit(1)
    ).first()
    return (row[0], row[1]) if row else None


def detail(db: Session, product_id: int, *, hide_fee: bool = False) -> dict:
    from src.services import quote_service, yield_service

    product = get_product(db, product_id)
    payload = serialize(product, hide_fee=hide_fee)
    quotes = db.scalars(
        select(Quote).where(Quote.product_id == product_id).order_by(Quote.quote_date.desc()).limit(5)
    ).all()
    payload["quotes"] = [quote_service.serialize(row, product=product) for row in reversed(quotes)]
    latest = latest_view(db, product_id)
    if latest:
        view, run = latest
        payload["view"] = yield_service.serialize_view(view, product=product, run_no=run.run_no)
    else:
        payload["view"] = None
    return payload


def create(db: Session, payload: dict) -> Product:
    exists = db.scalar(select(Product).where(Product.code == payload["code"]))
    if exists is not None:
        raise AppError("CONFLICT", 409, {"code": payload["code"]})
    product = Product(
        code=payload["code"],
        name=payload["name"],
        issuer=payload["issuer"],
        type=payload["type"],
        risk_level=payload["risk_level"],
        min_amount=float(payload.get("min_amount") or 10000.0),
        term_days=int(payload.get("term_days") or 0),
        fee_rate=float(payload.get("fee_rate") or 0.0),
        active=bool(payload.get("active", True)),
        note=payload.get("note"),
    )
    db.add(product)
    db.flush()
    return product


def update(db: Session, product: Product, payload: dict) -> Product:
    for field in ("name", "issuer", "type", "risk_level", "min_amount", "term_days", "fee_rate", "active", "note"):
        if field in payload and payload[field] is not None:
            setattr(product, field, payload[field])
    db.flush()
    return product


def stats(db: Session) -> dict:
    total = db.scalar(select(func.count()).select_from(Product)) or 0
    active = db.scalar(select(func.count()).select_from(Product).where(Product.active.is_(True))) or 0
    return {"total": total, "active": active, "issuers": len(issuers(db)), "quote_dates": iso_date(max_quote_date(db))}


def max_quote_date(db: Session):
    return db.scalar(select(func.max(Quote.quote_date)))

"""行情报价服务：按产品/日期检索，单条补录与批量导入（自然键 product_id + quote_date）。"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import QUOTE_SOURCE_LABELS
from src.constants.limits import MAX_IMPORT_ROWS
from src.models.product import Product
from src.models.quote import Quote
from src.utils.errors import AppError
from src.utils.timeutil import iso_date, iso_utc

FIELDS = ("nav", "seven_day_pct", "wanfen_yield", "bench_low", "bench_high", "year_pct")


def serialize(quote: Quote, *, product: Product | None = None) -> dict:
    return {
        "id": quote.id,
        "product_id": quote.product_id,
        "product_code": product.code if product else None,
        "product_name": product.name if product else None,
        "quote_date": iso_date(quote.quote_date),
        "nav": quote.nav,
        "seven_day_pct": quote.seven_day_pct,
        "wanfen_yield": quote.wanfen_yield,
        "bench_low": quote.bench_low,
        "bench_high": quote.bench_high,
        "year_pct": quote.year_pct,
        "source": quote.source,
        "source_label": QUOTE_SOURCE_LABELS.get(quote.source, quote.source),
        "created_at": iso_utc(quote.created_at),
    }


def list_quotes(
    db: Session,
    *,
    product_id: int | None = None,
    quote_date: str | None = None,
    method_missing: bool = False,
    limit: int = 60,
    offset: int = 0,
) -> dict:
    stmt = select(Quote)
    count_stmt = select(func.count()).select_from(Quote)
    if product_id:
        stmt = stmt.where(Quote.product_id == product_id)
        count_stmt = count_stmt.where(Quote.product_id == product_id)
    if quote_date:
        stmt = stmt.where(Quote.quote_date == date.fromisoformat(quote_date))
        count_stmt = count_stmt.where(Quote.quote_date == date.fromisoformat(quote_date))
    if method_missing:
        condition = Quote.seven_day_pct.is_(None) & Quote.wanfen_yield.is_(None) & Quote.nav.is_(None)
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Quote.quote_date.desc(), Quote.product_id).limit(limit).offset(offset)
    ).all()
    products = {product.id: product for product in db.scalars(select(Product)).all()}
    return {
        "items": [serialize(row, product=products.get(row.product_id)) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _resolve_product(db: Session, payload: dict) -> Product:
    product = None
    if payload.get("product_id"):
        product = db.get(Product, int(payload["product_id"]))
    elif payload.get("product_code"):
        product = db.scalar(select(Product).where(Product.code == payload["product_code"]))
    if product is None:
        raise AppError("NOT_FOUND", 404, {"entity": "product", "id": payload.get("product_id") or payload.get("product_code")})
    return product


def _assign(quote: Quote, payload: dict, source: str) -> None:
    for field in FIELDS:
        if field in payload:
            setattr(quote, field, payload[field])
    quote.source = source


def create(db: Session, payload: dict, source: str = "manual") -> Quote:
    product = _resolve_product(db, payload)
    quote_date = date.fromisoformat(str(payload["quote_date"])[:10])
    exists = db.scalar(select(Quote).where(Quote.product_id == product.id, Quote.quote_date == quote_date))
    if exists is not None:
        raise AppError(
            "CONFLICT",
            409,
            {"product_id": product.id, "quote_date": quote_date.isoformat(), "quote_id": exists.id},
        )
    quote = Quote(product_id=product.id, quote_date=quote_date)
    _assign(quote, payload, source)
    db.add(quote)
    db.flush()
    return quote


def import_rows(db: Session, rows: list[dict], source: str = "import") -> dict:
    """批量导入：自然键 upsert，返回新建/更新/跳过数量。"""
    if len(rows) > MAX_IMPORT_ROWS:
        raise AppError("VALIDATION", 422, {"rows": len(rows), "max": MAX_IMPORT_ROWS})
    created = updated = skipped = 0
    for payload in rows:
        try:
            product = _resolve_product(db, payload)
            quote_date = date.fromisoformat(str(payload["quote_date"])[:10])
        except (AppError, KeyError, ValueError):
            skipped += 1
            continue
        existing = db.scalar(select(Quote).where(Quote.product_id == product.id, Quote.quote_date == quote_date))
        if existing is None:
            quote = Quote(product_id=product.id, quote_date=quote_date)
            _assign(quote, payload, source)
            db.add(quote)
            created += 1
        else:
            _assign(existing, payload, source)
            updated += 1
    db.flush()
    return {"created": created, "updated": updated, "skipped": skipped}

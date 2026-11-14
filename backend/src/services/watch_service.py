"""关注清单服务：到期提醒与排名提醒，带剩余天数。"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import WATCH_KIND_LABELS, WATCH_STATUS_LABELS
from src.models.product import Product
from src.models.watch import Watch
from src.utils.errors import AppError, not_found
from src.utils.timeutil import iso_date, local_now

EXPIRING_WINDOW_DAYS = 7


def serialize(watch: Watch, *, product: Product | None = None) -> dict:
    days_left = (watch.due_on - local_now().date()).days
    return {
        "id": watch.id,
        "product_id": watch.product_id,
        "product_code": product.code if product else None,
        "product_name": product.name if product else None,
        "issuer": product.issuer if product else None,
        "risk_level": product.risk_level if product else None,
        "kind": watch.kind,
        "kind_label": WATCH_KIND_LABELS.get(watch.kind, watch.kind),
        "due_on": iso_date(watch.due_on),
        "days_left": days_left,
        "overdue": days_left < 0,
        "due_soon": 0 <= days_left <= EXPIRING_WINDOW_DAYS,
        "status": watch.status,
        "status_label": WATCH_STATUS_LABELS.get(watch.status, watch.status),
        "note": watch.note,
        "owner": watch.owner,
    }


def list_watches(
    db: Session,
    *,
    kind: str | None = None,
    status: str | None = None,
    due_within: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    stmt = select(Watch)
    count_stmt = select(func.count()).select_from(Watch)
    if kind:
        stmt = stmt.where(Watch.kind == kind)
        count_stmt = count_stmt.where(Watch.kind == kind)
    if status:
        stmt = stmt.where(Watch.status == status)
        count_stmt = count_stmt.where(Watch.status == status)
    if due_within is not None:
        today = local_now().date()
        end = date.fromordinal(today.toordinal() + due_within)
        condition = Watch.due_on >= today
        condition = condition & (Watch.due_on <= end)
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(Watch.due_on, Watch.id).limit(limit).offset(offset)).all()
    products = {product.id: product for product in db.scalars(select(Product)).all()}
    return {
        "items": [serialize(row, product=products.get(row.product_id)) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "expiring_7d": expiring_count(db),
    }


def expiring_count(db: Session, days: int = EXPIRING_WINDOW_DAYS) -> int:
    today = local_now().date()
    end = date.fromordinal(today.toordinal() + days)
    stmt = (
        select(func.count())
        .select_from(Watch)
        .where(Watch.kind == "expire")
        .where(Watch.due_on >= today)
        .where(Watch.due_on <= end)
        .where(Watch.status != "done")
    )
    return db.scalar(stmt) or 0


def create(db: Session, payload: dict) -> Watch:
    product = db.get(Product, int(payload["product_id"]))
    if product is None:
        raise not_found("product", payload.get("product_id"))
    due_on = date.fromisoformat(str(payload["due_on"])[:10])
    exists = db.scalar(select(Watch).where(Watch.product_id == product.id, Watch.kind == payload["kind"]))
    if exists is not None:
        raise AppError("CONFLICT", 409, {"product_id": product.id, "kind": payload["kind"]})
    watch = Watch(
        product_id=product.id,
        kind=payload["kind"],
        due_on=due_on,
        status=payload.get("status") or "pending",
        note=payload.get("note"),
    )
    db.add(watch)
    db.flush()
    return watch


def update(db: Session, watch: Watch, payload: dict) -> Watch:
    if payload.get("status") is not None:
        watch.status = payload["status"]
    if payload.get("due_on") is not None:
        watch.due_on = date.fromisoformat(str(payload["due_on"])[:10])
    if payload.get("note") is not None:
        watch.note = payload["note"]
    db.flush()
    return watch


def get_watch(db: Session, watch_id: int) -> Watch:
    watch = db.get(Watch, watch_id)
    if watch is None:
        raise not_found("watch", watch_id)
    return watch

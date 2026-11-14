"""总览：在售规模、到期提醒、口径异常、类型/口径分布与同类榜首。"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.constants.enums import (
    PRODUCT_TYPE_LABELS,
    RISK_LEVEL_LABELS,
    RISK_LEVEL_ORDER,
    YIELD_METHOD_LABELS,
)
from src.models.product import Product
from src.models.quote import Quote
from src.models.watch import Watch
from src.models.yield_run import YieldRun
from src.models.yield_view import YieldView
from src.services import watch_service, yield_service
from src.utils.timeutil import iso_date, iso_utc, local_now


def worker_alive() -> bool:
    try:
        import time

        import redis

        client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2)
        value = client.get(f"{settings.app_name}:worker:heartbeat")
        return bool(value) and (time.time() - float(value)) < 120
    except Exception:
        return False


def _quote_days(db: Session, limit: int = 5) -> list[dict]:
    rows = db.execute(
        select(Quote.quote_date, func.count()).group_by(Quote.quote_date).order_by(Quote.quote_date.desc()).limit(limit)
    ).all()
    return [{"date": iso_date(day), "count": count} for day, count in reversed(rows)]


def overview(db: Session) -> dict:
    products_total = db.scalar(select(func.count()).select_from(Product)) or 0
    active_total = db.scalar(select(func.count()).select_from(Product).where(Product.active.is_(True))) or 0
    issuer_total = db.scalar(select(func.count(func.distinct(Product.issuer)))) or 0
    quotes_total = db.scalar(select(func.count()).select_from(Quote)) or 0
    runs_total = db.scalar(select(func.count()).select_from(YieldRun)) or 0
    watches_total = db.scalar(select(func.count()).select_from(Watch)) or 0
    watch_pending = db.scalar(select(func.count()).select_from(Watch).where(Watch.status == "pending")) or 0

    latest_run = db.scalar(select(YieldRun).order_by(YieldRun.id.desc()).limit(1))
    latest_id = latest_run.id if latest_run else None
    views = (
        db.scalars(select(YieldView).where(YieldView.run_id == latest_id)).all() if latest_id else []
    )
    unknown_total = sum(1 for view in views if view.method == "unknown")
    pending_review = sum(1 for view in views if view.status == "pending")
    confirmed_review = sum(1 for view in views if view.status == "confirmed")
    dismissed_review = sum(1 for view in views if view.status == "dismissed")

    method_counts: dict[str, int] = {}
    for view in views:
        method_counts[view.method] = method_counts.get(view.method, 0) + 1
    method_mix = [
        {"key": key, "label": YIELD_METHOD_LABELS.get(key, key), "count": count}
        for key, count in sorted(method_counts.items(), key=lambda pair: -pair[1])
    ]

    type_rows = db.execute(select(Product.type, func.count()).group_by(Product.type)).all()
    type_mix = [
        {"key": key, "label": PRODUCT_TYPE_LABELS.get(key, key), "count": count}
        for key, count in sorted(type_rows, key=lambda pair: -pair[1])
    ]
    risk_rows = dict(db.execute(select(Product.risk_level, func.count()).group_by(Product.risk_level)).all())
    risk_mix = [
        {"key": level, "label": RISK_LEVEL_LABELS.get(level, level), "count": risk_rows.get(level, 0)}
        for level in RISK_LEVEL_ORDER
    ]

    groups = yield_service.groups(db, latest_id, top_n=3)["items"] if latest_id else []
    metrics = (latest_run.metrics or {}) if latest_run else {}

    today = local_now().date()
    expiry_rows = db.scalars(
        select(Watch)
        .where(Watch.kind == "expire")
        .where(Watch.due_on >= today)
        .where(Watch.due_on <= today + timedelta(days=7))
        .where(Watch.status != "done")
        .order_by(Watch.due_on)
    ).all()
    products = {product.id: product for product in db.scalars(select(Product)).all()}
    expiring = [
        {
            "id": watch.id,
            "product_name": products[watch.product_id].name if watch.product_id in products else None,
            "risk_level": products[watch.product_id].risk_level if watch.product_id in products else None,
            "due_on": iso_date(watch.due_on),
            "days_left": (watch.due_on - today).days,
            "kind": watch.kind,
        }
        for watch in expiry_rows
    ]

    return {
        "products_total": products_total,
        "active_total": active_total,
        "issuer_total": issuer_total,
        "quotes_total": quotes_total,
        "quote_days": _quote_days(db),
        "runs_total": runs_total,
        "watches_total": watches_total,
        "watch_pending": watch_pending,
        "expiring_total": watch_service.expiring_count(db),
        "expiring": expiring,
        "unknown_total": unknown_total,
        "pending_review": pending_review,
        "confirmed_review": confirmed_review,
        "dismissed_review": dismissed_review,
        "worker_alive": worker_alive(),
        "latest_run": {
            "id": latest_run.id,
            "run_no": latest_run.run_no,
            "status": latest_run.status,
            "status_label": yield_service.RUN_STATUS_LABELS.get(latest_run.status, latest_run.status),
            "started_at": iso_utc(latest_run.started_at),
            "view_count": latest_run.view_count,
            "top_group": metrics.get("top_group"),
        }
        if latest_run
        else None,
        "type_mix": type_mix,
        "risk_mix": risk_mix,
        "method_mix": method_mix,
        "risk_top": metrics.get("risk_top") or {},
        "groups": groups,
        "avg_comparable_pct": metrics.get("avg_comparable_pct"),
        "ranked_groups": metrics.get("ranked_groups"),
    }

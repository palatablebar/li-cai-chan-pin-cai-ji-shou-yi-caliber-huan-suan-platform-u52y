"""收益口径换算服务：取当日报价 → 算法 A 换算 → 算法 B 同类排名 → 落 YieldView。"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import (
    CONFIDENCE_LABELS,
    PRODUCT_TYPE_LABELS,
    REVIEW_STATUS_LABELS,
    RISK_LEVEL_LABELS,
    RUN_STATUS_LABELS,
    TERM_BUCKET_LABELS,
    TRIGGER_LABELS,
    YIELD_METHOD_LABELS,
    ReviewStatus,
    RunStatus,
)
from src.models.product import Product
from src.models.quote import Quote
from src.models.yield_run import YieldRun
from src.models.yield_view import YieldView
from src.services import yield_math
from src.utils.errors import AppError
from src.utils.timeutil import iso_utc, local_now, utcnow


def next_run_no(db: Session) -> str:
    prefix = f"YR{local_now():%Y%m%d}"
    count = db.scalar(select(func.count()).select_from(YieldRun).where(YieldRun.run_no.like(f"{prefix}%"))) or 0
    return f"{prefix}-{count + 1:04d}"


def compute_items(db: Session) -> list[dict]:
    """把库里所有产品 + 报价换算成可比年化，并完成同类排名（算法 A + B）。"""
    products = db.scalars(select(Product).order_by(Product.id)).all()
    quotes = db.scalars(select(Quote).order_by(Quote.product_id, Quote.quote_date)).all()
    by_product: dict[int, list[Quote]] = {}
    for quote in quotes:
        by_product.setdefault(quote.product_id, []).append(quote)

    items: list[dict] = []
    for product in products:
        rows = by_product.get(product.id, [])
        nav_series = [{"quote_date": row.quote_date, "nav": row.nav} for row in rows if row.nav is not None]
        latest = rows[-1] if rows else None
        quote_dict = (
            {
                "quote_date": latest.quote_date,
                "nav": latest.nav,
                "seven_day_pct": latest.seven_day_pct,
                "wanfen_yield": latest.wanfen_yield,
                "bench_low": latest.bench_low,
                "bench_high": latest.bench_high,
            }
            if latest
            else {}
        )
        normalized = yield_math.normalize_quote(quote_dict, nav_series)
        items.append(
            {
                "product_id": product.id,
                "product_name": product.name,
                "product_code": product.code,
                "product_type": product.type,
                "risk_level": product.risk_level,
                "term_days": product.term_days,
                "issuer": product.issuer,
                "quote_date": latest.quote_date if latest else None,
                "comparable_pct": normalized["comparable_pct"],
                "method": normalized["method"],
                "confidence": normalized["confidence"],
                "caveat": normalized["caveat"],
                "source_value": normalized["source_value"],
                "vol_annual": yield_math.annualized_volatility(nav_series),
            }
        )
    return yield_math.rank_peers(items)


def _upsert_views(db: Session, run: YieldRun, items: list[dict]) -> None:
    existing_rows = db.scalars(select(YieldView).where(YieldView.run_id == run.id)).all()
    existing = {row.product_id: row for row in existing_rows}
    for item in items:
        flags = {
            "caveat": item["caveat"],
            "source_value": item.get("source_value"),
            "tags": list(item.get("flags") or []),
            "group_median_vol": item.get("group_median_vol"),
        }
        row = existing.get(item["product_id"])
        if row is None:
            db.add(
                YieldView(
                    run_id=run.id,
                    product_id=item["product_id"],
                    comparable_pct=item["comparable_pct"],
                    method=item["method"],
                    confidence=item["confidence"],
                    peer_rank=item["peer_rank"],
                    risk_adj=item["risk_adj"],
                    group_key=item["group_key"],
                    group_size=item["group_size"],
                    vol_annual=item["vol_annual"],
                    status=ReviewStatus.PENDING.value,
                    flags=flags,
                )
            )
            continue
        # 重跑只刷新算法结果，不覆盖人工复核状态
        row.comparable_pct = item["comparable_pct"]
        row.method = item["method"]
        row.confidence = item["confidence"]
        row.peer_rank = item["peer_rank"]
        row.risk_adj = item["risk_adj"]
        row.group_key = item["group_key"]
        row.group_size = item["group_size"]
        row.vol_annual = item["vol_annual"]
        row.flags = flags


def _log_text(items: list[dict], metrics: dict) -> str:
    counts = metrics.get("method_counts") or {}
    parts = [
        f"{YIELD_METHOD_LABELS.get(key, key)} {value}"
        for key, value in sorted(counts.items(), key=lambda pair: -pair[1])
    ]
    top = metrics.get("top_group") or {}
    lines = [
        f"口径换算完成：{len(items)} 只产品 / {len(items)} 条结果",
        "方法分布：" + " · ".join(parts),
        f"同类分组 {len(metrics.get('groups') or [])} 个，可排名 {metrics.get('ranked_groups')} 个（样本≥{yield_math.PEER_MIN_SAMPLE}）",
    ]
    if top:
        lines.append(f"全局榜首：{top.get('group_label')} → {top.get('top_product_name')} {top.get('top_comparable_pct')}%")
    lines.append(f"口径缺失 {metrics.get('unknown')} 条，标记 unknown 待人工补录，不做估算")
    return "\n".join(lines)


def execute(db: Session, run: YieldRun) -> YieldRun:
    run.status = RunStatus.RUNNING.value
    try:
        items = compute_items(db)
        _upsert_views(db, run, items)
        metrics = yield_math.summarize(items)
        metrics["products"] = len(items)
        best_group = None
        for group in metrics["groups"]:
            if not group["ranked"]:
                continue
            if best_group is None or (group["top_comparable_pct"] or 0) > (best_group["top_comparable_pct"] or 0):
                best_group = group
        if best_group:
            group_type, _, bucket = best_group["group_key"].partition(":")
            label = f"{PRODUCT_TYPE_LABELS.get(group_type, group_type)} · {TERM_BUCKET_LABELS.get(bucket, bucket)}"
            metrics["top_group"] = {
                "group_key": best_group["group_key"],
                "group_label": label,
                "top_product_id": best_group["top_product_id"],
                "top_product_name": best_group["top_product_name"],
                "top_comparable_pct": best_group["top_comparable_pct"],
            }
        run.metrics = metrics
        run.log_text = _log_text(items, metrics)
        run.product_count = len(items)
        run.view_count = len(items)
        run.status = RunStatus.PARTIAL.value if metrics.get("unknown") else RunStatus.SUCCESS.value
    except Exception as exc:  # noqa: BLE001 - 运行失败留痕，不抛 500
        run.status = RunStatus.FAILED.value
        run.log_text = f"运行失败：{exc}"
        run.metrics = {"error": str(exc)[:300]}
    run.finished_at = utcnow()
    db.flush()
    return run


def create_and_execute(
    db: Session,
    *,
    trigger: str,
    operator_email: str,
    seed_key: str | None = None,
) -> YieldRun:
    if seed_key:
        existing = db.scalar(select(YieldRun).where(YieldRun.seed_key == seed_key))
        if existing is not None:
            return existing
    run = YieldRun(
        run_no=next_run_no(db),
        trigger=trigger,
        status=RunStatus.RUNNING.value,
        operator_email=operator_email,
        seed_key=seed_key,
    )
    db.add(run)
    db.flush()
    return execute(db, run)


def serialize_run(run: YieldRun) -> dict:
    return {
        "id": run.id,
        "run_no": run.run_no,
        "trigger": run.trigger,
        "trigger_label": TRIGGER_LABELS.get(run.trigger, run.trigger),
        "status": run.status,
        "status_label": RUN_STATUS_LABELS.get(run.status, run.status),
        "operator_email": run.operator_email,
        "product_count": run.product_count,
        "view_count": run.view_count,
        "metrics": run.metrics or {},
        "log_text": run.log_text,
        "started_at": iso_utc(run.started_at),
        "finished_at": iso_utc(run.finished_at),
    }


def list_runs(db: Session, *, status: str | None = None, limit: int = 20, offset: int = 0) -> dict:
    stmt = select(YieldRun)
    count_stmt = select(func.count()).select_from(YieldRun)
    if status:
        stmt = stmt.where(YieldRun.status == status)
        count_stmt = count_stmt.where(YieldRun.status == status)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(YieldRun.id.desc()).limit(limit).offset(offset)).all()
    return {"items": [serialize_run(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def get_run(db: Session, run_id: int) -> YieldRun:
    run = db.get(YieldRun, run_id)
    if run is None:
        raise AppError("NOT_FOUND", 404, {"entity": "yield_run", "id": run_id})
    return run


def serialize_view(view: YieldView, *, product: Product | None = None, run_no: str | None = None, hide_fee: bool = False) -> dict:
    group_type, _, bucket = (view.group_key or "").partition(":")
    flags = view.flags or {}
    return {
        "id": view.id,
        "run_id": view.run_id,
        "run_no": run_no,
        "product_id": view.product_id,
        "product_code": product.code if product else None,
        "product_name": product.name if product else None,
        "issuer": product.issuer if product else None,
        "type": product.type if product else None,
        "type_label": PRODUCT_TYPE_LABELS.get(product.type, product.type) if product else None,
        "risk_level": product.risk_level if product else None,
        "risk_label": RISK_LEVEL_LABELS.get(product.risk_level, product.risk_level) if product else None,
        "term_days": product.term_days if product else None,
        "term_bucket_label": TERM_BUCKET_LABELS.get(bucket, bucket) if bucket else None,
        "group_key": view.group_key,
        "group_label": f"{PRODUCT_TYPE_LABELS.get(group_type, group_type)} · {TERM_BUCKET_LABELS.get(bucket, bucket)}"
        if bucket
        else view.group_key,
        "group_size": view.group_size,
        "comparables": view.comparable_pct,
        "comparable_pct": view.comparable_pct,
        "method": view.method,
        "method_label": YIELD_METHOD_LABELS.get(view.method, view.method),
        "confidence": view.confidence,
        "confidence_label": CONFIDENCE_LABELS.get(view.confidence, view.confidence),
        "peer_rank": view.peer_rank,
        "risk_adj": view.risk_adj,
        "vol_annual": view.vol_annual,
        "fee_rate": None if hide_fee else (round(float(product.fee_rate or 0), 4) if product else None),
        "status": view.status,
        "status_label": REVIEW_STATUS_LABELS.get(view.status, view.status),
        "caveat": flags.get("caveat"),
        "tags": flags.get("tags") or [],
        "source_value": flags.get("source_value"),
        "reviewer": view.reviewer,
        "review_note": view.review_note,
        "created_at": iso_utc(view.created_at),
        "updated_at": iso_utc(view.updated_at),
    }


def _product_map(db: Session) -> dict[int, Product]:
    return {product.id: product for product in db.scalars(select(Product)).all()}


def _run_no_map(db: Session) -> dict[int, str]:
    return {run.id: run.run_no for run in db.scalars(select(YieldRun)).all()}


def list_views(
    db: Session,
    *,
    run_id: int | None = None,
    method: str | None = None,
    status: str | None = None,
    risk_level: str | None = None,
    group: str | None = None,
    q: str | None = None,
    ranked_only: bool = False,
    limit: int = 20,
    offset: int = 0,
    hide_fee: bool = False,
) -> dict:
    products = _product_map(db)
    run_nos = _run_no_map(db)
    stmt = select(YieldView)
    count_stmt = select(func.count()).select_from(YieldView)
    conditions = []
    if run_id:
        conditions.append(YieldView.run_id == run_id)
    if method:
        conditions.append(YieldView.method == method)
    if status:
        conditions.append(YieldView.status == status)
    if group:
        conditions.append(YieldView.group_key == group)
    if ranked_only:
        conditions.append(YieldView.peer_rank.is_not(None))
    if risk_level or q:
        matching = [product.id for product in products.values() if _match_product(product, risk_level, q)]
        if not matching:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}
        conditions.append(YieldView.product_id.in_(matching))
    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(YieldView.run_id.desc(), YieldView.peer_rank.is_(None), YieldView.peer_rank, YieldView.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return {
        "items": [
            serialize_view(
                row,
                product=products.get(row.product_id),
                run_no=run_nos.get(row.run_id),
                hide_fee=hide_fee,
            )
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _match_product(product: Product, risk_level: str | None, q: str | None) -> bool:
    if risk_level and product.risk_level != risk_level:
        return False
    if q:
        needle = q.strip().lower()
        haystack = f"{product.name} {product.code} {product.issuer}".lower()
        if needle and needle not in haystack:
            return False
    return True


def get_view(db: Session, view_id: int) -> dict:
    view = db.get(YieldView, view_id)
    if view is None:
        raise AppError("NOT_FOUND", 404, {"entity": "yield_view", "id": view_id})
    return serialize_view(
        view,
        product=db.get(Product, view.product_id),
        run_no=db.get(YieldRun, view.run_id).run_no if db.get(YieldRun, view.run_id) else None,
    )


def review(db: Session, view: YieldView, *, status: str, note: str | None, reviewer: str) -> YieldView:
    view.status = status
    view.review_note = note
    view.reviewer = reviewer
    view.updated_at = utcnow()
    db.flush()
    return view


def groups(db: Session, run_id: int | None = None, top_n: int = 10) -> dict:
    """对比榜：每个同类分组的前 N 名（含分组样本数与是否可排名）。"""
    latest = run_id
    if latest is None:
        latest_row = db.scalar(select(YieldRun).order_by(YieldRun.id.desc()).limit(1))
        latest = latest_row.id if latest_row else None
    if latest is None:
        return {"run_id": None, "items": []}
    products = _product_map(db)
    run_nos = _run_no_map(db)
    rows = db.scalars(
        select(YieldView).where(YieldView.run_id == latest).order_by(YieldView.comparable_pct.is_(None), YieldView.comparable_pct.desc())
    ).all()
    buckets: dict[str, list[YieldView]] = {}
    for row in rows:
        buckets.setdefault(row.group_key, []).append(row)
    type_order = {"cash": 0, "fixed": 1, "mixed": 2, "equity": 3}
    bucket_order = {"le30": 0, "d31_180": 1, "d181_365": 2, "gt365": 3, "unknown": 4}

    def _order(key: str) -> tuple[int, int, str]:
        group_type, _, bucket = key.partition(":")
        return (type_order.get(group_type, 9), bucket_order.get(bucket, 9), key)

    items = []
    for key, members in sorted(buckets.items(), key=lambda pair: _order(pair[0])):
        valid = [row for row in members if row.comparable_pct is not None]
        valid.sort(key=lambda row: (-float(row.comparable_pct), row.product_id))
        first = (valid or members)[0]
        group_type, _, bucket = key.partition(":")
        items.append(
            {
                "group_key": key,
                "group_label": f"{PRODUCT_TYPE_LABELS.get(group_type, group_type)} · {TERM_BUCKET_LABELS.get(bucket, bucket)}",
                "size": len(valid),
                "ranked": len(valid) >= yield_math.PEER_MIN_SAMPLE,
                "top": [
                    serialize_view(row, product=products.get(row.product_id), run_no=run_nos.get(row.run_id))
                    for row in valid[:top_n]
                ],
            }
        )
    return {"run_id": latest, "items": items}


def refresh_daily(db: Session, operator_email: str) -> YieldRun:
    """worker 定时任务入口：按当前报价重算一次口径。"""
    return create_and_execute(db, trigger="schedule", operator_email=operator_email)

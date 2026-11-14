"""导出服务：对比榜、报价流水、换算运行记录（UTF-8 BOM CSV）。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.constants.enums import (
    CONFIDENCE_LABELS,
    PRODUCT_TYPE_LABELS,
    QUOTE_SOURCE_LABELS,
    REVIEW_STATUS_LABELS,
    RISK_LEVEL_LABELS,
    RUN_STATUS_LABELS,
    TERM_BUCKET_LABELS,
    TRIGGER_LABELS,
    YIELD_METHOD_LABELS,
)
from src.models.product import Product
from src.models.quote import Quote
from src.models.yield_run import YieldRun
from src.models.yield_view import YieldView
from src.utils.csv_export import to_csv


def _fmt(value: float | None, digits: int = 2) -> str:
    return "" if value is None else f"{float(value):.{digits}f}"


def views_csv(db: Session, run_id: int | None = None) -> bytes:
    products = {product.id: product for product in db.scalars(select(Product)).all()}
    run_nos = {run.id: run.run_no for run in db.scalars(select(YieldRun)).all()}
    stmt = select(YieldView)
    if run_id:
        stmt = stmt.where(YieldView.run_id == run_id)
    views = db.scalars(stmt.order_by(YieldView.run_id, YieldView.id)).all()
    headers = [
        "运行编号",
        "产品编码",
        "产品名称",
        "发行机构",
        "产品类型",
        "风险等级",
        "期限(天)",
        "期限档",
        "可比年化(%)",
        "换算口径",
        "置信度",
        "同类排名",
        "分组样本",
        "年化波动(%)",
        "风险调整",
        "复核状态",
        "复核人",
        "复核备注",
    ]
    rows = []
    for view in views:
        product = products.get(view.product_id)
        flags = view.flags or {}
        group_type, _, bucket = (view.group_key or "").partition(":")
        rows.append(
            [
                run_nos.get(view.run_id, ""),
                product.code if product else "",
                product.name if product else "",
                product.issuer if product else "",
                PRODUCT_TYPE_LABELS.get(product.type, product.type) if product else "",
                RISK_LEVEL_LABELS.get(product.risk_level, product.risk_level) if product else "",
                product.term_days if product else "",
                TERM_BUCKET_LABELS.get(bucket, bucket),
                _fmt(view.comparable_pct, 4),
                YIELD_METHOD_LABELS.get(view.method, view.method),
                CONFIDENCE_LABELS.get(view.confidence, view.confidence),
                view.peer_rank or "",
                view.group_size or "",
                _fmt(view.vol_annual, 4),
                _fmt(view.risk_adj, 3),
                REVIEW_STATUS_LABELS.get(view.status, view.status),
                view.reviewer or "",
                view.review_note or flags.get("caveat", ""),
            ]
        )
    return to_csv(headers, rows)


def quotes_csv(db: Session) -> bytes:
    products = {product.id: product for product in db.scalars(select(Product)).all()}
    quotes = db.scalars(select(Quote).order_by(Quote.quote_date, Quote.product_id)).all()
    headers = [
        "产品编码",
        "产品名称",
        "报价日",
        "单位净值",
        "七日年化(%)",
        "万份收益",
        "基准下限(%)",
        "基准上限(%)",
        "近1年年化(%)",
        "来源",
    ]
    rows = [
        [
            products[quote.product_id].code if quote.product_id in products else "",
            products[quote.product_id].name if quote.product_id in products else "",
            quote.quote_date.isoformat(),
            "" if quote.nav is None else f"{quote.nav:.4f}",
            _fmt(quote.seven_day_pct, 2),
            _fmt(quote.wanfen_yield, 4),
            _fmt(quote.bench_low, 2),
            _fmt(quote.bench_high, 2),
            _fmt(quote.year_pct, 2),
            QUOTE_SOURCE_LABELS.get(quote.source, quote.source),
        ]
        for quote in quotes
    ]
    return to_csv(headers, rows)


def runs_csv(db: Session) -> bytes:
    runs = db.scalars(select(YieldRun).order_by(YieldRun.id)).all()
    headers = ["运行编号", "触发方式", "状态", "产品数", "结果数", "操作人", "开始时间", "结束时间"]
    rows = [
        [
            run.run_no,
            TRIGGER_LABELS.get(run.trigger, run.trigger),
            RUN_STATUS_LABELS.get(run.status, run.status),
            run.product_count,
            run.view_count,
            run.operator_email,
            run.started_at.strftime("%Y-%m-%d %H:%M") if run.started_at else "",
            run.finished_at.strftime("%Y-%m-%d %H:%M") if run.finished_at else "",
        ]
        for run in runs
    ]
    return to_csv(headers, rows)

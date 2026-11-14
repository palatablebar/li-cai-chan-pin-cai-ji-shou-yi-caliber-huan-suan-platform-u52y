"""幂等 seed：3 账号 / 68 只产品 / 340 条报价 / 12 条关注 / 1 次换算运行 → 68 条结果。

自然键 upsert：
  users.email
  products.code
  quotes(product_id, quote_date)
  watches(product_id, kind)
  yield_runs.seed_key
  yield_views(run_id, product_id)   —— 只刷新算法字段，不覆盖人工复核状态
  ingest_batches(institution, batch_key)  —— 演示批次已存在则整批跳过，不覆盖人工补齐/确认
  audit_logs.seed_key

重复执行不新增、不改写人工复核，SEED_SUMMARY 逐字一致（键名与顺序按 batch-plan 固定契约）。
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select

from src.config.database import session_scope
from src.models.audit import AuditLog
from src.models.ingest import IngestBatch
from src.models.product import Product
from src.models.quote import Quote
from src.models.user import User
from src.models.watch import Watch
from src.models.yield_run import YieldRun
from src.models.yield_view import YieldView
from src.services import ingest_service, yield_service
from src.utils.security import hash_password
from src.utils.timeutil import local_now

from scripts.demo_config import (
    DEMO_PASSWORD,
    DEMO_USERS,
    ORG,
    PRODUCTS,
    QUOTES,
    WATCH_SPECS,
)


def ensure_users(db) -> int:
    for email, display_name, role in DEMO_USERS:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            db.add(
                User(
                    email=email,
                    password_hash=hash_password(DEMO_PASSWORD),
                    display_name=display_name,
                    role=role,
                    org=ORG,
                )
            )
    db.flush()
    return db.scalar(select(func.count()).select_from(User)) or 0


def ensure_products(db) -> int:
    for spec in PRODUCTS:
        product = db.scalar(select(Product).where(Product.code == spec["code"]))
        if product is None:
            db.add(
                Product(
                    code=spec["code"],
                    name=spec["name"],
                    issuer=spec["issuer"],
                    type=spec["type"],
                    risk_level=spec["risk_level"],
                    min_amount=spec["min_amount"],
                    term_days=spec["term_days"],
                    fee_rate=spec["fee_rate"],
                    active=True,
                    note=spec["note"],
                )
            )
    db.flush()
    return db.scalar(select(func.count()).select_from(Product)) or 0


def ensure_quotes(db) -> int:
    codes = {product.code: product.id for product in db.scalars(select(Product)).all()}
    existing = {
        (quote.product_id, quote.quote_date)
        for quote in db.scalars(select(Quote)).all()
    }
    added = 0
    for row in QUOTES:
        product_id = codes.get(row["product_code"])
        if product_id is None:
            continue
        key = (product_id, row["quote_date"])
        if key in existing:
            continue
        db.add(
            Quote(
                product_id=product_id,
                quote_date=row["quote_date"],
                nav=row["nav"],
                seven_day_pct=row["seven_day_pct"],
                wanfen_yield=row["wanfen_yield"],
                bench_low=row["bench_low"],
                bench_high=row["bench_high"],
                year_pct=row["year_pct"],
                source=row["source"],
            )
        )
        existing.add(key)
        added += 1
    db.flush()
    return len(existing) if added else (db.scalar(select(func.count()).select_from(Quote)) or 0)


def ensure_watches(db) -> int:
    codes = {product.code: product.id for product in db.scalars(select(Product)).all()}
    today = local_now().date()
    for code, kind, offset, status, note in WATCH_SPECS:
        product_id = codes.get(code)
        if product_id is None:
            continue
        exists = db.scalar(select(Watch).where(Watch.product_id == product_id, Watch.kind == kind))
        if exists is not None:
            continue
        db.add(
            Watch(
                product_id=product_id,
                kind=kind,
                due_on=date.fromordinal(today.toordinal() + offset),
                status=status,
                note=note,
                owner=ORG,
            )
        )
    db.flush()
    return db.scalar(select(func.count()).select_from(Watch)) or 0


def ensure_run(db) -> int:
    run = db.scalar(select(YieldRun).where(YieldRun.seed_key == "seed-yield-run-1"))
    if run is None:
        yield_service.create_and_execute(
            db,
            trigger="seed",
            operator_email="system@yieldbook.io",
            seed_key="seed-yield-run-1",
        )
    return db.scalar(select(func.count()).select_from(YieldRun)) or 0


SEED_INGEST_INSTITUTION = "华信理财"
SEED_INGEST_BATCH_KEY = "seed-ingest-2026-11-13"


def _ingest_row(product: Product, **overrides) -> dict:
    row = {
        "inst_code": product.code,
        "name": product.name,
        "product_type": product.type,
        "risk_level": product.risk_level,
        "min_amount": float(product.min_amount),
        "term_days": product.term_days,
        "fee_rate": float(product.fee_rate),
    }
    row.update(overrides)
    return row


def ensure_ingest(db) -> None:
    """演示一批机构采集：合入 / 待确认 / 待补 全覆盖，且演示两家机构重码。

    全部锚定现有产品或不完整行，不新增产品主档，保证 SEED_SUMMARY 契约不变；
    批次已存在则整批跳过，不覆盖人工补齐与确认。
    """
    exists = db.scalar(
        select(IngestBatch).where(
            IngestBatch.institution == SEED_INGEST_INSTITUTION,
            IngestBatch.batch_key == SEED_INGEST_BATCH_KEY,
        )
    )
    if exists is not None:
        return
    products = {product.code: product for product in db.scalars(select(Product)).all()}
    merged_target = products.get("yb003")    # 华信理财 · 江城天天增
    conflict_target = products.get("yb011")  # 华信理财 · 江城聚宝盆
    if merged_target is None or conflict_target is None:
        return
    rows = [
        # 要素与目录一致 → 合入（认领存量产品，不新建）
        _ingest_row(merged_target),
        # 同一只产品、风险等级与起购金额不一致 → 待确认（保留来源，列出差异）
        _ingest_row(conflict_target, risk_level="R2", min_amount=1000.0),
        # 缺起购金额 → 待补
        {
            "inst_code": "HX1001",
            "name": "华信稳利 180 天",
            "product_type": "fixed",
            "risk_level": "R2",
            "term_days": 180,
            "fee_rate": 0.3,
        },
        # 缺风险等级 → 待补
        {
            "inst_code": "HX1002",
            "name": "华信日日升",
            "product_type": "cash",
            "min_amount": 1000.0,
            "term_days": 0,
            "fee_rate": 0.1,
        },
        # 机构间重码：华信理财也有一只 yb001（江城银行的 yb001 不受影响），要素不全 → 待补
        {
            "inst_code": "yb001",
            "name": "华信现金管理 1 号",
            "product_type": "cash",
            "min_amount": 10000.0,
        },
    ]
    ingest_service.submit_batch(
        db,
        institution=SEED_INGEST_INSTITUTION,
        batch_key=SEED_INGEST_BATCH_KEY,
        rows=rows,
        operator_email="system@yieldbook.io",
        note="seed 演示批次：合入 1 · 待确认 1 · 待补 3",
    )


def ensure_audit(db) -> None:
    seeds = [
        ("seed-audit-1", "admin@yieldbook.io", "admin", "product.create", "product", {"code": "yb001"}),
        ("seed-audit-2", "analyst@yieldbook.io", "analyst", "quote.import", "quote", {"rows": 340}),
        ("seed-audit-3", "system@yieldbook.io", "admin", "yield.run", "yield_run", {"run": "seed-yield-run-1"}),
        (
            "seed-audit-4",
            "system@yieldbook.io",
            "admin",
            "ingest.submit",
            "ingest_batch",
            {"institution": SEED_INGEST_INSTITUTION, "batch_key": SEED_INGEST_BATCH_KEY, "rows": 5},
        ),
    ]
    for seed_key, email, role, action, entity, detail in seeds:
        exists = db.scalar(select(AuditLog).where(AuditLog.seed_key == seed_key))
        if exists is None:
            db.add(
                AuditLog(
                    actor_email=email,
                    actor_role=role,
                    action=action,
                    entity=entity,
                    detail=detail,
                    layer="seed",
                    seed_key=seed_key,
                )
            )
    db.flush()


def seed_all() -> dict:
    with session_scope() as db:
        users = ensure_users(db)
        products = ensure_products(db)
        quotes = ensure_quotes(db)
        watches = ensure_watches(db)
        ensure_ingest(db)
        runs = ensure_run(db)
        ensure_audit(db)
        views = db.scalar(select(func.count()).select_from(YieldView)) or 0
        pending = db.scalar(select(func.count()).select_from(YieldView).where(YieldView.status == "pending")) or 0
        # 固定契约（batch-plan）：sources=产品主档数，findings=换算结果数
        summary = (
            f"SEED_SUMMARY brand=yieldbook users={users} sources={products} "
            f"runs={runs} findings={views} pending={pending}"
        )
        print(summary, flush=True)
        print(
            f"SEED_DETAIL products={products} quotes={quotes} watches={watches} "
            f"yield_runs={runs} yield_views={views}",
            flush=True,
        )
        return {
            "users": users,
            "products": products,
            "quotes": quotes,
            "watches": watches,
            "runs": runs,
            "views": views,
            "pending": pending,
        }


if __name__ == "__main__":
    seed_all()

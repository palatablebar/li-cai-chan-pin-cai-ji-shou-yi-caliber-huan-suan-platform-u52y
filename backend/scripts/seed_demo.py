"""幂等 seed：3 账号 / 68 只产品 / 340 条报价 / 12 条关注 / 1 次换算运行 → 68 条结果。

自然键 upsert：
  users.email
  products.code
  quotes(product_id, quote_date)
  watches(product_id, kind)
  yield_runs.seed_key
  yield_views(run_id, product_id)   —— 只刷新算法字段，不覆盖人工复核状态
  audit_logs.seed_key

重复执行不新增、不改写人工复核，SEED_SUMMARY 逐字一致（键名与顺序按 batch-plan 固定契约）。
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select

from src.config.database import session_scope
from src.models.audit import AuditLog
from src.models.product import Product
from src.models.quote import Quote
from src.models.user import User
from src.models.watch import Watch
from src.models.yield_run import YieldRun
from src.models.yield_view import YieldView
from src.services import yield_service
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


def ensure_audit(db) -> None:
    seeds = [
        ("seed-audit-1", "admin@yieldbook.io", "admin", "product.create", "product", {"code": "yb001"}),
        ("seed-audit-2", "analyst@yieldbook.io", "analyst", "quote.import", "quote", {"rows": 340}),
        ("seed-audit-3", "system@yieldbook.io", "admin", "yield.run", "yield_run", {"run": "seed-yield-run-1"}),
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

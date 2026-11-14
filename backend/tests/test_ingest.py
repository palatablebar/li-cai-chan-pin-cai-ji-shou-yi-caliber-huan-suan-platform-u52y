"""机构批量采集：按（机构, 机构编码）识别、幂等重试、待补/待确认/确认状态机、上榜闸门。"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.models import Base, Product
from src.models.ingest import IngestBatch, ProductSource, SourceRecord
from src.services import ingest_service, yield_service
from src.utils.errors import AppError


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _row(inst_code="ZX100", **overrides) -> dict:
    row = {
        "inst_code": inst_code,
        "name": "中盈稳利 90 天",
        "product_type": "fixed",
        "risk_level": "R2",
        "min_amount": 10000.0,
        "term_days": 90,
        "fee_rate": 0.3,
    }
    row.update(overrides)
    return row


def _submit(db, institution="中盈基金", batch_key="2026-11-14-01", rows=None, **kwargs):
    return ingest_service.submit_batch(
        db,
        institution=institution,
        batch_key=batch_key,
        rows=rows if rows is not None else [_row()],
        operator_email="analyst@yieldbook.io",
        **kwargs,
    )


def _count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


# ---------------- 缺失要素：逐字段列出，不静默跳过 ----------------
def test_missing_fields_are_listed_per_record(db):
    result = _submit(db, rows=[_row(min_amount=None, risk_level=None)])
    record = db.scalar(select(SourceRecord))
    assert record.status == "pending"
    assert record.missing_fields == ["risk_level", "min_amount"]
    assert record.product_id is None
    assert _count(db, Product) == 0  # 待补不建产品
    assert result["batch"]["counts"]["pending"] == 1


def test_row_without_inst_code_is_rejected_with_reason(db):
    result = _submit(db, rows=[_row(inst_code=None), _row()])
    assert len(result["rejected"]) == 1
    assert result["rejected"][0]["row_no"] == 1
    assert "机构编码" in result["rejected"][0]["reason"]
    assert _count(db, SourceRecord) == 1  # 另一行正常接收


def test_invalid_enum_value_goes_pending_with_invalid_flag(db):
    _submit(db, rows=[_row(risk_level="R9")])
    db.expire_all()  # 重新从库里加载，确认非法标记已持久化
    record = db.scalar(select(SourceRecord))
    assert record.status == "pending"
    assert record.invalid_fields == ["risk_level"]
    assert record.missing_fields == []


# ---------------- 按（机构, 机构编码）识别：两家机构同码各自成行 ----------------
def test_same_code_two_institutions_create_separate_products(db):
    _submit(db, institution="中盈基金", rows=[_row("ZX100")])
    _submit(db, institution="华信理财", rows=[_row("ZX100", name="华信稳利 90 天")])
    products = db.scalars(select(Product).order_by(Product.id)).all()
    assert len(products) == 2
    assert products[0].issuer == "中盈基金"
    assert products[1].issuer == "华信理财"
    assert products[0].code != products[1].code
    sources = db.scalars(select(ProductSource).order_by(ProductSource.id)).all()
    assert {(s.institution, s.inst_code) for s in sources} == {("中盈基金", "ZX100"), ("华信理财", "ZX100")}
    # 采集新建的产品都未上榜
    assert all(product.listed is False for product in products)


def test_second_institution_record_is_not_attached_to_first_product(db):
    """复现原始缺陷：同码后到记录既不能被拒，也不能挂到另一家产品上。"""
    _submit(db, institution="中盈基金", rows=[_row("ZX100")])
    first_product = db.scalar(select(Product))
    result = _submit(db, institution="华信理财", rows=[_row("ZX100")])
    record = db.scalar(select(SourceRecord).where(SourceRecord.institution == "华信理财"))
    assert record.status == "merged"
    assert record.product_id != first_product.id
    assert result["batch"]["counts"]["merged"] == 1


def test_existing_product_same_issuer_is_claimed_not_duplicated(db):
    """目录里已有「发行机构 = 机构 且 编码相同」的产品时，认领而不是新建。"""
    db.add(
        Product(
            code="ZX100",
            name="中盈稳利 90 天",
            issuer="中盈基金",
            type="fixed",
            risk_level="R2",
            min_amount=10000.0,
            term_days=90,
            fee_rate=0.3,
        )
    )
    db.flush()
    _submit(db, institution="中盈基金", rows=[_row("ZX100", name="中盈稳利 90 天")])
    record = db.scalar(select(SourceRecord))
    assert record.status == "merged"
    assert _count(db, Product) == 1  # 没有新建产品


def test_same_issuer_same_code_but_different_issuer_product_untouched(db):
    """目录里同码产品属于另一家机构时，绝不认领，新建未上榜产品。"""
    db.add(
        Product(
            code="ZX100",
            name="江城稳利 90 天",
            issuer="江城银行",
            type="fixed",
            risk_level="R2",
            min_amount=10000.0,
            term_days=90,
            fee_rate=0.3,
        )
    )
    db.flush()
    _submit(db, institution="中盈基金", rows=[_row("ZX100")])
    products = db.scalars(select(Product).order_by(Product.id)).all()
    assert len(products) == 2
    assert products[0].issuer == "江城银行"
    assert products[1].issuer == "中盈基金"
    assert products[1].listed is False


# ---------------- 幂等重试：不新增、不丢失、不改写已确认 ----------------
def test_retry_same_batch_is_idempotent(db):
    first = _submit(db, rows=[_row("ZX100"), _row("ZX101", name="中盈添利 60 天", term_days=60)])
    second = _submit(db, rows=[_row("ZX100"), _row("ZX101", name="中盈添利 60 天", term_days=60)])
    assert second["reused"] is True
    assert second["created"] == 0
    assert _count(db, IngestBatch) == 1
    assert _count(db, SourceRecord) == 2
    assert _count(db, Product) == 2
    assert first["batch"]["id"] == second["batch"]["id"]


def test_retry_with_completed_file_merges_pending_record(db):
    _submit(db, rows=[_row("ZX100", min_amount=None)])
    record = db.scalar(select(SourceRecord))
    assert record.status == "pending"
    _submit(db, rows=[_row("ZX100")])  # 同一批重发，这次带齐了起购金额
    db.expire_all()
    record = db.scalar(select(SourceRecord))
    assert record.status == "merged"
    assert _count(db, SourceRecord) == 1
    assert _count(db, Product) == 1


def test_retry_keeps_confirmed_record_and_review(db):
    _submit(db, rows=[_row("ZX100")])
    record = db.scalar(select(SourceRecord))
    ingest_service.confirm_record(db, record.id, reviewer="admin@yieldbook.io", note="要素无误")
    result = _submit(db, rows=[_row("ZX100", name="被改名 90 天")])
    assert result["kept_confirmed"] == 1
    db.expire_all()
    record = db.scalar(select(SourceRecord))
    assert record.status == "confirmed"
    assert record.reviewer == "admin@yieldbook.io"
    assert record.review_note == "要素无误"
    product = db.scalar(select(Product))
    assert product.name == "中盈稳利 90 天"  # 已确认记录不被批次重试改写


def test_retry_does_not_drop_records_absent_from_payload(db):
    _submit(db, rows=[_row("ZX100"), _row("ZX101", name="中盈添利 60 天", term_days=60)])
    _submit(db, rows=[_row("ZX100")])  # 重试只带一行
    assert _count(db, SourceRecord) == 2  # 另一条记录不丢失


def test_duplicate_inst_code_in_one_file_last_wins(db):
    result = _submit(db, rows=[_row("ZX100", min_amount=None), _row("ZX100")])
    assert _count(db, SourceRecord) == 1  # 同批同码只留一条，后行覆盖前行
    record = db.scalar(select(SourceRecord))
    assert record.status == "merged"
    assert result["created"] == 1 and result["updated"] == 1


# ---------------- 冲突：保留来源、列出待确认内容 ----------------
def _seed_catalog_product(db) -> Product:
    product = Product(
        code="ZX100",
        name="中盈稳利 90 天",
        issuer="中盈基金",
        type="fixed",
        risk_level="R2",
        min_amount=10000.0,
        term_days=90,
        fee_rate=0.3,
    )
    db.add(product)
    db.flush()
    return product


def test_conflict_keeps_source_and_lists_diffs(db):
    product = _seed_catalog_product(db)
    _submit(db, institution="中盈基金", rows=[_row("ZX100", name="中盈稳利 90 天", risk_level="R3", min_amount=50000.0)])
    record = db.scalar(select(SourceRecord))
    assert record.status == "conflict"
    diffs = {item["field"]: item for item in record.conflict_fields}
    assert set(diffs) == {"risk_level", "min_amount"}
    assert diffs["risk_level"] == {"field": "risk_level", "existing": "R2", "incoming": "R3"}
    assert diffs["min_amount"]["existing"] == 10000.0
    assert diffs["min_amount"]["incoming"] == 50000.0
    db.refresh(product)
    assert product.risk_level == "R2"  # 确认前不改写正式目录
    assert record.payload["risk_level"] == "R3"  # 来源值保留在记录里


def test_conflict_confirm_requires_resolution(db):
    _seed_catalog_product(db)
    _submit(db, institution="中盈基金", rows=[_row("ZX100", name="中盈稳利 90 天", risk_level="R3")])
    record = db.scalar(select(SourceRecord))
    with pytest.raises(AppError) as excinfo:
        ingest_service.confirm_record(db, record.id, reviewer="admin@yieldbook.io")
    assert excinfo.value.code == "VALIDATION"


def test_conflict_confirm_keep_existing(db):
    product = _seed_catalog_product(db)
    _submit(db, institution="中盈基金", rows=[_row("ZX100", name="中盈稳利 90 天", risk_level="R3")])
    record = db.scalar(select(SourceRecord))
    ingest_service.confirm_record(db, record.id, reviewer="admin@yieldbook.io", resolution="keep_existing")
    db.refresh(product)
    assert product.risk_level == "R2"
    assert record.status == "confirmed"
    assert record.confirmed_at is not None


def test_conflict_confirm_use_incoming(db):
    product = _seed_catalog_product(db)
    _submit(db, institution="中盈基金", rows=[_row("ZX100", name="中盈稳利 90 天", risk_level="R3")])
    record = db.scalar(select(SourceRecord))
    ingest_service.confirm_record(db, record.id, reviewer="admin@yieldbook.io", resolution="use_incoming")
    db.refresh(product)
    assert product.risk_level == "R3"
    assert record.status == "confirmed"


# ---------------- 补齐 + 确认 -> 进入正式对比榜 ----------------
def test_complete_then_confirm_lists_product(db):
    _submit(db, rows=[_row("ZX100", min_amount=None, risk_level=None)])
    record = db.scalar(select(SourceRecord))
    with pytest.raises(AppError) as excinfo:
        ingest_service.confirm_record(db, record.id, reviewer="admin@yieldbook.io")
    assert excinfo.value.code == "VALIDATION"  # 待补不能确认

    ingest_service.complete_record(db, record.id, {"risk_level": "R2", "min_amount": 10000.0})
    db.expire_all()
    record = db.scalar(select(SourceRecord))
    assert record.status == "merged"
    product = db.scalar(select(Product))
    assert product.listed is False  # 合入但未确认，仍不上榜

    ingest_service.confirm_record(db, record.id, reviewer="admin@yieldbook.io", note="已电话核实")
    db.refresh(product)
    assert product.listed is True
    assert record.reviewer == "admin@yieldbook.io"


def test_complete_confirmed_record_is_rejected(db):
    _submit(db, rows=[_row("ZX100")])
    record = db.scalar(select(SourceRecord))
    ingest_service.confirm_record(db, record.id, reviewer="admin@yieldbook.io")
    with pytest.raises(AppError) as excinfo:
        ingest_service.complete_record(db, record.id, {"fee_rate": 0.5})
    assert excinfo.value.code == "CONFLICT"


def test_double_confirm_is_idempotent(db):
    _submit(db, rows=[_row("ZX100")])
    record = db.scalar(select(SourceRecord))
    ingest_service.confirm_record(db, record.id, reviewer="admin@yieldbook.io", note="第一次")
    again = ingest_service.confirm_record(db, record.id, reviewer="other@yieldbook.io", note="第二次")
    assert again.reviewer == "admin@yieldbook.io"  # 不改写已有复核


# ---------------- 上榜闸门：换算运行只取 listed 产品 ----------------
def test_unlisted_products_excluded_from_yield_run(db):
    db.add(
        Product(
            code="yb001", name="江城现金宝", issuer="江城银行", type="cash",
            risk_level="R1", min_amount=100.0, term_days=1, fee_rate=0.1, listed=True,
        )
    )
    db.add(
        Product(
            code="ig0001", name="采集待确认", issuer="中盈基金", type="fixed",
            risk_level="R2", min_amount=10000.0, term_days=90, fee_rate=0.3, listed=False,
        )
    )
    db.flush()
    items = yield_service.compute_items(db)
    codes = {item["product_code"] for item in items}
    assert codes == {"yb001"}


def test_full_ingest_flow_lands_in_yield_run(db):
    """采集 -> 补齐 -> 确认 之后，产品才会出现在换算结果里。"""
    _submit(db, rows=[_row("ZX100", min_amount=None)])
    assert yield_service.compute_items(db) == []
    record = db.scalar(select(SourceRecord))
    ingest_service.complete_record(db, record.id, {"min_amount": 10000.0})
    assert yield_service.compute_items(db) == []  # 未确认仍不上榜
    ingest_service.confirm_record(db, record.id, reviewer="admin@yieldbook.io")
    items = yield_service.compute_items(db)
    assert len(items) == 1
    assert items[0]["issuer"] == "中盈基金"

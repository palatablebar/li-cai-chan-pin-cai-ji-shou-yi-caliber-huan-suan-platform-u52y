"""机构批量采集服务：按（机构, 机构编码）识别来源记录，幂等接收、合入、补齐与确认。

要点：
- 同一机构同一 batch_key 只建一个批次；重试同一批不新增记录、不丢失已有记录与复核；
- 机构编码只在机构内唯一：两家机构同码各自映射到各自的产品，绝不互挂；
- 要素缺失（起购金额 / 风险等级等）进入「待补」，逐字段列出，不静默跳过；
- 同一只产品要素不一致进入「待确认」，保留来源值并列出差异，确认前不改写正式目录；
- 确认后产品才 listed=True，进入正式对比榜（换算运行只取 listed 产品）。
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.constants.enums import (
    INGEST_BATCH_STATUS_LABELS,
    INGEST_STATUS_LABELS,
    PRODUCT_TYPE_LABELS,
    RISK_LEVEL_LABELS,
    IngestBatchStatus,
    IngestStatus,
)
from src.models.ingest import IngestBatch, ProductSource, SourceRecord
from src.models.product import Product
from src.utils.errors import AppError, not_found
from src.utils.timeutil import iso_utc, local_now, utcnow

# 进入正式目录前必须齐全的要素；term_days / fee_rate 允许缺省（0 天 = 期限未知档）
REQUIRED_FIELDS = ("name", "product_type", "risk_level", "min_amount")
ELEMENT_FIELDS = ("name", "product_type", "risk_level", "min_amount", "term_days", "fee_rate")
FIELD_LABELS = {
    "name": "产品名称",
    "product_type": "产品类型",
    "risk_level": "风险等级",
    "min_amount": "起购金额",
    "term_days": "期限（天）",
    "fee_rate": "销售费率",
}
VALID_TYPES = set(PRODUCT_TYPE_LABELS)
VALID_RISKS = set(RISK_LEVEL_LABELS)
CONFLICT_RESOLUTIONS = ("use_incoming", "keep_existing")


# ---------------- 序列化 ----------------
def serialize_record(record: SourceRecord, *, product: Product | None = None) -> dict:
    conflicts = [
        {
            "field": item.get("field"),
            "field_label": FIELD_LABELS.get(item.get("field"), item.get("field")),
            "existing": item.get("existing"),
            "incoming": item.get("incoming"),
        }
        for item in (record.conflict_fields or [])
    ]
    return {
        "id": record.id,
        "batch_id": record.batch_id,
        "row_no": record.row_no,
        "institution": record.institution,
        "inst_code": record.inst_code,
        "name": record.name,
        "product_type": record.product_type,
        "product_type_label": PRODUCT_TYPE_LABELS.get(record.product_type, record.product_type),
        "risk_level": record.risk_level,
        "risk_label": RISK_LEVEL_LABELS.get(record.risk_level, record.risk_level),
        "min_amount": record.min_amount,
        "term_days": record.term_days,
        "fee_rate": record.fee_rate,
        "status": record.status,
        "status_label": INGEST_STATUS_LABELS.get(record.status, record.status),
        "missing_fields": list(record.missing_fields or []),
        "invalid_fields": list(record.invalid_fields or []),
        "missing_labels": [FIELD_LABELS.get(field, field) for field in (record.missing_fields or [])],
        "invalid_labels": [FIELD_LABELS.get(field, field) for field in (record.invalid_fields or [])],
        "conflict_fields": conflicts,
        "product_id": record.product_id,
        "product_code": product.code if product else None,
        "product_name": product.name if product else None,
        "product_listed": product.listed if product else None,
        "reviewer": record.reviewer,
        "review_note": record.review_note,
        "confirmed_at": iso_utc(record.confirmed_at),
        "payload": record.payload or {},
        "created_at": iso_utc(record.created_at),
        "updated_at": iso_utc(record.updated_at),
    }


def _status_counts(db: Session, batch_id: int) -> dict:
    rows = db.execute(
        select(SourceRecord.status, func.count()).where(SourceRecord.batch_id == batch_id).group_by(SourceRecord.status)
    ).all()
    counts = {status.value: 0 for status in IngestStatus}
    for status, count in rows:
        counts[status] = count
    return counts


def serialize_batch(db: Session, batch: IngestBatch) -> dict:
    counts = _status_counts(db, batch.id)
    return {
        "id": batch.id,
        "batch_no": batch.batch_no,
        "institution": batch.institution,
        "batch_key": batch.batch_key,
        "status": batch.status,
        "status_label": INGEST_BATCH_STATUS_LABELS.get(batch.status, batch.status),
        "row_count": batch.row_count,
        "received": sum(counts.values()),
        "counts": counts,
        "rejected": list(batch.rejected or []),
        "operator_email": batch.operator_email,
        "note": batch.note,
        "created_at": iso_utc(batch.created_at),
        "updated_at": iso_utc(batch.updated_at),
    }


# ---------------- 批次接收（幂等） ----------------
def _next_batch_no(db: Session) -> str:
    prefix = f"IB{local_now():%Y%m%d}"
    count = db.scalar(select(func.count()).select_from(IngestBatch).where(IngestBatch.batch_no.like(f"{prefix}%"))) or 0
    return f"{prefix}-{count + 1:04d}"


def _next_ingest_code(db: Session) -> str:
    """机构采集新建产品的目录编码：ig 开头顺序号，与人工登记的 yb 编码区分开。"""
    seq = db.scalar(select(func.count()).select_from(Product).where(Product.code.like("ig%"))) or 0
    while True:
        seq += 1
        code = f"ig{seq:04d}"
        if db.scalar(select(Product).where(Product.code == code)) is None:
            return code


def _missing_fields(record: SourceRecord) -> list[str]:
    missing = []
    for field in REQUIRED_FIELDS:
        value = getattr(record, field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return missing


def _invalid_fields(record: SourceRecord) -> list[str]:
    invalid = []
    if record.product_type and record.product_type not in VALID_TYPES:
        invalid.append("product_type")
    if record.risk_level and record.risk_level not in VALID_RISKS:
        invalid.append("risk_level")
    return invalid


def _diff_product(product: Product, record: SourceRecord) -> list[dict]:
    """同一只产品的要素差异：保留两边取值，确认前不改写正式目录。"""
    pairs = [
        ("name", product.name, record.name),
        ("product_type", product.type, record.product_type),
        ("risk_level", product.risk_level, record.risk_level),
        ("min_amount", float(product.min_amount or 0), float(record.min_amount or 0)),
        ("term_days", int(product.term_days or 0), int(record.term_days or 0)),
        ("fee_rate", float(product.fee_rate or 0), float(record.fee_rate or 0)),
    ]
    diffs = []
    for field, existing, incoming in pairs:
        if isinstance(existing, float) or isinstance(incoming, float):
            same = abs(float(existing) - float(incoming)) < 1e-9
        else:
            same = existing == incoming
        if not same:
            diffs.append({"field": field, "existing": existing, "incoming": incoming})
    return diffs


def _resolve_product(db: Session, record: SourceRecord) -> Product:
    """（机构, 机构编码）-> 正式产品：先查映射，再按「发行机构 = 机构 且 目录编码 = 机构编码」
    认领存量产品，否则新建未上榜产品。另一家机构的同码产品绝不会被认领。"""
    mapping = db.scalar(
        select(ProductSource).where(
            ProductSource.institution == record.institution,
            ProductSource.inst_code == record.inst_code,
        )
    )
    if mapping is not None:
        product = db.get(Product, mapping.product_id)
        if product is not None:
            return product
    product = db.scalar(
        select(Product).where(Product.code == record.inst_code, Product.issuer == record.institution)
    )
    if product is None:
        product = Product(
            code=_next_ingest_code(db),
            name=record.name,
            issuer=record.institution,
            type=record.product_type,
            risk_level=record.risk_level,
            min_amount=float(record.min_amount or 0),
            term_days=int(record.term_days or 0),
            fee_rate=float(record.fee_rate or 0),
            active=True,
            listed=False,
            note=f"机构采集 {record.institution} · {record.inst_code}，待确认入榜",
        )
        db.add(product)
        db.flush()
    db.add(ProductSource(product_id=product.id, institution=record.institution, inst_code=record.inst_code))
    db.flush()
    return product


def _evaluate(db: Session, record: SourceRecord) -> None:
    """按当前要素重算记录状态（confirmed 记录由调用方保证不进入）。"""
    record.missing_fields = _missing_fields(record)
    record.invalid_fields = _invalid_fields(record)
    record.conflict_fields = []
    if record.missing_fields or record.invalid_fields:
        record.status = IngestStatus.PENDING.value
        return
    product = _resolve_product(db, record)
    record.product_id = product.id
    diffs = _diff_product(product, record)
    if diffs:
        record.status = IngestStatus.CONFLICT.value
        record.conflict_fields = diffs
    else:
        record.status = IngestStatus.MERGED.value


def _apply_row(record: SourceRecord, row: dict) -> None:
    record.payload = dict(row)
    for field in ELEMENT_FIELDS:
        setattr(record, field, row.get(field))


def submit_batch(
    db: Session,
    *,
    institution: str,
    batch_key: str,
    rows: list[dict],
    operator_email: str,
    note: str | None = None,
) -> dict:
    """接收一批机构记录。同一（机构, batch_key）重试：复用批次与记录，已确认记录原样保留。"""
    institution = institution.strip()
    batch_key = batch_key.strip()
    if len(institution) < 2 or not batch_key:
        raise AppError("VALIDATION", 422, {"fields": ["institution", "batch_key"]})
    batch = db.scalar(
        select(IngestBatch).where(
            IngestBatch.institution == institution,
            IngestBatch.batch_key == batch_key,
        )
    )
    reused = batch is not None
    if batch is None:
        batch = IngestBatch(
            batch_no=_next_batch_no(db),
            institution=institution,
            batch_key=batch_key,
            status=IngestBatchStatus.RECEIVED.value,
            operator_email=operator_email,
            note=note,
        )
        db.add(batch)
        db.flush()
    existing = {
        record.inst_code: record
        for record in db.scalars(select(SourceRecord).where(SourceRecord.batch_id == batch.id)).all()
    }
    created = updated = kept = 0
    rejected: list[dict] = []
    for index, row in enumerate(rows, start=1):
        inst_code = str(row.get("inst_code") or "").strip()
        if not inst_code:
            rejected.append({"row_no": index, "reason": "缺少机构编码，无法按（机构, 机构编码）识别来源"})
            continue
        record = existing.get(inst_code)
        if record is not None and record.status == IngestStatus.CONFIRMED.value:
            kept += 1  # 不丢失已有复核：已确认记录不被批次重试改写
            continue
        if record is None:
            record = SourceRecord(
                batch_id=batch.id,
                row_no=index,
                institution=institution,
                inst_code=inst_code,
            )
            db.add(record)
            existing[inst_code] = record
            created += 1
        else:
            record.row_no = index
            updated += 1
        _apply_row(record, row)
        _evaluate(db, record)
    batch.row_count = len(rows)
    batch.rejected = rejected
    batch.status = IngestBatchStatus.PROCESSED.value
    db.flush()
    return {
        "batch": serialize_batch(db, batch),
        "reused": reused,
        "created": created,
        "updated": updated,
        "kept_confirmed": kept,
        "rejected": rejected,
    }


# ---------------- 查询 ----------------
def list_batches(db: Session, *, institution: str | None = None, limit: int = 20, offset: int = 0) -> dict:
    stmt = select(IngestBatch)
    count_stmt = select(func.count()).select_from(IngestBatch)
    if institution:
        stmt = stmt.where(IngestBatch.institution == institution)
        count_stmt = count_stmt.where(IngestBatch.institution == institution)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(IngestBatch.id.desc()).limit(limit).offset(offset)).all()
    return {
        "items": [serialize_batch(db, row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_batch(db: Session, batch_id: int) -> IngestBatch:
    batch = db.get(IngestBatch, batch_id)
    if batch is None:
        raise not_found("ingest_batch", batch_id)
    return batch


def batch_detail(db: Session, batch_id: int) -> dict:
    batch = get_batch(db, batch_id)
    payload = serialize_batch(db, batch)
    payload["records"] = list_records(db, batch_id=batch_id, limit=500)["items"]
    return payload


def list_records(
    db: Session,
    *,
    batch_id: int | None = None,
    status: str | None = None,
    institution: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    stmt = select(SourceRecord)
    count_stmt = select(func.count()).select_from(SourceRecord)
    if batch_id:
        stmt = stmt.where(SourceRecord.batch_id == batch_id)
        count_stmt = count_stmt.where(SourceRecord.batch_id == batch_id)
    if status:
        stmt = stmt.where(SourceRecord.status == status)
        count_stmt = count_stmt.where(SourceRecord.status == status)
    if institution:
        stmt = stmt.where(SourceRecord.institution == institution)
        count_stmt = count_stmt.where(SourceRecord.institution == institution)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(SourceRecord.id).limit(limit).offset(offset)).all()
    products = {
        product.id: product
        for product in db.scalars(select(Product).where(Product.id.in_([row.product_id for row in rows if row.product_id]))).all()
    } if rows else {}
    return {
        "items": [serialize_record(row, product=products.get(row.product_id)) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_record(db: Session, record_id: int) -> SourceRecord:
    record = db.get(SourceRecord, record_id)
    if record is None:
        raise not_found("source_record", record_id)
    return record


# ---------------- 补齐与确认 ----------------
def complete_record(db: Session, record_id: int, fields: dict) -> SourceRecord:
    """补齐缺失要素后重算状态；已确认记录不允许再改（不丢失已有复核）。"""
    record = get_record(db, record_id)
    if record.status == IngestStatus.CONFIRMED.value:
        raise AppError("CONFLICT", 409, {"status": record.status, "hint": "已确认记录不能改要素"})
    updates = {key: value for key, value in fields.items() if key in ELEMENT_FIELDS and value is not None}
    for field, value in updates.items():
        setattr(record, field, value)
    payload = dict(record.payload or {})
    payload.update(updates)
    record.payload = payload
    _evaluate(db, record)
    db.flush()
    return record


def _apply_to_product(product: Product, record: SourceRecord) -> None:
    product.name = record.name
    product.type = record.product_type
    product.risk_level = record.risk_level
    product.min_amount = float(record.min_amount or 0)
    product.term_days = int(record.term_days or 0)
    product.fee_rate = float(record.fee_rate or 0)


def confirm_record(
    db: Session,
    record_id: int,
    *,
    reviewer: str,
    note: str | None = None,
    resolution: str | None = None,
) -> SourceRecord:
    """确认后产品进入正式对比榜；冲突记录必须显式选择保留现有值或采用来源值。"""
    record = get_record(db, record_id)
    if record.status == IngestStatus.CONFIRMED.value:
        return record  # 幂等：重复确认不报错、不改写
    if record.status == IngestStatus.PENDING.value:
        raise AppError(
            "VALIDATION",
            422,
            {
                "missing": record.missing_fields or [],
                "invalid": record.invalid_fields or [],
                "hint": "要素未补齐，不能确认入榜",
            },
        )
    product = db.get(Product, record.product_id) if record.product_id else None
    if product is None:
        raise AppError("CONFLICT", 409, {"hint": "记录尚未关联正式产品"})
    if record.status == IngestStatus.CONFLICT.value:
        if resolution not in CONFLICT_RESOLUTIONS:
            raise AppError(
                "VALIDATION",
                422,
                {"resolutions": list(CONFLICT_RESOLUTIONS), "hint": "冲突记录必须选择保留现有值或采用来源值"},
            )
        if resolution == "use_incoming":
            _apply_to_product(product, record)
    record.status = IngestStatus.CONFIRMED.value
    record.reviewer = reviewer
    record.review_note = note
    record.confirmed_at = utcnow()
    product.listed = True
    db.flush()
    return record

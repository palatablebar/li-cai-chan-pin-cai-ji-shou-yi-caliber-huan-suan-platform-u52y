"""机构批量采集：批次、来源记录（按机构 + 机构编码识别）、机构编码映射。

- ingest_batches：同一机构同一 batch_key 只建一次，重试同一批不新增；
- source_records：自然键 (batch_id, inst_code)，状态机 pending/merged/conflict/confirmed；
- product_sources：（机构, 机构编码）-> 正式产品的稳定映射，两家机构同码各自成行。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class IngestBatch(Base):
    __tablename__ = "ingest_batches"
    __table_args__ = (UniqueConstraint("institution", "batch_key", name="uq_ingest_batch_inst_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    institution: Mapped[str] = mapped_column(String(80), index=True)
    batch_key: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), default="received", index=True)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[list] = mapped_column(JSON, default=list)
    operator_email: Mapped[str] = mapped_column(String(160))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class SourceRecord(Base):
    __tablename__ = "source_records"
    __table_args__ = (UniqueConstraint("batch_id", "inst_code", name="uq_source_record_batch_code"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("ingest_batches.id", ondelete="CASCADE"), index=True)
    row_no: Mapped[int] = mapped_column(Integer, default=0)
    institution: Mapped[str] = mapped_column(String(80), index=True)
    inst_code: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    product_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(4), nullable=True)
    min_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    term_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fee_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    missing_fields: Mapped[list] = mapped_column(JSON, default=list)
    invalid_fields: Mapped[list] = mapped_column(JSON, default=list)
    conflict_fields: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reviewer: Mapped[str | None] = mapped_column(String(160), nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ProductSource(Base):
    __tablename__ = "product_sources"
    __table_args__ = (UniqueConstraint("institution", "inst_code", name="uq_product_source_inst_code"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    institution: Mapped[str] = mapped_column(String(80))
    inst_code: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

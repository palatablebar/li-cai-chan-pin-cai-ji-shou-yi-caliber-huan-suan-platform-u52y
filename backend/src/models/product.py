"""理财产品主档：代销 68 只，按机构 / 类型 / 风险等级 / 期限维护。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    issuer: Mapped[str] = mapped_column(String(80), index=True)
    type: Mapped[str] = mapped_column(String(20), index=True)
    risk_level: Mapped[str] = mapped_column(String(4), index=True)
    min_amount: Mapped[float] = mapped_column(Float, default=10000.0)
    term_days: Mapped[int] = mapped_column(Integer, default=0)
    fee_rate: Mapped[float] = mapped_column(Float, default=0.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

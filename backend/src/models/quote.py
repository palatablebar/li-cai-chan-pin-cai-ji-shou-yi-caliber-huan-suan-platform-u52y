"""每日行情报价：5 个交易日 × 68 只 = 340 条；四个口径字段允许缺失（缺失不猜）。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class Quote(Base):
    __tablename__ = "quotes"
    __table_args__ = (UniqueConstraint("product_id", "quote_date", name="uq_quotes_product_date"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    quote_date: Mapped[date] = mapped_column(Date, index=True)
    nav: Mapped[float | None] = mapped_column(Float, nullable=True)
    seven_day_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    wanfen_yield: Mapped[float | None] = mapped_column(Float, nullable=True)
    bench_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    bench_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    year_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="seed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

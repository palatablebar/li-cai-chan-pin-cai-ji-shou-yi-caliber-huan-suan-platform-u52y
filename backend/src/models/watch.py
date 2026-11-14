"""关注清单：到期提醒（expire）与排名变动提醒（rank），due_on 决定跟进时点。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base
from src.utils.timeutil import utcnow


class Watch(Base):
    __tablename__ = "watches"
    __table_args__ = (UniqueConstraint("product_id", "kind", name="uq_watches_product_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10), default="expire", index=True)
    due_on: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner: Mapped[str] = mapped_column(String(80), default="江城银行 · 财富管理部产品组")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

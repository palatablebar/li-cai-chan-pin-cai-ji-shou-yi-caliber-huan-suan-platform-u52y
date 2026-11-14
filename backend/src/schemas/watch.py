from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class WatchIn(BaseModel):
    product_id: int = Field(ge=1)
    kind: Literal["expire", "rank"]
    due_on: date
    status: Literal["pending", "notified", "done"] = "pending"
    note: str | None = Field(default=None, max_length=500)


class WatchPatch(BaseModel):
    status: Literal["pending", "notified", "done"] | None = None
    due_on: date | None = None
    note: str | None = Field(default=None, max_length=500)

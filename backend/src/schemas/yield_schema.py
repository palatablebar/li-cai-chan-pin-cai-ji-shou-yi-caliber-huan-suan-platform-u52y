from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class YieldRunIn(BaseModel):
    trigger: Literal["manual", "schedule"] = "manual"
    note: str | None = Field(default=None, max_length=200)


class ViewReviewIn(BaseModel):
    status: Literal["pending", "confirmed", "dismissed"]
    note: str | None = Field(default=None, max_length=1000)

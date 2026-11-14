from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ProductTypeLiteral = Literal["cash", "fixed", "mixed", "equity"]
RiskLevelLiteral = Literal["R1", "R2", "R3", "R4", "R5"]


class ProductIn(BaseModel):
    code: str = Field(min_length=3, max_length=40, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=2, max_length=120)
    issuer: str = Field(min_length=2, max_length=80)
    type: ProductTypeLiteral
    risk_level: RiskLevelLiteral
    min_amount: float = Field(default=10000.0, ge=0, le=100_000_000)
    term_days: int = Field(default=0, ge=0, le=3650)
    fee_rate: float = Field(default=0.0, ge=0, le=10)
    active: bool = True
    note: str | None = Field(default=None, max_length=1000)


class ProductPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    issuer: str | None = Field(default=None, min_length=2, max_length=80)
    type: ProductTypeLiteral | None = None
    risk_level: RiskLevelLiteral | None = None
    min_amount: float | None = Field(default=None, ge=0, le=100_000_000)
    term_days: int | None = Field(default=None, ge=0, le=3650)
    fee_rate: float | None = Field(default=None, ge=0, le=10)
    active: bool | None = None
    note: str | None = Field(default=None, max_length=1000)

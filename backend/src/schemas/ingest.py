from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class IngestRowIn(BaseModel):
    """机构文件里的一行：要素允许缺失或为空，缺失行进「待补」而不是静默跳过。

    extra="allow"：未识别的列也原样留在 payload 里备查（保留来源）。
    """

    model_config = ConfigDict(extra="allow")

    inst_code: str | None = Field(default=None, max_length=40)
    name: str | None = Field(default=None, max_length=120)
    product_type: str | None = Field(default=None, max_length=20)
    risk_level: str | None = Field(default=None, max_length=4)
    min_amount: float | None = Field(default=None, ge=0, le=100_000_000)
    term_days: int | None = Field(default=None, ge=0, le=3650)
    fee_rate: float | None = Field(default=None, ge=0, le=10)
    note: str | None = Field(default=None, max_length=1000)


class IngestBatchIn(BaseModel):
    institution: str = Field(min_length=2, max_length=80)
    batch_key: str = Field(min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=500)
    rows: list[IngestRowIn] = Field(min_length=1, max_length=5000)


class IngestRecordPatch(BaseModel):
    """补齐来源记录要素：只接受元素字段，null 视为未提供。"""

    name: str | None = Field(default=None, min_length=2, max_length=120)
    product_type: Literal["cash", "fixed", "mixed", "equity"] | None = None
    risk_level: Literal["R1", "R2", "R3", "R4", "R5"] | None = None
    min_amount: float | None = Field(default=None, ge=0, le=100_000_000)
    term_days: int | None = Field(default=None, ge=0, le=3650)
    fee_rate: float | None = Field(default=None, ge=0, le=10)


class IngestConfirmIn(BaseModel):
    resolution: Literal["use_incoming", "keep_existing"] | None = None
    note: str | None = Field(default=None, max_length=500)

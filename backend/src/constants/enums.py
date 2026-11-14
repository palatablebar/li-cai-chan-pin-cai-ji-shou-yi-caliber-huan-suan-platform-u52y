"""共享枚举（后端唯一定义处）。前端副本见 frontend/site/js/config.js。

README「共享枚举出现位置」一节列出全部出现点，改动需两侧同步。
"""
from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class ProductType(StrEnum):
    """理财产品大类。决定同类排名的一级分组。"""

    CASH = "cash"
    FIXED = "fixed"
    MIXED = "mixed"
    EQUITY = "equity"


PRODUCT_TYPE_LABELS: dict[str, str] = {
    ProductType.CASH.value: "现金管理类",
    ProductType.FIXED.value: "固定收益类",
    ProductType.MIXED.value: "混合类",
    ProductType.EQUITY.value: "权益类",
}


class RiskLevel(StrEnum):
    """风险等级 R1-R5（监管口径，R1 最低）。"""

    R1 = "R1"
    R2 = "R2"
    R3 = "R3"
    R4 = "R4"
    R5 = "R5"


RISK_LEVEL_LABELS: dict[str, str] = {
    RiskLevel.R1.value: "R1 谨慎型",
    RiskLevel.R2.value: "R2 稳健型",
    RiskLevel.R3.value: "R3 平衡型",
    RiskLevel.R4.value: "R4 成长型",
    RiskLevel.R5.value: "R5 进取型",
}

RISK_LEVEL_ORDER: list[str] = ["R1", "R2", "R3", "R4", "R5"]


class TermBucket(StrEnum):
    """期限档：算法 B 的同类分组维度。"""

    LE30 = "le30"
    D31_180 = "d31_180"
    D181_365 = "d181_365"
    GT365 = "gt365"
    UNKNOWN = "unknown"


TERM_BUCKET_LABELS: dict[str, str] = {
    TermBucket.LE30.value: "≤30 天",
    TermBucket.D31_180.value: "31-180 天",
    TermBucket.D181_365.value: "181-365 天",
    TermBucket.GT365.value: ">365 天",
    TermBucket.UNKNOWN.value: "期限未知",
}


class YieldMethod(StrEnum):
    """可比年化的换算口径。算法 A 的输出，不猜缺失值。"""

    DIRECT = "direct"
    WANFEN = "wanfen"
    NAV = "nav"
    BENCH = "bench"
    UNKNOWN = "unknown"


YIELD_METHOD_LABELS: dict[str, str] = {
    YieldMethod.DIRECT.value: "七日年化直取",
    YieldMethod.WANFEN.value: "万份收益折算",
    YieldMethod.NAV.value: "净值区间年化",
    YieldMethod.BENCH.value: "业绩基准中值",
    YieldMethod.UNKNOWN.value: "口径缺失",
}


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


CONFIDENCE_LABELS: dict[str, str] = {
    Confidence.HIGH.value: "高",
    Confidence.MEDIUM.value: "中",
    Confidence.LOW.value: "低",
    Confidence.NONE.value: "无",
}


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


RUN_STATUS_LABELS: dict[str, str] = {
    RunStatus.RUNNING.value: "执行中",
    RunStatus.SUCCESS.value: "成功",
    RunStatus.PARTIAL.value: "部分成功",
    RunStatus.FAILED.value: "失败",
}


class TriggerKind(StrEnum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    SEED = "seed"


TRIGGER_LABELS: dict[str, str] = {
    TriggerKind.MANUAL.value: "手动",
    TriggerKind.SCHEDULE.value: "定时",
    TriggerKind.SEED.value: "初始化",
}


class WatchKind(StrEnum):
    EXPIRE = "expire"
    RANK = "rank"


WATCH_KIND_LABELS: dict[str, str] = {
    WatchKind.EXPIRE.value: "到期提醒",
    WatchKind.RANK.value: "排名变动",
}


class WatchStatus(StrEnum):
    PENDING = "pending"
    NOTIFIED = "notified"
    DONE = "done"


WATCH_STATUS_LABELS: dict[str, str] = {
    WatchStatus.PENDING.value: "待跟进",
    WatchStatus.NOTIFIED.value: "已通知",
    WatchStatus.DONE.value: "已处理",
}

WATCH_STATUS_ORDER: list[str] = [
    WatchStatus.PENDING.value,
    WatchStatus.NOTIFIED.value,
    WatchStatus.DONE.value,
]


class ReviewStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


REVIEW_STATUS_LABELS: dict[str, str] = {
    ReviewStatus.PENDING.value: "待复核",
    ReviewStatus.CONFIRMED.value: "已确认",
    ReviewStatus.DISMISSED.value: "已驳回",
}

REVIEW_STATUS_ORDER: list[str] = [
    ReviewStatus.PENDING.value,
    ReviewStatus.CONFIRMED.value,
    ReviewStatus.DISMISSED.value,
]


class QuoteSource(StrEnum):
    SEED = "seed"
    IMPORT = "import"
    MANUAL = "manual"


QUOTE_SOURCE_LABELS: dict[str, str] = {
    QuoteSource.SEED.value: "初始化导入",
    QuoteSource.IMPORT.value: "机构批量导入",
    QuoteSource.MANUAL.value: "手工补录",
}

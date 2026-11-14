"""收益口径换算与同类排名（纯函数，无数据库依赖，供 pytest 直接单测）。

算法 A｜收益口径归一（先到先用，缺失不猜）：
  1. direct：七日年化，直接取，置信度 high；
  2. wanfen：万份收益 → 年化 = 万份收益 × 365 / 10000（结果按百分数保存）；
     例：0.62 → 2.263%；
  3. nav：净值序列 → (NAV_end / NAV_start) ^ (365 / 天数) - 1；
  4. bench：业绩基准区间取中值，标记「非承诺」，置信度 low；
  5. unknown：四项全缺失 → comparable_pct=None，不做估算。

算法 B｜同类排名与风险调整：
  PeerGroup = 产品类型 + 期限档（≤30 / 31-180 / 181-365 / >365 天）；
  年化波动 = 近 30 个交易日净值日收益的样本标准差 × √252；
  风险调整 = 可比年化 / 年化波动；波动为 0 → 用同类中位数并标记；
  样本 < 5 只不排名（peer_rank=None，标记 sample_short）。
"""
from __future__ import annotations

import math
import statistics
from datetime import date
from typing import Any, Iterable

from src.constants.enums import (
    TERM_BUCKET_LABELS,
    Confidence,
    TermBucket,
    YieldMethod,
)
from src.constants.limits import (
    PEER_MIN_SAMPLE,
    TRADING_DAYS_PER_YEAR,
    VOL_WINDOW_DAYS,
    VOL_ZERO_EPSILON,
)

SESSION_DAYS = 365
WANFEN_FACTOR = SESSION_DAYS / 10000.0 * 100.0  # 3.65，即 1 元万份收益对应的年化百分点


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(float(value), digits)


# --------------------------------------------------------------------------
# 期限档 / 分组
# --------------------------------------------------------------------------
def term_bucket(term_days: int | None) -> str:
    """期限档：算法 B 的二级分组维度。"""
    if term_days is None or term_days < 0:
        return TermBucket.UNKNOWN.value
    if term_days <= 30:
        return TermBucket.LE30.value
    if term_days <= 180:
        return TermBucket.D31_180.value
    if term_days <= 365:
        return TermBucket.D181_365.value
    return TermBucket.GT365.value


def group_key(product_type: str, term_days: int | None) -> str:
    return f"{product_type}:{term_bucket(term_days)}"


def group_label(key: str, type_label: str) -> str:
    _, _, bucket = key.partition(":")
    return f"{type_label} · {TERM_BUCKET_LABELS.get(bucket, bucket)}"


# --------------------------------------------------------------------------
# 算法 A：单条口径换算
# --------------------------------------------------------------------------
def wanfen_to_annual(wanfen_yield: float) -> float:
    """万份收益 → 年化百分数。0.62 → 2.263。"""
    return _round(float(wanfen_yield) * WANFEN_FACTOR, 4)  # type: ignore[return-value]


def bench_mid(bench_low: float | None, bench_high: float | None) -> float | None:
    """业绩基准区间取中值；只有单边缺失视为不可用（不猜）。"""
    if bench_low is None or bench_high is None:
        return None
    low, high = float(bench_low), float(bench_high)
    if high < low:
        low, high = high, low
    return _round((low + high) / 2.0, 4)


def _nav_points(nav_series: Iterable[dict[str, Any]]) -> list[tuple[date, float]]:
    points: list[tuple[date, float]] = []
    for row in nav_series or []:
        value = row.get("nav")
        day = row.get("quote_date")
        if value is None or day is None:
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        points.append((day, value))
    points.sort(key=lambda item: item[0])
    return points


def nav_annualized(nav_series: Iterable[dict[str, Any]]) -> float | None:
    """净值区间年化百分数：(NAV_end/NAV_start)^(365/天数)-1。"""
    points = _nav_points(nav_series)
    if len(points) < 2:
        return None
    start_day, start_nav = points[0]
    end_day, end_nav = points[-1]
    days = (end_day - start_day).days
    if days <= 0 or start_nav <= 0 or end_nav <= 0:
        return None
    try:
        annual = (end_nav / start_nav) ** (SESSION_DAYS / days) - 1.0
    except (OverflowError, ZeroDivisionError):
        return None
    return _round(annual * 100.0, 4)


def normalize_quote(
    quote: dict[str, Any] | None,
    nav_series: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """把一条报价按口径优先级换算成可比年化。

    返回 {comparable_pct, method, confidence, caveat, source_value, raw}。
    """
    quote = quote or {}
    nav_series = list(nav_series or [])

    seven_day = quote.get("seven_day_pct")
    if seven_day is not None:
        return _result(seven_day, YieldMethod.DIRECT, Confidence.HIGH, "七日年化直取，与其他口径对齐后可直接比较", seven_day)

    wanfen = quote.get("wanfen_yield")
    if wanfen is not None:
        return _result(
            wanfen_to_annual(wanfen),
            YieldMethod.WANFEN,
            Confidence.HIGH,
            f"万份收益 {float(wanfen):g} × 365 / 10000 折算年化",
            wanfen,
        )

    nav_pct = nav_annualized(nav_series)
    if nav_pct is not None:
        days = (max(p[0] for p in _nav_points(nav_series)) - min(p[0] for p in _nav_points(nav_series))).days
        confidence = Confidence.HIGH if days >= VOL_WINDOW_DAYS else Confidence.MEDIUM
        return _result(nav_pct, YieldMethod.NAV, confidence, f"净值区间 {days} 天几何年化（区间不足 30 天，置信度中）", None)

    mid = bench_mid(quote.get("bench_low"), quote.get("bench_high"))
    if mid is not None:
        return _result(mid, YieldMethod.BENCH, Confidence.LOW, "业绩基准区间中值，非承诺收益", mid)

    return _result(None, YieldMethod.UNKNOWN, Confidence.NONE, "四项口径均缺失，不做估算", None)


def _result(value: float | None, method: str, confidence: str, caveat: str, source_value: float | None) -> dict[str, Any]:
    return {
        "comparable_pct": _round(value, 4),
        "method": method.value if isinstance(method, YieldMethod) else method,
        "confidence": confidence.value if isinstance(confidence, Confidence) else confidence,
        "caveat": caveat,
        "source_value": _round(source_value, 4),
    }


# --------------------------------------------------------------------------
# 算法 B：波动 / 风险调整 / 同类排名
# --------------------------------------------------------------------------
def daily_returns(nav_series: Iterable[dict[str, Any]]) -> list[float]:
    points = _nav_points(nav_series)
    returns: list[float] = []
    for index in range(1, len(points)):
        prev = points[index - 1][1]
        cur = points[index][1]
        if prev > 0:
            returns.append(cur / prev - 1.0)
    return returns


def annualized_volatility(nav_series: Iterable[dict[str, Any]], window: int = VOL_WINDOW_DAYS) -> float | None:
    """近 window 个交易日日收益标准差 × √252，返回百分数。"""
    returns = daily_returns(nav_series)
    if len(returns) < 2:
        return None
    returns = returns[-window:]
    try:
        stdev = statistics.stdev(returns)
    except statistics.StatisticsError:
        return None
    return _round(stdev * math.sqrt(TRADING_DAYS_PER_YEAR) * 100.0, 4)


def risk_adjust(
    comparable_pct: float | None,
    vol_pct: float | None,
    group_median_vol: float | None,
) -> tuple[float | None, str | None]:
    """风险调整收益 = 可比年化 / 年化波动；返回 (risk_adj, flag)。"""
    if comparable_pct is None:
        return None, "no_comparable"
    if vol_pct is None:
        return None, "no_vol"
    if vol_pct < VOL_ZERO_EPSILON:
        if group_median_vol is None or group_median_vol <= 1e-9:
            return None, "vol_zero_no_median"
        return _round(comparable_pct / group_median_vol, 3), "vol_zero_median"
    return _round(comparable_pct / vol_pct, 3), None


def _median(values: list[float]) -> float | None:
    values = [value for value in values if value is not None and value > 0]
    if not values:
        return None
    return round(statistics.median(values), 6)


def rank_peers(
    items: list[dict[str, Any]],
    min_sample: int = PEER_MIN_SAMPLE,
) -> list[dict[str, Any]]:
    """按「类型 + 期限档」分组排名，并给出风险调整值。

    items 每项至少包含：product_id、product_type、term_days、comparable_pct、vol_annual。
    返回同一批 item 的副本，追加 group_key / group_size / peer_rank / group_median_vol /
    risk_adj / flags。
    """
    prepared: list[dict[str, Any]] = []
    for item in items:
        row = dict(item)
        row["group_key"] = group_key(str(row.get("product_type") or ""), row.get("term_days"))
        row["flags"] = list(row.get("flags") or [])
        prepared.append(row)

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in prepared:
        groups.setdefault(row["group_key"], []).append(row)

    for key, members in groups.items():
        valid = [row for row in members if row.get("comparable_pct") is not None]
        median_vol = _median([row.get("vol_annual") for row in valid if row.get("vol_annual") is not None])
        ranked = len(valid) >= min_sample
        ordered = sorted(valid, key=lambda row: (-float(row["comparable_pct"]), int(row["product_id"])))
        rank_of = {id(row): index + 1 for index, row in enumerate(ordered)} if ranked else {}
        for row in members:
            row["group_size"] = len(valid)
            row["group_median_vol"] = median_vol
            row["peer_rank"] = rank_of.get(id(row))
            if row.get("comparable_pct") is None:
                row["risk_adj"] = None
                row["flags"].append("no_comparable")
                continue
            if not ranked:
                row["flags"].append("sample_short")
            risk_adj, flag = risk_adjust(row.get("comparable_pct"), row.get("vol_annual"), median_vol)
            row["risk_adj"] = risk_adj
            if flag:
                row["flags"].append(flag)
    return prepared


def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
    """一次运行的口径分布与分组概况，用于 YieldRun.metrics。"""
    method_counts: dict[str, int] = {}
    for row in items:
        method_counts[row["method"]] = method_counts.get(row["method"], 0) + 1
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in items:
        groups.setdefault(row["group_key"], []).append(row)
    group_rows = []
    for key, members in sorted(groups.items()):
        valid = [row for row in members if row.get("comparable_pct") is not None]
        valid.sort(key=lambda row: (-float(row["comparable_pct"]), int(row["product_id"])))
        group_rows.append(
            {
                "group_key": key,
                "size": len(valid),
                "ranked": len(valid) >= PEER_MIN_SAMPLE,
                "top_product_id": valid[0]["product_id"] if valid else None,
                "top_product_name": valid[0].get("product_name") if valid else None,
                "top_comparable_pct": valid[0]["comparable_pct"] if valid else None,
                "median_vol": _median([row.get("vol_annual") for row in valid if row.get("vol_annual") is not None]),
            }
        )
    risk_top: dict[str, dict[str, Any]] = {}
    for level in ("R1", "R2", "R3", "R4", "R5"):
        members = [row for row in items if row.get("risk_level") == level and row.get("comparable_pct") is not None]
        if not members:
            continue
        best = max(members, key=lambda row: (float(row["comparable_pct"]), -int(row["product_id"])))
        risk_top[level] = {
            "product_id": best["product_id"],
            "product_name": best.get("product_name"),
            "comparable_pct": best["comparable_pct"],
            "peer_rank": best.get("peer_rank"),
            "group_key": best.get("group_key"),
        }
    comparables = [float(row["comparable_pct"]) for row in items if row.get("comparable_pct") is not None]
    return {
        "views": len(items),
        "risk_top": risk_top,
        "unknown": method_counts.get(YieldMethod.UNKNOWN.value, 0),
        "method_counts": method_counts,
        "groups": group_rows,
        "ranked_groups": sum(1 for group in group_rows if group["ranked"]),
        "avg_comparable_pct": round(sum(comparables) / len(comparables), 4) if comparables else None,
    }

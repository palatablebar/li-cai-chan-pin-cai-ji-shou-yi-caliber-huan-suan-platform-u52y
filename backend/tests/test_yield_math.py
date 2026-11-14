"""算法 A/B 单测：口径优先级、边界、缺失不猜、同类排名与风险调整。"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.constants.enums import Confidence, YieldMethod
from src.services import yield_math

D0 = date(2026, 11, 9)


def nav_series(values, start=D0):
    return [{"quote_date": start + timedelta(days=index), "nav": value} for index, value in enumerate(values)]


# ---------------- 算法 A：口径换算 ----------------
def test_wanfen_conversion_matches_acceptance_value():
    """0.62 万份收益 → 2.263%（验收锚点）。"""
    assert yield_math.wanfen_to_annual(0.62) == pytest.approx(2.263, abs=1e-6)


def test_seven_day_is_direct_and_wins_precedence():
    quote = {"seven_day_pct": 2.31, "wanfen_yield": 0.62, "bench_low": 2.0, "bench_high": 4.0}
    result = yield_math.normalize_quote(quote, nav_series([1.0, 1.01, 1.02, 1.03]))
    assert result["method"] == YieldMethod.DIRECT.value
    assert result["comparable_pct"] == pytest.approx(2.31)
    assert result["confidence"] == Confidence.HIGH.value


def test_wanfen_used_when_seven_day_missing():
    result = yield_math.normalize_quote({"wanfen_yield": 0.62}, nav_series([1.0, 1.0, 1.0]))
    assert result["method"] == YieldMethod.WANFEN.value
    assert result["comparable_pct"] == pytest.approx(2.263)


def test_nav_annualized_formula():
    """(end/start)^(365/天数)-1：4 天涨 0.02% 约等于年化 1.83%。"""
    series = [{"quote_date": D0, "nav": 1.0}, {"quote_date": D0 + timedelta(days=4), "nav": 1.0002}]
    value = yield_math.nav_annualized(series)
    assert value == pytest.approx(1.8354, abs=0.01)
    result = yield_math.normalize_quote({"nav": 1.0002}, series)
    assert result["method"] == YieldMethod.NAV.value
    assert result["comparable_pct"] == pytest.approx(value)


def test_nav_confidence_drops_for_short_window():
    series = nav_series([1.0, 1.00005, 1.0001])
    result = yield_math.normalize_quote({}, series)
    assert result["method"] == YieldMethod.NAV.value
    assert result["confidence"] == Confidence.MEDIUM.value


def test_bench_mid_and_single_side_missing():
    assert yield_math.bench_mid(2.5, 3.5) == pytest.approx(3.0)
    assert yield_math.bench_mid(3.5, 2.5) == pytest.approx(3.0)  # 上下限写反也要能对齐
    assert yield_math.bench_mid(2.5, None) is None
    result = yield_math.normalize_quote({"bench_low": 2.5, "bench_high": 3.5})
    assert result["method"] == YieldMethod.BENCH.value
    assert result["comparable_pct"] == pytest.approx(3.0)
    assert result["confidence"] == Confidence.LOW.value
    assert "非承诺" in result["caveat"]


def test_all_fields_missing_is_unknown_never_guessed():
    result = yield_math.normalize_quote({"nav": None, "seven_day_pct": None, "wanfen_yield": None})
    assert result["method"] == YieldMethod.UNKNOWN.value
    assert result["comparable_pct"] is None
    assert result["confidence"] == Confidence.NONE.value


def test_single_nav_point_falls_back_to_bench_not_nav():
    result = yield_math.normalize_quote(
        {"bench_low": 3.0, "bench_high": 4.0},
        nav_series([1.0]),
    )
    assert result["method"] == YieldMethod.BENCH.value
    assert result["comparable_pct"] == pytest.approx(3.5)


def test_nav_same_day_returns_none():
    same_day = [
        {"quote_date": D0, "nav": 1.0},
        {"quote_date": D0, "nav": 1.05},
    ]
    assert yield_math.nav_annualized(same_day) is None


# ---------------- 算法 B：分组 / 波动 / 排名 ----------------
@pytest.mark.parametrize(
    "days,expected",
    [(0, "le30"), (30, "le30"), (31, "d31_180"), (180, "d31_180"), (181, "d181_365"), (365, "d181_365"), (366, "gt365"), (None, "unknown")],
)
def test_term_bucket_boundaries(days, expected):
    assert yield_math.term_bucket(days) == expected


def test_annualized_volatility_flat_and_varying():
    flat = yield_math.annualized_volatility(nav_series([1.0, 1.0, 1.0, 1.0]))
    assert flat == pytest.approx(0.0, abs=1e-9)
    varying = yield_math.annualized_volatility(nav_series([1.0, 1.002, 1.001, 1.004, 1.003]))
    assert varying is not None and varying > 0


def test_risk_adjust_uses_median_when_vol_zero():
    value, flag = yield_math.risk_adjust(2.5, 0.0, 1.25)
    assert value == pytest.approx(2.0)
    assert flag == "vol_zero_median"
    value, flag = yield_math.risk_adjust(2.5, 0.0, None)
    assert value is None and flag == "vol_zero_no_median"
    # 净值 6 位小数带来的精度噪声（<0.01%）按无波动处理
    value, flag = yield_math.risk_adjust(2.5, 0.004, 1.25)
    assert value == pytest.approx(2.0) and flag == "vol_zero_median"
    assert yield_math.risk_adjust(None, 1.0, 1.0) == (None, "no_comparable")


def test_rank_peers_orders_and_marks_sample_short():
    items = [
        {"product_id": 1, "product_type": "fixed", "term_days": 90, "comparable_pct": 2.31, "vol_annual": 0.2},
        {"product_id": 2, "product_type": "fixed", "term_days": 120, "comparable_pct": 3.05, "vol_annual": 0.3},
        {"product_id": 3, "product_type": "fixed", "term_days": 60, "comparable_pct": 1.80, "vol_annual": 0.1},
        {"product_id": 4, "product_type": "fixed", "term_days": 90, "comparable_pct": None, "vol_annual": None},
        {"product_id": 5, "product_type": "fixed", "term_days": 90, "comparable_pct": 2.0, "vol_annual": 0.2},
        {"product_id": 6, "product_type": "cash", "term_days": 1, "comparable_pct": 2.26, "vol_annual": 0.0},
        {"product_id": 7, "product_type": "fixed", "term_days": 150, "comparable_pct": 2.60, "vol_annual": 0.2},
        {"product_id": 8, "product_type": "cash", "term_days": 1, "comparable_pct": 2.40, "vol_annual": 0.4},
    ]
    ranked = yield_math.rank_peers(items, min_sample=5)
    fixed = [row for row in ranked if row["group_key"] == "fixed:d31_180"]
    assert len(fixed) == 6
    by_id = {row["product_id"]: row for row in fixed}
    assert by_id[2]["peer_rank"] == 1
    assert by_id[7]["peer_rank"] == 2
    assert by_id[1]["peer_rank"] == 3
    assert by_id[5]["peer_rank"] == 4
    assert by_id[3]["peer_rank"] == 5
    assert by_id[4]["peer_rank"] is None and "no_comparable" in by_id[4]["flags"]
    assert by_id[2]["risk_adj"] == pytest.approx(round(3.05 / 0.3, 3))
    cash = next(row for row in ranked if row["group_key"] == "cash:le30")
    assert cash["peer_rank"] is None and "sample_short" in cash["flags"]
    assert "vol_zero_median" in cash["flags"]


def test_summarize_counts_and_risk_top():
    base = [
        (1, "A", 2.31),
        (2, "B", 3.05),
        (3, "C", 2.20),
        (4, "D", 2.50),
        (5, "E", 2.80),
    ]
    items = [
        {
            "product_id": pid,
            "product_name": name,
            "product_type": "fixed",
            "term_days": 90,
            "risk_level": "R2",
            "comparable_pct": pct,
            "method": "direct",
            "vol_annual": 0.2,
            "flags": [],
        }
        for pid, name, pct in base
    ]
    items.append(
        {
            "product_id": 6,
            "product_name": "F",
            "product_type": "cash",
            "term_days": 1,
            "risk_level": "R1",
            "comparable_pct": None,
            "method": "unknown",
            "vol_annual": None,
            "flags": [],
        }
    )
    ranked = yield_math.rank_peers(items)
    summary = yield_math.summarize(ranked)
    assert summary["views"] == 6
    assert summary["unknown"] == 1
    assert summary["method_counts"] == {"direct": 5, "unknown": 1}
    assert summary["risk_top"]["R2"]["comparable_pct"] == pytest.approx(3.05)
    assert summary["risk_top"]["R2"]["peer_rank"] == 1
    assert summary["risk_top"]["R2"]["product_name"] == "B"
    assert summary["avg_comparable_pct"] == pytest.approx(2.572)
    assert summary["ranked_groups"] == 1


def test_pipeline_is_deterministic():
    items = [
        {
            "product_id": 1,
            "product_name": "A",
            "product_type": "fixed",
            "term_days": 90,
            "risk_level": "R2",
            "comparable_pct": 2.31,
            "method": "direct",
            "vol_annual": 0.2,
            "flags": [],
        },
        {
            "product_id": 2,
            "product_name": "B",
            "product_type": "fixed",
            "term_days": 90,
            "risk_level": "R2",
            "comparable_pct": 2.20,
            "method": "nav",
            "vol_annual": 0.0,
            "flags": [],
        },
    ]
    first = yield_math.summarize(yield_math.rank_peers(items))
    second = yield_math.summarize(yield_math.rank_peers(items))
    assert first == second

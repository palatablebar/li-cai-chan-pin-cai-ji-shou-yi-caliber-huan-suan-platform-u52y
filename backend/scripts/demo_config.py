"""演示账号与种子数据：68 只代销产品 / 5 个交易日 340 条报价 / 12 条关注。

数据全部确定性生成（无随机数、锚定固定报价日 2026-11-13），保证 seed 幂等，
两次执行 SEED_SUMMARY 逐字一致。算法结果由后端根据这些字段真实计算，
不在任何地方硬编码「可比年化」。

验收锚点（seed 保证）：
  yb001 江城稳健 90 天   七日年化 2.31  → 可比 2.31%（direct）
  yb002 江城现金宝       万份收益 0.62  → 可比 2.263%（wanfen）
  yb003 江城添利 120 天  七日年化 3.05  → R2 组同类第 1（peer_rank=1）
"""
from __future__ import annotations

import math
from datetime import date, timedelta

DEMO_PASSWORD = "Demo@2026"

DEMO_USERS = [
    ("admin@yieldbook.io", "林可 · 产品经理", "admin"),
    ("analyst@yieldbook.io", "周棠 · 口径专员", "analyst"),
    ("viewer@yieldbook.io", "陈默 · 客户经理", "viewer"),
]

ORG = "江城银行 · 财富管理部产品组"

# 报价锚点固定，避免跨天重跑时数据漂移
SEED_ANCHOR_DATE = date(2026, 11, 13)
QUOTE_DAYS = 5

ISSUERS = [
    "江城银行",
    "江城理财",
    "华信理财",
    "中盈基金",
    "瑞丰资产管理",
    "恒安理财",
    "长润资本",
    "鼎泰基金",
]

CASH_NAMES = [
    "江城现金宝",
    "江城日利盈",
    "江城天天增",
    "江城月月宝",
    "江城日日金",
    "江城添鑫宝",
    "江城钱袋宝",
    "江城稳利宝",
    "江城活期盈",
    "江城朝夕宝",
    "江城聚宝盆",
    "江城零钱通",
]

FIXED_R2 = [
    ("江城稳健", 90),
    ("江城添利", 120),
    ("江城恒盈", 60),
    ("江城季季盈", 91),
    ("江城安心", 150),
    ("江城稳盈", 180),
    ("江城丰利", 75),
    ("江城汇盈", 100),
    ("江城恒利", 45),
    ("江城安盈", 130),
    ("江城稳享", 160),
    ("江城季享", 95),
    ("江城添瑞", 110),
    ("江城盈丰", 140),
    ("江城泰利", 65),
    ("江城安泰", 170),
    ("江城瑞盈", 80),
    ("江城锦盈", 125),
    ("江城聚盈", 155),
    ("江城顺盈", 105),
    ("江城宝盈", 70),
    ("江城康盈", 135),
]

FIXED_R3 = [
    ("江城增利", 182),
    ("江城恒润", 210),
    ("江城半年盈", 240),
    ("江城瑞享", 270),
    ("江城中盈", 300),
    ("江城稳进", 330),
    ("江城安润", 365),
    ("江城丰润", 200),
    ("江城泰盈", 225),
    ("江城兴利", 255),
    ("江城嘉盈", 285),
    ("江城聚利", 315),
    ("江城康泰", 345),
    ("江城顺泰", 360),
]

MIXED_R3 = [
    ("江城平衡优选", 200),
    ("江城混合稳健", 240),
    ("江城多元配置", 300),
    ("江城灵活配置", 270),
    ("江城均衡增长", 330),
    ("江城稳中求进", 365),
    ("江城多策略", 250),
    ("江城价值平衡", 290),
]

MIXED_R4 = [
    ("江城成长甄选", 540),
    ("江城优选成长", 730),
    ("江城价值成长", 400),
    ("江城趋势配置", 900),
]

EQUITY_R5 = [
    ("江城进取先锋", 730),
    ("江城沪深精选", 1080),
    ("江城消费主题", 900),
    ("江城科技成长", 800),
    ("江城医药精选", 950),
    ("江城新能源主题", 1000),
    ("江城港股精选", 760),
    ("江城红利精选", 850),
]

# 每个分组的口径方法分布（合计：direct 29 / wanfen 9 / nav 18 / bench 3 / unknown 9 = 68）
GROUP_SPECS = [
    {
        "risk": "R1",
        "type": "cash",
        "items": [(name, 1) for name in CASH_NAMES],
        "methods": ["wanfen"] * 10 + ["unknown", "direct"],
        "min_amount": 100.0,
    },
    {
        "risk": "R2",
        "type": "fixed",
        "items": FIXED_R2,
        "methods": ["direct"] * 14 + ["nav"] * 6 + ["unknown"] * 2,
        "min_amount": 10000.0,
    },
    {
        "risk": "R3",
        "type": "fixed",
        "items": FIXED_R3,
        "methods": ["direct"] * 9 + ["nav"] * 3 + ["unknown"] * 2,
        "min_amount": 10000.0,
    },
    {
        "risk": "R3",
        "type": "mixed",
        "items": MIXED_R3,
        "methods": ["direct"] * 4 + ["nav"] * 3 + ["unknown"] * 1,
        "min_amount": 50000.0,
    },
    {
        "risk": "R4",
        "type": "mixed",
        "items": MIXED_R4,
        "methods": ["nav"] * 2 + ["unknown"] * 2,
        "min_amount": 50000.0,
    },
    {
        "risk": "R5",
        "type": "equity",
        "items": EQUITY_R5,
        "methods": ["nav"] * 4 + ["bench"] * 3 + ["unknown"] * 1,
        "min_amount": 100000.0,
    },
]

# 手工锚定的验收数值：产品编码 -> 目标可比年化（编码由分组顺序决定，见 README）
TARGET_OVERRIDES = {"yb013": 2.31, "yb014": 3.05}


def _target_pct(index: int, code: str | None = None) -> float:
    if code and code in TARGET_OVERRIDES:
        return TARGET_OVERRIDES[code]
    return round(1.60 + ((index * 37) % 130) / 100.0, 2)


def build_products() -> list[dict]:
    products: list[dict] = []
    index = 0
    for spec in GROUP_SPECS:
        methods = spec["methods"]
        assert len(methods) == len(spec["items"]), f"方法分布与产品数不一致：{spec['type']}"
        for offset, (name, term_days) in enumerate(spec["items"]):
            code = f"yb{index + 1:03d}"
            display = name if spec["type"] == "cash" else f"{name} {term_days} 天"
            products.append(
                {
                    "code": code,
                    "name": display,
                    "issuer": ISSUERS[index % len(ISSUERS)],
                    "type": spec["type"],
                    "risk_level": spec["risk"],
                    "min_amount": spec["min_amount"],
                    "term_days": term_days,
                    "fee_rate": round(0.10 + (index % 7) * 0.05, 2),
                    "note": f"代销产品 {code}，要素来自机构官网/APP 采集",
                    "method": methods[offset],
                    "target_pct": _target_pct(index, code),
                }
            )
            index += 1
    return products


PRODUCTS = build_products()


def _nav_series(index: int, target_pct: float, is_cash: bool) -> list[tuple[date, float]]:
    """5 个交易日的单位净值：首尾精确对齐目标年化，中间加微小波动供算年化波动率。"""
    nav0 = 1.0 if is_cash else round(1.0 + (index % 7) * 0.0137, 4)
    daily_log = math.log(1.0 + target_pct / 100.0) / 365.0
    amplitude = 0.0 if index % 9 == 0 else 0.0009 + (index % 5) * 0.00012
    series = []
    for step in range(QUOTE_DAYS):
        day = SEED_ANCHOR_DATE - timedelta(days=QUOTE_DAYS - 1 - step)
        # sin(pi*step/4) 在首尾为 0：端点净值不受波动项影响，年化严格等于目标值
        drift = amplitude * math.sin(math.pi * step / 4.0) * math.sin(index * 1.7 + step * 0.9)
        nav = nav0 * math.exp(daily_log * step + drift)
        series.append((day, round(nav, 6)))
    return series


def build_quotes() -> list[dict]:
    rows: list[dict] = []
    for index, product in enumerate(PRODUCTS):
        method = product["method"]
        target = product["target_pct"]
        series = _nav_series(index, target, product["type"] == "cash")
        is_pinned_wanfen = index == 0  # yb001 江城现金宝：万份收益 0.62
        for day, nav in series:
            row = {
                "product_code": product["code"],
                "quote_date": day,
                "source": "seed",
                "nav": None,
                "seven_day_pct": None,
                "wanfen_yield": None,
                "bench_low": None,
                "bench_high": None,
                "year_pct": None,
            }
            if method == "direct":
                row["nav"] = nav
                row["seven_day_pct"] = target
                row["year_pct"] = round(target + 0.12, 2)
            elif method == "wanfen":
                row["nav"] = nav
                row["wanfen_yield"] = 0.62 if is_pinned_wanfen else round(target / 3.65, 2)
            elif method == "nav":
                row["nav"] = nav
                row["year_pct"] = round(target + 0.12, 2)
            elif method == "bench":
                row["bench_low"] = round(target - 0.35, 2)
                row["bench_high"] = round(target + 0.35, 2)
            # unknown：五个字段全空，模拟机构页面字段缺失
            rows.append(row)
    return rows


QUOTES = build_quotes()

# 关注清单：8 条到期提醒 + 4 条排名变动；到期偏移决定「7 天内到期」条数
WATCH_SPECS = [
    ("yb035", "expire", 2, "pending", "182 天产品到期日临近，需提前 3 个工作日通知客户经理"),
    ("yb037", "expire", 5, "pending", "240 天产品到期，客户拟续投"),
    ("yb040", "expire", 7, "notified", "270 天产品到期，已微信通知"),
    ("yb043", "expire", 12, "pending", "365 天产品到期，需准备承接产品清单"),
    ("yb049", "expire", 18, "pending", "混合类 200 天产品到期"),
    ("yb053", "expire", 25, "notified", "多策略产品到期，客户经理已确认"),
    ("yb061", "expire", 31, "pending", "权益类 730 天产品到期"),
    ("yb065", "expire", 45, "done", "医药精选到期，已完成兑付告知"),
    ("yb001", "rank", 3, "pending", "现金宝万份收益连续两日下滑，需复核口径"),
    ("yb002", "rank", 10, "pending", "日利盈七日年化回落，需核对报价"),
    ("yb003", "rank", 16, "pending", "天天增保持现金类第 1，跟踪可持续性"),
    ("yb013", "rank", 22, "done", "稳健 90 天排名变动已复核"),
]

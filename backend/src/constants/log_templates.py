"""审计动作 -> 中文标签。"""
from __future__ import annotations

ACTIONS: dict[str, str] = {
    "auth.login": "登录",
    "product.create": "新建产品",
    "product.update": "修改产品要素",
    "quote.import": "导入行情报价",
    "yield.run": "发起口径换算",
    "yield.review": "复核可比口径",
    "watch.create": "新增关注",
    "watch.update": "更新关注",
    "export.views": "导出对比榜",
    "export.quotes": "导出报价流水",
    "http.mutation": "写请求",
}

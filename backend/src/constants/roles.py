"""角色 -> 权限点映射。README 与前端 site/js/config.js 同步。

角色键固定为 admin / analyst / viewer，本项目的展示名与职责：
admin  产品经理（维护产品与机构、导入报价、导出、审计）
analyst 口径专员（导入报价、复核可比口径、维护关注）
viewer 客户经理（只读榜单，费率明细隐藏）
"""
from __future__ import annotations

from src.constants.enums import Role

ROLE_LABELS: dict[str, str] = {
    Role.ADMIN.value: "产品经理",
    Role.ANALYST.value: "口径专员",
    Role.VIEWER.value: "客户经理",
}

ROLE_DUTIES: dict[str, str] = {
    Role.ADMIN.value: "维护产品与机构、导入报价、导出报表、查看审计",
    Role.ANALYST.value: "导入报价、复核可比口径、维护关注清单",
    Role.VIEWER.value: "只读查看对比榜与产品要素，费率明细不展示",
}

PERMISSIONS: dict[str, set[str]] = {
    Role.ADMIN.value: {
        "product:read", "product:write",
        "quote:read", "quote:import",
        "yield:read", "yield:run", "yield:review",
        "watch:read", "watch:write",
        "export:read", "audit:read", "overview:read",
    },
    Role.ANALYST.value: {
        "product:read",
        "quote:read", "quote:import",
        "yield:read", "yield:run", "yield:review",
        "watch:read", "watch:write",
        "overview:read",
    },
    Role.VIEWER.value: {
        "product:read", "quote:read", "yield:read", "watch:read", "overview:read",
    },
}

PRODUCT_WRITE_ROLES = (Role.ADMIN.value,)
QUOTE_IMPORT_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
RUN_CREATE_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
REVIEW_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
WATCH_WRITE_ROLES = (Role.ADMIN.value, Role.ANALYST.value)
EXPORT_ROLES = (Role.ADMIN.value,)
AUDIT_ROLES = (Role.ADMIN.value,)
READ_ROLES = (Role.ADMIN.value, Role.ANALYST.value, Role.VIEWER.value)


def has_permission(role: str, permission: str) -> bool:
    return permission in PERMISSIONS.get(role, set())

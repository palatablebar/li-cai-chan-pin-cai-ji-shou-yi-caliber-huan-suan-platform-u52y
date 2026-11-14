"""ORM 模型聚合导出（Base 用于 create_all）。"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from src.models.user import User  # noqa: E402
from src.models.audit import AuditLog  # noqa: E402
from src.models.product import Product  # noqa: E402
from src.models.quote import Quote  # noqa: E402
from src.models.watch import Watch  # noqa: E402
from src.models.yield_run import YieldRun  # noqa: E402
from src.models.yield_view import YieldView  # noqa: E402

__all__ = ["Base", "User", "AuditLog", "Product", "Quote", "Watch", "YieldRun", "YieldView"]

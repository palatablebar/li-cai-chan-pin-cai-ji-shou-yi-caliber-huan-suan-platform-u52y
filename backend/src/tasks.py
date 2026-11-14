"""Celery 任务：worker 心跳 + 每日口径换算（对全部在售产品重算一次）。"""
from __future__ import annotations

import time

from src.config.celery_app import TASK_DAILY, TASK_HEARTBEAT, celery_app
from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger("tasks")


def _redis():
    import redis

    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


@celery_app.task(name=TASK_HEARTBEAT)
def heartbeat() -> str:
    try:
        _redis().set(f"{settings.app_name}:worker:heartbeat", time.time())
        return "ok"
    except Exception as exc:  # noqa: BLE001
        logger.warning("heartbeat failed: %s", exc)
        return "error"


@celery_app.task(name=TASK_DAILY)
def daily_yield_refresh() -> dict:
    """每日 07:30 由 beat 触发：按最新报价重算可比年化，写审计。"""
    from src.config.database import session_scope
    from src.services import audit_service, yield_service

    operator = "scheduler@" + settings.app_name + ".io"
    with session_scope() as db:
        run = yield_service.refresh_daily(db, operator)
        audit_service.record(
            db,
            actor_email=operator,
            actor_role="admin",
            action="yield.run",
            entity="yield_run",
            entity_id=run.id,
            detail={"trigger": "schedule", "run_no": run.run_no, "views": run.view_count},
            layer="worker",
        )
    logger.info("daily yield refresh finished: %s", run.run_no)
    return {"run_no": run.run_no, "views": run.view_count}

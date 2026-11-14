"""路由聚合：统一 /api 前缀（Nginx 反代时剥掉 /api）。"""
from fastapi import APIRouter

from src.routes.audit import router as audit_router
from src.routes.auth import router as auth_router
from src.routes.exports import router as exports_router
from src.routes.health import router as health_router
from src.routes.overview import router as overview_router
from src.routes.products import router as products_router
from src.routes.quotes import router as quotes_router
from src.routes.watchlist import router as watchlist_router
from src.routes.yield_routes import router as yield_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(overview_router)
api_router.include_router(products_router)
api_router.include_router(quotes_router)
api_router.include_router(yield_router)
api_router.include_router(watchlist_router)
api_router.include_router(exports_router)
api_router.include_router(audit_router)

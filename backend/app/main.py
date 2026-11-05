"""FastAPI 應用程式進入點。"""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api import admin_routes, auth_routes, caregiver_routes, line_routes, quality_routes
from app.config import get_settings
from app.db import new_session
from app.logging_setup import setup_logging
from app.providers.llm import warmup as llm_warmup

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """啟動時在背景預熱本機 LLM（不阻塞啟動）。"""
    if get_settings().app_env != "test":
        threading.Thread(target=llm_warmup, daemon=True).start()
    yield


app = FastAPI(title="長照 AI 照護小幫手 API", version="0.1.0", docs_url="/api/docs",
              openapi_url="/api/openapi.json", lifespan=lifespan)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    """統一錯誤格式：{"error": {code, message, retryable}}。"""
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "error", "message": str(exc.detail)}
    from app.services.public_messages import safe_error_message, SYSTEM_FAILURE
    detail = dict(detail)
    detail['message'] = SYSTEM_FAILURE if exc.status_code >= 500 else safe_error_message(detail.get('message'))
    detail.setdefault("retryable", exc.status_code in (429, 502, 503, 504))
    return JSONResponse(status_code=exc.status_code, content={"error": detail})


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """輸入驗證錯誤（不回傳使用者輸入內容，避免敏感文字進回應或日誌）。"""
    fields = [".".join(str(p) for p in err.get("loc", [])) for err in exc.errors()]
    return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "retryable": False,
                                                            "message": "輸入格式不正確", "fields": fields}})


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    """未預期錯誤：日誌只記例外類型與路徑。"""
    logger.error("unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path)
    return JSONResponse(status_code=500, content={"error": {"code": "internal_error", "retryable": True,
                                                            "message": "系統目前無法完成回答，請稍後再試或送交督導確認"}})


@app.middleware("http")
async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
    """基本安全標頭；API 回應一律不快取。"""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api/") and not request.url.path.startswith("/api/media/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


for module in (auth_routes, caregiver_routes, admin_routes, line_routes, quality_routes):
    app.include_router(module.router, prefix="/api")

from app.api import jiaan1030_emergency_routes as _jiaan1030_emergency
app.include_router(_jiaan1030_emergency.router, prefix="/api")

from app.api import jiaan1030_service_catalog as _jiaan1030_service_catalog
app.include_router(_jiaan1030_service_catalog.router, prefix="/api")
from app.api import jiaan1030_service_drafts as _jiaan1030_service_drafts
app.include_router(_jiaan1030_service_drafts.router, prefix="/api")

from app.api import jiaan_webpush_routes as _jiaan_webpush
app.include_router(_jiaan_webpush.router, prefix="/api")


@app.get("/api/healthz")
def healthz() -> dict:
    """健康檢查：資料庫、provider 模式、worker 心跳。"""
    session = new_session()
    try:
        database_name = session.execute(text("SELECT current_database()")).scalar_one()
        age = session.execute(text("SELECT EXTRACT(EPOCH FROM now() - max(seen_at)) FROM worker_heartbeats")).scalar()
    finally:
        session.close()
    return {"db": "ok", "database_name": database_name, "modes": get_settings().provider_modes(),
            "worker_heartbeat_age_sec": round(float(age), 1) if age is not None else None}


# ── 前端靜態檔（frontend/dist 存在時由同一個 process 提供，讓單一 HTTPS 入口涵蓋 LIFF、後台與 API）──
# 必須放在所有 /api 路由之後：FastAPI 依註冊順序比對，catch-all 放前面會蓋掉後面的 API 路由。
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if (_DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        """SPA fallback：非 /api 路徑一律回 index.html（React Router 處理 /liff、/admin）。"""
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "not found"})
        candidate = _DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        if "." in full_path.rsplit("/", 1)[-1]:  # 像檔案的路徑（favicon.ico、x.js）找不到就 404，不回 index.html
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "not found"})
        return FileResponse(_DIST / "index.html", headers={"Cache-Control": "no-cache"})

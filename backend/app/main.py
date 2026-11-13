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

from app.api import interaction_routes, admin_routes, auth_routes, caregiver_routes, line_routes, quality_routes
from app.api import fieldtest_routes
from app.config import get_settings
from app.db import new_session
from app.logging_setup import setup_logging
from app.providers.llm import warmup as llm_warmup
from app.services.health import collect_health_for_request, ensure_internal_health_token

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """啟動時在背景預熱本機 LLM（不阻塞啟動）；同時初始化本機健康檢查 Token。

    Token 初始化要在這裡（啟動時、受控、跟任何 HTTP 請求無關），不能放進
    /api/healthz 的請求處理路徑——否則會變成「要先有人帶對 Token 來才生得出
    Token」的先有雞先有蛋問題，也可能被未授權的公開請求間接觸發。
    """
    ensure_internal_health_token()
    if get_settings().app_env != "test":
        threading.Thread(target=llm_warmup, daemon=True).start()
    yield


# 正式環境（APP_ENV=production）關閉公開 API 文件；/api/docs、/api/redoc、
# /api/openapi.json 三個入口一起關，避免有人忘記其中一個仍是 FastAPI 預設值
# （先前 redoc_url 未設定，就曾經在正式環境以預設 /redoc 路徑公開）。
_docs_enabled = get_settings().api_docs_enabled
app = FastAPI(
    title="長照 AI 照護小幫手 API", version="0.1.0",
    docs_url="/api/docs" if _docs_enabled else None,
    redoc_url="/api/redoc" if _docs_enabled else None,
    openapi_url="/api/openapi.json" if _docs_enabled else None,
    lifespan=lifespan,
)


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


for module in (interaction_routes, auth_routes, caregiver_routes, admin_routes, line_routes, quality_routes):
    app.include_router(module.router, prefix="/api")
app.include_router(fieldtest_routes.router, prefix="/api")


from app.api import jiaan1030_emergency_routes as _jiaan1030_emergency
app.include_router(_jiaan1030_emergency.router, prefix="/api")


# JIAAN1030_REGISTERED_ROUTES_20261102
from app.api import jiaan1030_service_catalog as _jiaan1030_service_catalog
app.include_router(_jiaan1030_service_catalog.router, prefix='/api')
from app.api import jiaan1030_service_drafts as _jiaan1030_service_drafts
app.include_router(_jiaan1030_service_drafts.router, prefix='/api')
# XZ_JIAAN_WEBPUSH_ROUTER
from app.api import jiaan_webpush_routes as _jiaan_webpush
app.include_router(_jiaan_webpush.router, prefix='/api')

@app.get("/api/healthz")
def healthz(request: Request) -> dict:
    """健康檢查：對公開網路只回傳 status／worker 心跳秒數。

    這台機器透過 Tailscale Funnel 對公開網路開放，這個端點不需要登入就能打到，
    所以預設不回傳資料庫名稱、LLM/embedding/LINE 等 provider 模式。本機既有的
    啟動／重啟腳本（deploy/fieldtest/*.ps1）會帶上只有本機才有的
    X-Internal-Health-Token，驗證通過才給完整內容；沒有這個 Token（包含所有
    經 Funnel 進來的公開請求）一律拿到精簡版。需要人工查看完整內容另見
    /api/admin/healthz（需要管理員登入）。
    """
    session = new_session()
    try:
        return collect_health_for_request(session, request.headers.get("x-internal-health-token"))
    finally:
        session.close()


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


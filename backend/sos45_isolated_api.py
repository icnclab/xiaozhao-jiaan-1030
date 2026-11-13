from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from fastapi.responses import JSONResponse

from app import db

SOURCE = "ltc_clean"
TARGET = "ltc_sos45_acceptance"

# 原本連線只用來取得連線設定，不做資料寫入。
source_engine = db.get_engine()

if source_engine.url.get_backend_name() != "postgresql":
    raise RuntimeError("STOP_NOT_POSTGRESQL")

if source_engine.url.database != SOURCE:
    raise RuntimeError("STOP_UNEXPECTED_SOURCE_DATABASE")

target_url = source_engine.url.set(database=TARGET)

# 防止新的測試 API 被重新設定回正式資料庫。
original_configure = db.configure_engine

def guarded_configure_engine(url):
    database = make_url(url).database

    if database != TARGET:
        raise RuntimeError(
            "STOP_PRODUCTION_DATABASE_CONFIGURATION"
        )

    return original_configure(url)

db.configure_engine = guarded_configure_engine

# 在匯入 FastAPI 主程式之前切換資料庫。
db.configure_engine(target_url.render_as_string(hide_password=False))

def verify_target():
    engine = db.get_engine()

    if engine.url.database != TARGET:
        raise RuntimeError("STOP_WRONG_DATABASE_ENGINE")

    with engine.connect() as conn:
        name = conn.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if name != TARGET:
            raise RuntimeError("STOP_WRONG_DATABASE_CONNECTION")

    return name

verify_target()

from app.main import app

# 每次 HTTP 請求前都重新核對資料庫。
@app.middleware("http")
async def sos45_database_guard(request, call_next):
    try:
        verify_target()
    except Exception:
        return JSONResponse(
            {"detail": "SOS45_DATABASE_GUARD_STOP"},
            status_code=503
        )

    return await call_next(request)

print("SOS45_DATABASE=ltc_sos45_acceptance")
print("DATABASE_GUARD=ENABLED")
print("PRODUCTION_DATABASE_TARGET=BLOCKED")
print("AUTO_DISPATCH=OFF")
print("RESULT=READY")

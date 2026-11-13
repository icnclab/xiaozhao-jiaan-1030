import sys
from pathlib import Path
from types import SimpleNamespace

prod = Path(sys.argv[1])
dev = Path(sys.argv[2])
sys.path.insert(0, str(dev))

from sqlalchemy import create_engine, text
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.config import get_settings
from dotenv import load_dotenv

# 僅從正式後端目錄載入設定，不改動正式設定檔
load_dotenv(prod / ".env", override=False)
from app.auth import current_user
from app.db import get_db
from app.api import admin_routes

engine = create_engine(get_settings().database_url)
app = FastAPI()
app.include_router(admin_routes.router, prefix="/api/admin")

def fail(message):
    raise RuntimeError(message)

with engine.connect() as conn:
    conn.execute(text("SET TRANSACTION READ ONLY"))

    records = conn.execute(text("""
        SELECT username, id, org_id, role
        FROM users
        WHERE username IN ('jiaan_director01', 'jiaan_director02')
    """)).mappings().all()

    if len(records) != 2:
        fail("DIRECTOR_ACCOUNTS_NOT_FOUND")

    org_ids = {str(r["org_id"]) for r in records}
    if len(org_ids) != 1:
        fail("DIRECTOR_ACCOUNTS_HAVE_DIFFERENT_ORGS")

    director = records[0]
    own_org = str(director["org_id"])

    other_org = conn.execute(text("""
        SELECT 1 FROM users
        WHERE org_id IS NOT NULL
          AND CAST(org_id AS TEXT) <> :org
        LIMIT 1
    """), {"org": own_org}).first()

    if other_org is None:
        fail("NO_SECOND_ORG_AVAILABLE_FOR_ISOLATION_TEST")

    print("PASS: TWO_DIRECTORS_SAME_ORG")
    print("PASS: CROSS_ORG_TEST_DATA_EXISTS")

    def readonly_db():
        yield conn

    def test_user():
        return SimpleNamespace(
            id=director["id"],
            org_id=director["org_id"],
            role="director",
            username=director["username"],
            is_active=True
        )

    app.dependency_overrides[get_db] = readonly_db
    app.dependency_overrides[current_user] = test_user

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/admin/users")

    if response.status_code != 200:
        fail(
            "REAL_USERS_HTTP_" + str(response.status_code)
            + " BODY=" + response.text[:200]
        )

    payload = response.json()

    if isinstance(payload, list):
        users = payload
    elif isinstance(payload, dict):
        users = next(
            (
                payload[key] for key in ("items", "users", "data")
                if isinstance(payload.get(key), list)
            ),
            None
        )
    else:
        users = None

    if users is None:
        fail("USER_RESPONSE_STRUCTURE_UNRECOGNIZED")

    if not users:
        fail("EMPTY_RESULT_CANNOT_VERIFY_ISOLATION")

    if not all(
        isinstance(item, dict) and "org_id" in item
        for item in users
    ):
        fail("USER_RESPONSE_MISSING_ORG_ID")

    foreign = [
        item for item in users
        if str(item["org_id"]) != own_org
    ]

    if foreign:
        fail("CROSS_ORG_USERS_VISIBLE")

    print("PASS: REAL_DIRECTOR_USERS_HTTP_200")
    print("PASS: ONLY_OWN_ORG_USERS_RETURNED")
    print("PASS: DATABASE_TRANSACTION_READONLY")

    conn.rollback()

print("PASS: REAL_USER_LIST_ORG_ISOLATION")
print("NEXT: REVIEW_BACKEND_DEPLOYMENT_AND_ACCOUNT_CONVERSION")
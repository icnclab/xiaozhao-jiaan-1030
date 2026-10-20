"""測試共用設定：測試資料庫、mock provider、兩個虛構機構的最小世界。

所有外部依賴（LLM、STT、TTS、LINE）都用 mock；這些測試驗證的是流程、授權與狀態，
不是模型品質（模型品質見 scripts/eval_run.py 與 docs/eval-results.md）。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import uuid
from datetime import date
from pathlib import Path

import pytest

_DATA_DIR = Path(tempfile.mkdtemp(prefix="ltc_test_"))


def _test_db_url() -> str:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("TEST_DATABASE_URL="):
            return line.split("=", 1)[1].split("#", 1)[0].strip()
    raise RuntimeError("找不到 TEST_DATABASE_URL")


os.environ.update({
    "APP_ENV": "test",
    "DATABASE_URL": _test_db_url(),
    "LLM_PROVIDER": "mock",
    "EMBEDDING_PROVIDER": "hash",
    "STT_PROVIDER": "mock",
    "TTS_PROVIDER": "mock",
    "LINE_MODE": "mock",
    "LINE_CHANNEL_SECRET": "test-channel-secret",
    "DATA_DIR": str(_DATA_DIR),
    "PUBLIC_BASE_URL": "http://testserver",
    "LIFF_ID": "",
})

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.auth import set_password  # noqa: E402
from app.db import configure_engine, new_session  # noqa: E402
from app.line.client import MockLineClient  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, CategoryTemplate, LineAccount, Organization, User  # noqa: E402
from app.providers.llm import MockLlm  # noqa: E402
from app.providers.stt import MockStt  # noqa: E402
from app.providers.tts import MockTts  # noqa: E402
from app.services import cases as case_service  # noqa: E402
from app.services import documents as doc_service  # noqa: E402

configure_engine(os.environ["DATABASE_URL"])
DOCS = Path(__file__).resolve().parents[2] / "demo" / "documents"
PASSWORD = "test-password-123"
TABLES = (
    "citations, feedback, tts_assets, notification_jobs, case_messages, case_events, cases, transcript_revisions, "
    "transcript_segments, qa_items, transcripts, chunks, document_versions, documents, category_templates, "
    "categories, binding_codes, sessions, line_accounts, deid_terms, users, organizations, line_events, "
    "line_mock_outbox, jobs, audit_logs, worker_heartbeats"
)


def line_id(username: str) -> str:
    """測試用 LINE userId。"""
    return "U" + hashlib.md5(username.encode()).hexdigest()


@pytest.fixture(autouse=True)
def _reset_state():
    # 測試庫專用：DELETE 比 TRUNCATE 快很多（WSL 卷上 TRUNCATE 每次約 6 秒）；
    # replica 角色暫停觸發器（含 append-only 與外鍵），僅在測試清庫時使用。
    session = new_session()
    session.execute(text("SET session_replication_role = replica"))
    for table in TABLES.split(","):
        session.execute(text(f"DELETE FROM {table.strip()}"))
    session.execute(text("SET session_replication_role = DEFAULT"))
    session.commit()
    session.close()
    for sub in ("documents", "audio_tmp", "tts", "mock_line_content"):
        shutil.rmtree(_DATA_DIR / sub, ignore_errors=True)
    MockLlm.script = None
    MockStt.script = None
    MockTts.fail = False
    MockLineClient.force_push_status = None
    case_service.FAULT_INJECTION = None
    yield


class World:
    """兩個機構（幸福園、松柏居）＋帳號＋分類＋已發布文件。"""

    def __init__(self) -> None:
        self.ids: dict[str, uuid.UUID] = {}


def _publish(session, owner, title, doc_type, scope, facility, files):
    document = doc_service.create_document(session, owner, title=title, doc_type=doc_type, scope=scope,
                                           facility_types=facility)
    versions = []
    for file_name, label, eff_from, eff_to, do_publish in files:
        version = doc_service.add_version(session, owner, document, file_name=file_name,
                                          data=(DOCS / file_name).read_bytes(), version_label=label,
                                          effective_from=eff_from, effective_to=eff_to,
                                          source="〔合成〕測試" if do_publish else None, source_url=None)
        session.flush()
        doc_service.ingest_version(session, version.id)
        if do_publish:
            doc_service.publish(session, owner, version)
        versions.append(version)
    return document, versions


@pytest.fixture
def world() -> World:
    """建立最小測試世界。"""
    w = World()
    session = new_session()
    happy = Organization(code="HAPPY", name="幸福園（虛構）", facility_type="residential")
    pine = Organization(code="PINE", name="松柏居（虛構）", facility_type="residential")
    session.add_all([happy, pine])
    session.flush()
    users = {}
    for org, username, role in [
        (happy, "admin_happy", "admin"), (happy, "sup_a", "supervisor"), (happy, "sup_b", "supervisor"),
        (happy, "cg1", "caregiver"), (happy, "cg2", "caregiver"), (pine, "sup_pine", "supervisor"),
        (pine, "cg_pine", "caregiver"),
    ]:
        user = User(org_id=org.id, username=username, display_name=username, role=role)
        if role != "caregiver":
            set_password(user, PASSWORD)
        session.add(user)
        session.flush()
        if username in {"cg1", "cg_pine"}:
            session.add(LineAccount(user_id=user.id, line_user_id=line_id(username)))
        users[username] = user
    for org, assignees in ((happy, {"家屬額外要求": users["sup_a"], "移位與行動協助": users["sup_b"]}),
                           (pine, {"家屬額外要求": users["sup_pine"]})):
        for order, name in enumerate(["家屬額外要求", "移位與行動協助", "其他"]):
            category = Category(org_id=org.id, name=name, sort_order=order,
                                default_assignee_id=assignees[name].id if name in assignees else None)
            session.add(category)
            session.flush()
            session.add(CategoryTemplate(category_id=category.id, text=f"{name}常見問題", sort_order=0))
            w.ids[f"cat:{org.code}:{name}"] = category.id
    admin = users["admin_happy"]
    _, reg_versions = _publish(session, admin, "〔合成〕營運規範", "regulation", "shared", ["residential"], [
        ("reg_operation_v1.md", "第 1 版", date(2024, 1, 1), date(2025, 12, 31), True),
        ("reg_operation_v2.md", "第 2 版", date(2026, 1, 1), None, True),
    ])
    _publish(session, admin, "〔合成〕居家規範", "regulation", "shared", ["home"], [
        ("home_service_rules.md", "第 1 版", date(2025, 1, 1), None, True)])
    _, scope_versions = _publish(session, users["sup_a"], "〔合成〕幸福園服務範圍內規", "internal_rule", "org",
                                 ["residential"], [("happy_scope_rules.md", "v1", date(2026, 3, 1), None, True)])
    _publish(session, users["sup_b"], "〔合成〕幸福園移位SOP", "sop", "org", ["residential"], [
        ("happy_transfer_sop.docx", "v1", date(2025, 7, 1), None, True)])
    _publish(session, users["sup_a"], "〔合成〕幸福園異常事件SOP", "sop", "org", ["residential"], [
        ("happy_incident_sop.pdf", "v1", date(2024, 5, 1), None, True)])
    _publish(session, users["sup_a"], "〔合成〕幸福園交班注意事項", "internal_rule", "org", ["residential"], [
        ("happy_handover_notes.md", "v1", date(2026, 2, 1), None, True)])
    _, pine_versions = _publish(session, users["sup_pine"], "〔合成〕松柏居服務範圍內規", "internal_rule", "org",
                                ["residential"], [("pine_scope_rules.md", "v1", date(2026, 1, 1), None, True)])
    session.commit()
    for name, user in users.items():
        w.ids[name] = user.id
    w.ids["org:HAPPY"], w.ids["org:PINE"] = happy.id, pine.id
    w.ids["reg_v1"], w.ids["reg_v2"] = reg_versions[0].id, reg_versions[1].id
    w.ids["happy_scope"], w.ids["pine_scope"] = scope_versions[0].id, pine_versions[0].id
    session.close()
    return w


@pytest.fixture
def client() -> TestClient:
    """FastAPI 測試 client。"""
    return TestClient(app)


def login_liff(client: TestClient, username: str) -> dict[str, str]:
    """以模擬 LIFF token 登入，回傳 Authorization header。"""
    response = client.post("/api/auth/liff", json={"id_token": f"dev:{line_id(username)}"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok", body
    return {"Authorization": f"Bearer {body['session_token']}"}


def login_web(client: TestClient, username: str) -> dict[str, str]:
    """後台帳密登入。"""
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['session_token']}"}


def new_id() -> str:
    """client_request_id。"""
    return str(uuid.uuid4())


def make_wav(path: Path, seconds: float = 1.5) -> Path:
    """產生測試用 wav（440 Hz）。"""
    import math
    import struct
    import wave

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"".join(struct.pack("<h", int(2000 * math.sin(2 * math.pi * 440 * i / 16000)))
                                    for i in range(int(16000 * seconds))))
    return path


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    shutil.rmtree(_DATA_DIR, ignore_errors=True)

"""A11：版本管理——新版發布前不破壞現行版、過期文件不混入、歷史回答可追溯。"""

from __future__ import annotations

from sqlalchemy import select

from app.db import new_session
from app.models import DocumentVersion
from app.worker import drain
from tests.conftest import DOCS, login_liff, login_web, new_id


def ask(client, headers, question):
    return client.post("/api/qa/ask", headers=headers, json={"question": question,
                                                             "client_request_id": new_id()}).json()


def test_version_supersede_and_history(client, world):
    """先讓 v2 停用：答案引 v1；恢復一個新版後答案改引新版，舊回答仍指向 v1 並可開啟。"""
    admin = login_web(client, "admin_happy")
    cg = login_liff(client, "cg1")
    # 1) 停用 v2 → 現行只剩 v1（v1 有失效日 2025-12-31，今天已過期 → 無現行版）
    client.post(f"/api/admin/versions/{world.ids['reg_v2']}/deactivate", headers=admin)
    none_now = ask(client, cg, "夜間每多少位住民要配置一名照服員？")
    assert none_now["outcome"] == "escalated"  # 過期的 v1 不混入現行查詢
    # 2) 上傳 v3（內容同 v2），發布前不影響查詢
    docs = client.get("/api/admin/documents", headers=admin).json()
    reg = next(d for d in docs if d["title"] == "〔合成〕營運規範")
    with (DOCS / "reg_operation_v2.md").open("rb") as handle:
        uploaded = client.post(f"/api/admin/documents/{reg['id']}/versions", headers=admin,
                               data={"version_label": "第 3 版", "effective_from": "2026-01-01",
                                     "source": "〔合成〕測試"},
                               files={"file": ("v3.md", handle, "text/markdown")}).json()
    drain()
    preview = client.get(f"/api/admin/versions/{uploaded['id']}", headers=admin).json()
    assert preview["status"] == "review" and preview["chunk_count"] == 8
    assert ask(client, cg, "夜間每多少位住民要配置一名照服員？")["outcome"] == "escalated"
    client.post(f"/api/admin/versions/{uploaded['id']}/publish", headers=admin)
    answer = ask(client, cg, "夜間每多少位住民要配置一名照服員？")
    assert answer["outcome"] == "answered"
    assert answer["citations"][0]["version_label"] == "第 3 版"


def test_history_points_to_old_version(client, world):
    """歷史回答永遠指向當時的版本：新版發布後，舊回答的出處仍是舊版原文。"""
    admin = login_web(client, "admin_happy")
    cg = login_liff(client, "cg1")
    old = ask(client, cg, "夜間每多少位住民要配置一名照服員？")
    assert old["citations"][0]["version_label"] == "第 2 版"
    docs = client.get("/api/admin/documents", headers=admin).json()
    reg = next(d for d in docs if d["title"] == "〔合成〕營運規範")
    modified = (DOCS / "reg_operation_v2.md").read_text(encoding="utf-8").replace("每二十位", "每十五位")
    uploaded = client.post(f"/api/admin/documents/{reg['id']}/versions", headers=admin,
                           data={"version_label": "第 3 版", "effective_from": "2026-06-01", "source": "〔合成〕測試"},
                           files={"file": ("v3.md", modified.encode("utf-8"), "text/markdown")}).json()
    drain()
    client.post(f"/api/admin/versions/{uploaded['id']}/publish", headers=admin)
    new = ask(client, cg, "夜間每多少位住民要配置一名照服員？")
    assert new["citations"][0]["version_label"] == "第 3 版" and "十五位" in new["answer_text"]
    # 舊回答
    replay = client.get(f"/api/qa/{old['id']}", headers=cg).json()
    assert replay["citations"][0]["version_label"] == "第 2 版"
    source = client.get(replay["citations"][0]["source_url"], headers=cg).json()
    assert "二十位" in source["chunk"]["text"] and source["version"]["version_label"] == "第 2 版"


def test_future_version_does_not_replace_current(client, world):
    admin = login_web(client, "admin_happy")
    cg = login_liff(client, "cg1")
    docs = client.get("/api/admin/documents", headers=admin).json()
    reg = next(d for d in docs if d["title"] == "〔合成〕營運規範")
    modified = (DOCS / "reg_operation_v2.md").read_text(encoding="utf-8").replace("每二十位", "每十位")
    uploaded = client.post(f"/api/admin/documents/{reg['id']}/versions", headers=admin,
                           data={"version_label": "未來版", "effective_from": "2099-01-01", "source": "〔合成〕測試"},
                           files={"file": ("v9.md", modified.encode("utf-8"), "text/markdown")}).json()
    drain()
    client.post(f"/api/admin/versions/{uploaded['id']}/publish", headers=admin)
    answer = ask(client, cg, "夜間每多少位住民要配置一名照服員？")
    assert answer["citations"][0]["version_label"] == "第 2 版"


def test_missing_fields_block_publish(client, world):
    sup = login_web(client, "sup_a")
    created = client.post("/api/admin/documents", headers=sup, json={
        "title": "〔合成〕待補測試", "doc_type": "internal_rule", "scope": "org", "facility_types": ["residential"]}).json()
    version = client.post(f"/api/admin/documents/{created['id']}/versions", headers=sup,
                          data={"version_label": "草稿"},
                          files={"file": ("d.md", "一、測試\n測試內容一二三四五六七。".encode(), "text/markdown")}).json()
    drain()
    preview = client.get(f"/api/admin/versions/{version['id']}", headers=sup).json()
    assert set(preview["missing_fields"]) == {"effective_from", "source"}
    response = client.post(f"/api/admin/versions/{version['id']}/publish", headers=sup)
    assert response.status_code == 422 and response.json()["error"]["code"] == "missing_fields"
    client.patch(f"/api/admin/versions/{version['id']}", headers=sup,
                 json={"effective_from": "2026-01-01", "source": "督導上傳（測試）"})
    assert client.post(f"/api/admin/versions/{version['id']}/publish", headers=sup).status_code == 200


def test_parse_failure_reported(client, world):
    sup = login_web(client, "sup_a")
    created = client.post("/api/admin/documents", headers=sup, json={
        "title": "壞檔", "doc_type": "sop", "scope": "org", "facility_types": ["residential"]}).json()
    version = client.post(f"/api/admin/documents/{created['id']}/versions", headers=sup,
                          data={"version_label": "v1"},
                          files={"file": ("x.pdf", b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 10, "application/pdf")}).json()
    drain()
    session = new_session()
    row = session.get(DocumentVersion, version["id"])
    assert row.status == "parse_failed" and row.parse_error
    session.close()


def test_published_version_metadata_locked(client, world):
    admin = login_web(client, "admin_happy")
    response = client.patch(f"/api/admin/versions/{world.ids['reg_v2']}", headers=admin,
                            json={"effective_from": "2020-01-01"})
    assert response.status_code == 409


def test_coverage_lists_current_only(client, world):
    cg = login_liff(client, "cg1")
    coverage = client.get("/api/documents/coverage", headers=cg).json()
    labels = {(d["title"], d["version_label"]) for d in coverage["documents"]}
    assert ("〔合成〕營運規範", "第 2 版") in labels
    assert ("〔合成〕營運規範", "第 1 版") not in labels
    assert not any("居家" in title or "松柏居" in title for title, _ in labels)
    session = new_session()
    assert session.scalar(select(DocumentVersion.status).where(DocumentVersion.id == world.ids["reg_v1"])) == "published"
    session.close()

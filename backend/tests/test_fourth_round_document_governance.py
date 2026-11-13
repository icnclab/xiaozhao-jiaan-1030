"""第四輪：保存原檔閱讀與主任／督導草稿權限，不提升發布權限。"""

from __future__ import annotations

import io
from pathlib import Path

from sqlalchemy import select

from app.db import new_session
from app.models import Document, DocumentVersion, User
from tests.conftest import login_web


def _login_director(client):
    session = new_session()
    user = session.scalar(select(User).where(User.username == "sup_a"))
    user.role = "director"
    session.commit()
    session.close()
    return login_web(client, "sup_a")


def test_director_can_create_org_draft_but_cannot_publish(client, world):
    headers = _login_director(client)
    created = client.post("/api/admin/documents", headers=headers, json={
        "title": "第四輪主任草稿", "doc_type": "other", "scope": "org", "facility_types": ["home"],
    })
    assert created.status_code == 200
    uploaded = client.post(
        f"/api/admin/documents/{created.json()['id']}/versions", headers=headers,
        data={"version_label": "draft-v1", "source": "人工待審"},
        files={"file": ("draft.txt", io.BytesIO("安全草稿內容".encode()), "text/plain")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["status"] == "uploaded"
    denied = client.post(f"/api/admin/versions/{uploaded.json()['id']}/publish", headers=headers, json={})
    assert denied.status_code == 403


def test_saved_pdf_is_inline_and_cross_org_hidden(client, world):
    admin = login_web(client, "admin_happy")
    session = new_session()
    pdf = session.scalar(select(DocumentVersion).where(DocumentVersion.file_name == "happy_incident_sop.pdf"))
    session.close()
    result = client.get(f"/api/admin/versions/{pdf.id}/file", headers=admin)
    assert result.status_code == 200
    assert result.headers["content-type"].startswith("application/pdf")
    assert "inline;" in result.headers["content-disposition"]
    pine = login_web(client, "sup_pine")
    hidden = client.get(f"/api/admin/versions/{pdf.id}/file", headers=pine)
    assert hidden.status_code == 404


def test_duplicate_upload_gets_warning(client, world):
    admin = login_web(client, "admin_happy")
    session = new_session()
    original = session.scalar(select(DocumentVersion).where(DocumentVersion.file_name == "happy_incident_sop.pdf"))
    document_id, file_name, mime, data = original.document_id, original.file_name, original.mime, Path(original.file_path).read_bytes()
    session.close()
    result = client.post(
        f"/api/admin/documents/{document_id}/versions", headers=admin,
        data={"version_label": "duplicate-fourth-round", "source": "測試"},
        files={"file": (file_name, io.BytesIO(data), mime)},
    )
    assert result.status_code == 200
    assert any("SHA-256 相同" in item for item in result.json()["warnings"])

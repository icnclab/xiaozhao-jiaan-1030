"""原文連結應讓瀏覽器直接開啟 PDF，而不是強制下載；docx 等無法安全預覽的格式維持下載。"""

from __future__ import annotations

from sqlalchemy import select

from app.db import new_session
from app.models import DocumentVersion
from tests.conftest import login_liff


def test_pdf_file_is_inline_and_docx_stays_attachment(client, world):
    happy = login_liff(client, "cg1")
    session = new_session()
    pdf_version = session.scalar(select(DocumentVersion).where(DocumentVersion.file_name == "happy_incident_sop.pdf"))
    docx_version = session.scalar(select(DocumentVersion).where(DocumentVersion.file_name == "happy_transfer_sop.docx"))
    session.close()

    pdf_result = client.get(f"/api/sources/versions/{pdf_version.id}/file", headers=happy)
    assert pdf_result.status_code == 200
    assert "inline;" in pdf_result.headers["content-disposition"]

    docx_result = client.get(f"/api/sources/versions/{docx_version.id}/file", headers=happy)
    assert docx_result.status_code == 200
    assert "attachment;" in docx_result.headers["content-disposition"]

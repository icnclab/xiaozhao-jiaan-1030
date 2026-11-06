"""知識庫文件：建立、上傳版本、解析入庫、發布、停用，以及「現行版本」查詢。

「現行版本」在查詢時計算：同一文件的 published 版本中，取生效區間涵蓋查詢日、
生效日最新的一版。所以新版以未來生效日發布時，舊版照常服務到生效日；
歷史引用指向 chunk，chunk 永久屬於當時的版本。
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Chunk, Document, DocumentVersion, User
from app.providers.embedding import get_embedding_provider
from app.services import audit, jobs
from app.services.ingest import ParseError, chunk, parse
from app.services.text import tsvector_source

DOC_TYPES = {"regulation", "internal_rule", "sop", "other"}
FACILITY_TYPES = {"residential", "home", "community"}
REQUIRED_FIELDS = ("effective_from", "source")


class DocumentError(Exception):
    """文件操作錯誤。

    Attributes:
        code: 機器可讀錯誤碼。
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def missing_fields(version: DocumentVersion) -> list[str]:
    """回傳尚待補齊的必要欄位（不自行推測日期或來源）。"""
    return [name for name in REQUIRED_FIELDS if not getattr(version, name)]


def create_document(
    session: Session, actor: User, *, title: str, doc_type: str, scope: str, facility_types: list[str]
) -> Document:
    """建立文件。

    Args:
        session: ORM session。
        actor: 建立者（督導或管理員）。
        title: 文件名。
        doc_type: regulation、internal_rule、sop、other。
        scope: org（本機構）或 shared（全機構共用，限管理員）。
        facility_types: 適用機構類型。

    Returns:
        新文件。

    Raises:
        DocumentError: 參數不合法或權限不足。
    """
    if doc_type not in DOC_TYPES:
        raise DocumentError("invalid_doc_type", "文件類型不正確")
    if not facility_types or not set(facility_types) <= FACILITY_TYPES:
        raise DocumentError("invalid_facility_types", "請選擇適用機構類型")
    if scope not in {"org", "shared"}:
        raise DocumentError("invalid_scope", "範圍不正確")
    if scope == "shared" and actor.role != "admin":
        raise DocumentError("forbidden", "只有管理員可以建立全機構共用文件")
    document = Document(
        org_id=None if scope == "shared" else actor.org_id,
        title=title.strip()[:200],
        doc_type=doc_type,
        facility_types=sorted(set(facility_types)),
        created_by=actor.id,
    )
    session.add(document)
    session.flush()
    audit.record(session, "doc.create", actor=actor, target_type="document", target_id=document.id,
                 meta={"scope": scope, "doc_type": doc_type})
    return document


def add_version(
    session: Session,
    actor: User,
    document: Document,
    *,
    file_name: str,
    data: bytes,
    version_label: str,
    effective_from: date | None,
    effective_to: date | None,
    source: str | None,
    source_url: str | None,
) -> DocumentVersion:
    """上傳新版本並排入解析工作。現行版本不受影響，直到新版被發布且生效。

    Args:
        session: ORM session。
        actor: 上傳者。
        document: 所屬文件。
        file_name: 原始檔名（只作顯示）。
        data: 檔案內容。
        version_label: 版本標籤。
        effective_from: 生效日（可空，空則列為待補）。
        effective_to: 失效日（可空）。
        source: 來源說明（可空，空則列為待補）。
        source_url: 原始出處網址（可空；由人填寫，系統不推測）。

    Returns:
        新版本。

    Raises:
        DocumentError: 檔案過大、版本重複、日期不合理。
    """
    settings = get_settings()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise DocumentError("too_large", f"檔案超過 {settings.max_upload_mb} MB")
    if not data:
        raise DocumentError("empty", "檔案是空的")
    if effective_from and effective_to and effective_to < effective_from:
        raise DocumentError("invalid_dates", "失效日不可早於生效日")
    label = version_label.strip()[:50]
    if not label:
        raise DocumentError("invalid_label", "請填寫版本標籤")
    exists = session.scalar(
        select(DocumentVersion.id).where(
            DocumentVersion.document_id == document.id, DocumentVersion.version_label == label
        )
    )
    if exists:
        raise DocumentError("duplicate_version", "此文件已有相同版本標籤")
    if source_url and not re.match(r"^https?://", source_url):
        raise DocumentError("invalid_source_url", "出處網址須為 http(s)")
    version_id = uuid.uuid4()
    safe_name = re.sub(r"[^\w.\-一-鿿]", "_", Path(file_name).name)[:120] or "upload.bin"
    folder = settings.data_dir / "documents" / str(version_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / safe_name
    path.write_bytes(data)
    version = DocumentVersion(
        id=version_id,
        document_id=document.id,
        version_label=label,
        status="uploaded",
        effective_from=effective_from,
        effective_to=effective_to,
        source=(source or "").strip()[:300] or None,
        source_url=(source_url or "").strip()[:500] or None,
        file_path=str(path),
        file_name=safe_name,
        file_sha256=hashlib.sha256(data).hexdigest(),
        mime="application/octet-stream",
        uploaded_by=actor.id,
        warnings=[],
    )
    session.add(version)
    session.flush()
    jobs.enqueue(session, "doc_ingest", {"version_id": str(version_id)}, f"doc_ingest:{version_id}")
    audit.record(session, "doc.upload", actor=actor, org_id=actor.org_id, target_type="document_version",
                 target_id=version_id, meta={"document_id": str(document.id), "bytes": len(data)})
    return version


def ingest_version(session: Session, version_id: uuid.UUID) -> DocumentVersion:
    """解析、切塊、嵌入並寫入切塊；完成後狀態為 review（待檢查、待發布）。

    Args:
        session: ORM session（由呼叫端 commit）。
        version_id: 版本 ID。

    Returns:
        更新後的版本。
    """
    version = session.get(DocumentVersion, version_id)
    if version is None:
        raise DocumentError("not_found", "版本不存在")
    if version.status not in {"uploaded", "parsing"}:
        return version  # 冪等：已處理過
    version.status = "parsing"
    session.flush()
    data = Path(version.file_path).read_bytes()
    try:
        parsed = parse(data)
    except ParseError as exc:
        version.status = "parse_failed"
        version.parse_error = str(exc)
        return version
    drafts, extra_warnings = chunk(parsed)
    warnings = list(parsed.warnings) + extra_warnings
    document = session.get(Document, version.document_id)
    if document and document.doc_type == "regulation" and not any(d.article_no for d in drafts):
        warnings.append("法規類文件未偵測到「第 X 條」結構，已改按段落切塊")
    if not drafts:
        version.status = "parse_failed"
        version.parse_error = "切塊結果為空"
        return version
    session.execute(text("DELETE FROM chunks WHERE version_id = :v"), {"v": version.id})
    provider = get_embedding_provider()
    vectors = provider.embed_documents([d.text for d in drafts])
    for draft, vector in zip(drafts, vectors, strict=True):
        chunk_row = Chunk(
            version_id=version.id,
            seq=draft.seq,
            locator=draft.locator,
            article_no=draft.article_no,
            page_no=draft.page_no,
            heading=draft.heading,
            text=draft.text,
            embedding=vector,
            embedding_model=provider.model,
        )
        session.add(chunk_row)
        session.flush()
        session.execute(
            text("UPDATE chunks SET tsv = to_tsvector('simple', :src) WHERE id = :id"),
            {"src": tsvector_source(draft.text), "id": chunk_row.id},
        )
    version.mime = parsed.mime
    version.page_count = sum(1 for p in parsed.pages if p.number is not None) or None
    version.chunk_count = len(drafts)
    version.warnings = warnings
    version.status = "review"
    return version


def publish(session: Session, actor: User, version: DocumentVersion) -> DocumentVersion:
    """發布版本（待補欄位必須清空）。舊版本不刪除，由生效日決定誰是現行版。

    Args:
        session: ORM session。
        actor: 發布者。
        version: 版本。

    Returns:
        已發布版本。

    Raises:
        DocumentError: 狀態不允許或欄位待補。
    """
    if version.status != "review":
        raise DocumentError("invalid_state", "只有待檢查（已解析）的版本可以發布")
    missing = missing_fields(version)
    if missing:
        raise DocumentError("missing_fields", "請先補齊：" + "、".join(missing))
    version.status = "published"
    version.published_by = actor.id
    version.published_at = jobs.utcnow()
    audit.record(session, "doc.publish", actor=actor, target_type="document_version", target_id=version.id,
                 meta={"document_id": str(version.document_id), "version_label": version.version_label})
    return version


def deactivate(session: Session, actor: User, version: DocumentVersion) -> DocumentVersion:
    """停用版本：不再被檢索，但歷史引用仍可開啟。"""
    if version.status not in {"review", "published"}:
        raise DocumentError("invalid_state", "此版本目前狀態不能停用")
    version.status = "deactivated"
    version.deactivated_by = actor.id
    version.deactivated_at = jobs.utcnow()
    audit.record(session, "doc.deactivate", actor=actor, target_type="document_version", target_id=version.id)
    return version


CURRENT_VERSIONS_SQL = """
    SELECT DISTINCT ON (dv.document_id) dv.id AS version_id, dv.document_id
    FROM document_versions dv
    JOIN documents d ON d.id = dv.document_id
    WHERE dv.status = 'published'
      AND dv.effective_from <= :today
      AND (dv.effective_to IS NULL OR dv.effective_to >= :today)
      AND (d.org_id IS NULL OR d.org_id = :org_id)
      AND :facility_type = ANY(d.facility_types)
    ORDER BY dv.document_id, dv.effective_from DESC, dv.published_at DESC
"""


def current_versions(session: Session, org_id: uuid.UUID, facility_type: str, today: date) -> list[uuid.UUID]:
    """某機構在某日可用的現行版本 ID 清單。"""
    rows = session.execute(
        text(CURRENT_VERSIONS_SQL), {"today": today, "org_id": org_id, "facility_type": facility_type}
    ).all()
    return [row.version_id for row in rows]


def document_visible_to(document: Document, user: User) -> bool:
    """文件是否屬於使用者機構（或共用）。"""
    return document.org_id is None or document.org_id == user.org_id

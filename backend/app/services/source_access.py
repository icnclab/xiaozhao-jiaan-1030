"""One source policy for excerpts, files and signed download redemption.

Current availability uses the existing RAG rule. Historical availability requires
an accessible, persisted reference, never merely a supplied document identifier.
"""
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import String, cast, exists, func, select
from sqlalchemy.orm import Session

from app.auth import deny_not_found
from app.models import Case, Chunk, Citation, Document, DocumentVersion, Organization, QaItem, User
from app.services.documents import current_versions

ROLES = {"caregiver", "supervisor", "admin"}


def _deny() -> None:
    raise HTTPException(404, detail={"code": "not_found", "message": "找不到資料"})


def historical_reference(db: Session, user: User, version: DocumentVersion) -> bool:
    query = (select(Citation.id).join(QaItem, QaItem.id == Citation.qa_item_id)
             .join(Chunk, Chunk.id == Citation.chunk_id)
             .where(Citation.version_id == version.id, Chunk.version_id == version.id,
                    QaItem.org_id == user.org_id, QaItem.created_at >= version.published_at))
    if user.role == "caregiver":
        query = query.where(QaItem.user_id == user.id)
    if db.scalar(query.limit(1)) is not None:
        return True
    if user.role not in {"supervisor", "admin"}:
        return False
    # Escalated cases expose persisted retrieval candidates, not just final citations.
    # Match real chunks of this exact version, inside the same authorized org/case.
    referenced_chunk = exists(select(Chunk.id).where(
        Chunk.version_id == version.id,
        QaItem.checks["retrieval"].contains(
            func.jsonb_build_array(func.jsonb_build_object("chunk_id", cast(Chunk.id, String))))))
    candidates = (select(QaItem.id).join(Case, Case.qa_item_id == QaItem.id)
                  .where(QaItem.org_id == user.org_id, Case.org_id == user.org_id,
                         QaItem.created_at >= version.published_at, referenced_chunk).limit(1))
    return db.scalar(candidates) is not None


def visible_version(db: Session, user: User, version_id: uuid.UUID) -> tuple[DocumentVersion, Document]:
    if user.role not in ROLES or not user.is_active:
        _deny()
    version = db.get(DocumentVersion, version_id)
    document = db.get(Document, version.document_id) if version else None
    org = db.get(Organization, user.org_id)
    if version is None or document is None or org is None:
        _deny()
    if document.org_id is not None and document.org_id != user.org_id:
        raise deny_not_found(db, user, "document_version", version_id)
    if org.facility_type not in (document.facility_types or []):
        _deny()
    today = datetime.now(ZoneInfo("Asia/Taipei")).date()
    if version.id in current_versions(db, user.org_id, org.facility_type, today):
        return version, document
    # A deactivated review-only version must not acquire historical privileges.
    if (version.status not in {"published", "deactivated"} or version.published_at is None
            or version.effective_from is None or version.effective_from > today):
        _deny()
    if not historical_reference(db, user, version):
        _deny()
    return version, document

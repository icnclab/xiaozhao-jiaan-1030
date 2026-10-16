"""ORM 資料模型。

命名依關聯與交易需求合併，不強求一個概念一張表：
- 對話與問答合併為 `qa_items`（一問一答一列，`conversation_id` 串起同一次查詢脈絡）。
- 轉錄工作與原始草稿合併為 `transcripts`（草稿加密、到期清除），確認後的遮罩片段在 `transcript_segments`。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

EMBEDDING_DIM = 1024


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Organization(Base):
    """長照機構。`facility_type` 決定哪些文件適用（MVP 以住宿式為主）。"""

    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = _pk()
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    facility_type: Mapped[str] = mapped_column(String(20))  # residential | home | community
    created_at: Mapped[datetime] = _created()


class User(Base):
    """系統帳號。照服員以 LINE 綁定登入，督導與管理員以帳密登入後台。"""

    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20))  # caregiver | supervisor | admin
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = _created()


class LineAccount(Base):
    """LINE userId 與系統帳號的綁定；追蹤封鎖狀態以決定能否推播。"""

    __tablename__ = "line_accounts"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    line_user_id: Mapped[str] = mapped_column(String(64), unique=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    followed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    linked_at: Mapped[datetime] = _created()


class BindingCode(Base):
    """一次性綁定碼（只存雜湊）。"""

    __tablename__ = "binding_codes"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class AuthSession(Base):
    """登入 session（只存 token 雜湊）。"""

    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    kind: Mapped[str] = mapped_column(String(10))  # liff | web | dev
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class Category(Base):
    """問題分類（後台可編輯）；`default_assignee_id` 決定分類回報送到哪位督導。"""

    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("org_id", "name"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    default_assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _created()


class CategoryTemplate(Base):
    """分類下的常見問題模板。"""

    __tablename__ = "category_templates"
    id: Mapped[uuid.UUID] = _pk()
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"), index=True)
    text: Mapped[str] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Document(Base):
    """知識庫文件（不含內容；內容在版本）。`org_id` 為 NULL 表示全機構共用（限管理員建立）。"""

    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    doc_type: Mapped[str] = mapped_column(String(20))  # regulation | internal_rule | sop | other
    facility_types: Mapped[list[str]] = mapped_column(ARRAY(String(20)))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _created()


class DocumentVersion(Base):
    """文件版本。缺生效日或來源時列入 `missing_fields`，清空前不可發布。"""

    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_label"),)
    id: Mapped[uuid.UUID] = _pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), index=True)
    version_label: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), index=True)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str | None] = mapped_column(String(300))
    source_url: Mapped[str | None] = mapped_column(String(500))
    file_path: Mapped[str] = mapped_column(String(500))
    file_name: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64))
    mime: Mapped[str] = mapped_column(String(100))
    page_count: Mapped[int | None] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    warnings: Mapped[list] = mapped_column(JSONB, default=list)
    parse_error: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = _created()
    published_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deactivated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Chunk(Base):
    """檢索切塊。法規按條文、內規按段落；永久屬於某一版本，歷史引用不會被新版覆寫。"""

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("version_id", "seq"),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
    id: Mapped[uuid.UUID] = _pk()
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_versions.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    locator: Mapped[str] = mapped_column(String(100))
    article_no: Mapped[str | None] = mapped_column(String(30))
    page_no: Mapped[int | None] = mapped_column(Integer)
    heading: Mapped[str | None] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    tsv: Mapped[str | None] = mapped_column(TSVECTOR)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = _created()


class QaItem(Base):
    """一次問答（問題只存遮罩後文字）。"""

    __tablename__ = "qa_items"
    __table_args__ = (UniqueConstraint("user_id", "client_request_id"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    client_request_id: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(20))
    transcript_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("transcripts.id"))
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"))
    question_masked: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String(20), index=True)
    answer_text: Mapped[str | None] = mapped_column(Text)
    claims: Mapped[list] = mapped_column(JSONB, default=list)
    escalation_reason: Mapped[str | None] = mapped_column(String(50))
    escalation_detail: Mapped[str | None] = mapped_column(Text)
    case_error: Mapped[str | None] = mapped_column(Text)
    checks: Mapped[dict] = mapped_column(JSONB, default=dict)
    llm_provider: Mapped[str] = mapped_column(String(30))
    llm_model: Mapped[str | None] = mapped_column(String(100))
    embedding_provider: Mapped[str] = mapped_column(String(30))
    qa_policy_version: Mapped[str] = mapped_column(String(30))
    timings_ms: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _created()


class Citation(Base):
    """回答引用；同時記 chunk 與版本，歷史回答永遠指向當時的版本。"""

    __tablename__ = "citations"
    __table_args__ = (UniqueConstraint("qa_item_id", "label"),)
    id: Mapped[uuid.UUID] = _pk()
    qa_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("qa_items.id"), index=True)
    chunk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chunks.id"), index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_versions.id"), index=True)
    label: Mapped[str] = mapped_column(String(10))
    rank: Mapped[int] = mapped_column(Integer)
    support_score: Mapped[float | None]
    created_at: Mapped[datetime] = _created()


class Transcript(Base):
    """轉錄工作。未遮罩草稿加密存於 `draft_encrypted`，確認或到期即清除。"""

    __tablename__ = "transcripts"
    __table_args__ = (UniqueConstraint("user_id", "client_upload_id"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    mode: Mapped[str] = mapped_column(String(20))  # question | conversation
    channel: Mapped[str] = mapped_column(String(10))  # liff | line
    client_upload_id: Mapped[str] = mapped_column(String(64))
    line_message_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    consent_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_text_version: Mapped[str | None] = mapped_column(String(30))
    audio_path: Mapped[str | None] = mapped_column(String(500))
    audio_mime: Mapped[str | None] = mapped_column(String(100))
    audio_duration_ms: Mapped[int | None] = mapped_column(Integer)
    audio_size: Mapped[int | None] = mapped_column(Integer)
    audio_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    audio_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    draft_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    draft_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    draft_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    speaker_roles: Mapped[dict] = mapped_column(JSONB, default=dict)
    summary_masked: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    stt_provider: Mapped[str | None] = mapped_column(String(30))
    stt_model: Mapped[str | None] = mapped_column(String(100))
    stt_ms: Mapped[int | None] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = _created()
    draft_ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TranscriptSegment(Base):
    """確認後的轉錄片段（遮罩後）。"""

    __tablename__ = "transcript_segments"
    __table_args__ = (UniqueConstraint("transcript_id", "idx"),)
    id: Mapped[uuid.UUID] = _pk()
    transcript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("transcripts.id"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(String(20))  # speaker_1.. | unknown
    text_masked: Mapped[str] = mapped_column(Text)
    uncertain: Mapped[bool] = mapped_column(Boolean, default=False)
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)


class TranscriptRevision(Base):
    """修訂軌跡：只記遮罩後的前後文字與說話者變更。"""

    __tablename__ = "transcript_revisions"
    id: Mapped[uuid.UUID] = _pk()
    transcript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("transcripts.id"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    before_masked: Mapped[str] = mapped_column(Text)
    after_masked: Mapped[str] = mapped_column(Text)
    speaker_before: Mapped[str] = mapped_column(String(20))
    speaker_after: Mapped[str] = mapped_column(String(20))
    revised_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _created()


class Case(Base):
    """督導待確認案件。"""

    __tablename__ = "cases"
    __table_args__ = (UniqueConstraint("created_by", "client_request_id"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    number: Mapped[str] = mapped_column(String(30), unique=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    client_request_id: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(20))  # ai_escalation | manual_escalation | quick_report
    qa_item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("qa_items.id"), index=True)
    transcript_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("transcripts.id"))
    summary_masked: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), index=True)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    first_replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CaseEvent(Base):
    """案件狀態歷程（append-only）。"""

    __tablename__ = "case_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(30))
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str | None] = mapped_column(String(20))
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _created()


class CaseMessage(Base):
    """案件內的訊息：督導回覆或照服員補充。"""

    __tablename__ = "case_messages"
    __table_args__ = (UniqueConstraint("author_id", "client_request_id"),)
    id: Mapped[uuid.UUID] = _pk()
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    author_role: Mapped[str] = mapped_column(String(20))
    body: Mapped[str] = mapped_column(Text)
    client_request_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _created()


class NotificationJob(Base):
    """通知工作。`accepted` 表示 LINE 平臺已受理，不代表已送達。"""

    __tablename__ = "notification_jobs"
    __table_args__ = (UniqueConstraint("source_type", "source_id", "channel"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(30))  # case_message | answer | transcript
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    channel: Mapped[str] = mapped_column(String(10))  # line
    status: Mapped[str] = mapped_column(String(20), index=True)  # queued|sending|accepted|failed|skipped
    retry_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=_uuid)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(50))
    last_error: Mapped[str | None] = mapped_column(Text)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Feedback(Base):
    """回答回饋（回答有誤／有幫助）。"""

    __tablename__ = "feedback"
    __table_args__ = (UniqueConstraint("qa_item_id", "user_id", "kind"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    qa_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("qa_items.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(10))  # wrong | helpful
    reason_masked: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | reviewed
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class AuditLog(Base):
    """稽核紀錄（append-only，DB 觸發器禁止更新與刪除）。不存未遮罩文字與 token。"""

    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    actor_role: Mapped[str | None] = mapped_column(String(20))
    action: Mapped[str] = mapped_column(String(50), index=True)
    target_type: Mapped[str | None] = mapped_column(String(30))
    target_id: Mapped[str | None] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(10))  # ok | denied | error
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _created()


class LineEvent(Base):
    """LINE webhook 事件。只存識別與類型；文字內容加密暫存，處理完即清除。"""

    __tablename__ = "line_events"
    id: Mapped[uuid.UUID] = _pk()
    webhook_event_id: Mapped[str] = mapped_column(String(64), unique=True)
    event_type: Mapped[str] = mapped_column(String(30))
    message_type: Mapped[str | None] = mapped_column(String(20))
    message_id: Mapped[str | None] = mapped_column(String(64))
    line_user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    reply_token: Mapped[str | None] = mapped_column(String(100))
    is_redelivery: Mapped[bool] = mapped_column(Boolean, default=False)
    redelivery_count: Mapped[int] = mapped_column(Integer, default=0)
    content_provider: Mapped[str | None] = mapped_column(String(20))
    payload_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(20), default="received")
    error: Mapped[str | None] = mapped_column(Text)
    event_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = _created()
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LineMockOutbox(Base):
    """模擬模式下的 reply／push 紀錄（不會真的送到 LINE）。"""

    __tablename__ = "line_mock_outbox"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(10))  # reply | push
    to: Mapped[str | None] = mapped_column(String(100))
    messages: Mapped[list] = mapped_column(JSONB)
    retry_key: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = _created()


class Job(Base):
    """可恢復的背景工作。`idempotency_key` 唯一，避免重複排入。"""

    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_pick", "status", "run_after"),)
    id: Mapped[uuid.UUID] = _pk()
    kind: Mapped[str] = mapped_column(String(30), index=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(10), default="queued")  # queued|running|done|failed|dead
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TtsAsset(Base):
    """回答的語音檔。播放 URL 以隨機 token＋簽章＋到期時間保護。"""

    __tablename__ = "tts_assets"
    id: Mapped[uuid.UUID] = _pk()
    qa_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("qa_items.id"), unique=True)
    status: Mapped[str] = mapped_column(String(10))  # queued|running|ready|failed|expired
    provider: Mapped[str] = mapped_column(String(20))
    file_path: Mapped[str | None] = mapped_column(String(500))
    mime: Mapped[str | None] = mapped_column(String(50))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    token_id: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    error: Mapped[str | None] = mapped_column(Text)
    tts_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created()


class DeidTerm(Base):
    """機構自訂遮罩詞（只存 HMAC，不存明文），例如住民常用暱稱。"""

    __tablename__ = "deid_terms"
    __table_args__ = (UniqueConstraint("org_id", "term_hmac"),)
    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    term_hmac: Mapped[str] = mapped_column(String(64))
    length: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = _created()


class WorkerHeartbeat(Base):
    """Worker 心跳，供健康檢查。"""

    __tablename__ = "worker_heartbeats"
    worker_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

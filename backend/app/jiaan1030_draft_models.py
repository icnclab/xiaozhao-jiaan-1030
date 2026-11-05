"""GA09/SC09 服務紀錄草稿；關聯獨立的服務個案主檔（jiaan1030_service_clients），不綁定 cases（問題回報工單）。"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, String, Table, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# jiaan1030_service_forms 本身用 raw SQL 操作（見 app/api/jiaan1030_service_catalog.py），無完整 ORM model。
# 這裡只註冊最小欄位供 FK 解析使用，不透過 ORM 寫入此表；實際結構由 migration 0003 定義。
jiaan1030_service_forms = Table(
    "jiaan1030_service_forms",
    Base.metadata,
    Column("code", String(20), primary_key=True),
    Column("reviewed", Boolean),
    extend_existing=True,
)


class Jiaan1030ServiceFormDraft(Base):
    """GA09/SC09 等服務紀錄表單的填寫草稿；僅在對應 form 的 reviewed 與 schema_status 皆核准後才可送出。"""

    __tablename__ = "jiaan1030_service_form_drafts"
    __table_args__ = (
        CheckConstraint("status IN ('draft','submitted')", name="ck_jiaan1030_drafts_status"),
        UniqueConstraint("created_by", "client_request_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    service_client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jiaan1030_service_clients.id"), index=True)
    form_code: Mapped[str] = mapped_column(ForeignKey("jiaan1030_service_forms.code"), index=True)
    client_request_id: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

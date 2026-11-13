"""隔離提案：群組與明確的業務讀取授權；不改 QA、案件或錄音表。"""
import uuid
from datetime import datetime
from sqlalchemy import ForeignKey, String, DateTime, Boolean, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class Interaction(Base):
    __tablename__ = "service_interactions"
    __table_args__ = (UniqueConstraint("owner_id", "start_request_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    start_request_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HistoryGrant(Base):
    """照服員逐群組提出請求，主任核准，雙方均可撤銷；預設不分享。

    每一群組、每位讀者獨立授權，避免把未知長輩／申訴混入廣域查閱。
    supervisor 的 responsible 必須為真；director 必須有 read_approved。
    """
    __tablename__ = "interaction_read_grants"
    __table_args__ = (UniqueConstraint("interaction_id", "viewer_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    interaction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("service_interactions.id"), index=True)
    viewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    approved_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    responsible: Mapped[bool] = mapped_column(Boolean, default=False)
    read_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

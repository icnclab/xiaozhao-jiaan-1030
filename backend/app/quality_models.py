"""Quality-only tables; no modifications to existing QA/case models."""
import uuid
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app import models  # noqa: F401 - FK targets


class QualityFeedback(Base):
    __tablename__ = 'feedback_entries'
    __table_args__ = (
        UniqueConstraint('qa_id', 'submitted_by'),
        CheckConstraint("status IN ('pending_review','verified','rejected')"),
        CheckConstraint("dataset_split IS NULL OR dataset_split IN ('training','validation','test')"),
        {'schema': 'rag_quality'},
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('organizations.id', ondelete='RESTRICT'), index=True)
    qa_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('qa_items.id', ondelete='RESTRICT'), index=True)
    submitted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'))
    qa_snapshot: Mapped[dict] = mapped_column(JSONB)
    submission: Mapped[dict] = mapped_column(JSONB)
    reviewed_correction: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='pending_review', index=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    dataset_split: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QualityReview(Base):
    __tablename__ = 'feedback_reviews'
    __table_args__ = (UniqueConstraint('feedback_id', 'revision'), {'schema': 'rag_quality'})
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feedback_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('rag_quality.feedback_entries.id', ondelete='RESTRICT'), index=True)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('organizations.id', ondelete='RESTRICT'), index=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='RESTRICT'))
    revision: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(20))
    correction: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

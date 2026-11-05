"""GA09/SC09 服務個案主檔（最小化）：與 cases（督導問題回報工單）無關，獨立代表受照顧者。

本階段僅供假資料測試：display_label 僅為照服員自訂代稱，不存放真實姓名、房號或其他個資。
存取政策（無明確授權規則前的保守預設，支援跨居督共用照服員）：建立者可讀寫；任何角色
僅在「同機構」且存在有效（未撤銷）授權紀錄 jiaan1030_service_client_grants 時才可存取，
兩者皆不滿足一律視為不可見。被授權的角色決定能做什麼：照服員可唯讀並建立自己的服務草稿；
督導/主任/admin 僅唯讀，不可建立/修改/送出草稿。授權/撤銷只能由建立者或主任/admin 執行。
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Jiaan1030ServiceClient(Base):
    """GA09/SC09 服務個案（受照顧者）主檔，最小化欄位，僅供本批次草稿功能關聯使用。"""

    __tablename__ = "jiaan1030_service_clients"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    display_label: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Jiaan1030ServiceClientGrant(Base):
    """明確授權：讓特定使用者（照服員可唯讀+建立自己的草稿；督導/主任/admin 僅唯讀）
    存取特定服務個案；未撤銷（revoked_at IS NULL）才有效。支援跨居督共用照服員情境。"""

    __tablename__ = "jiaan1030_service_client_grants"
    __table_args__ = (UniqueConstraint("service_client_id", "grantee_id", name="uq_jiaan1030_client_grant"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jiaan1030_service_clients.id"), index=True)
    grantee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    granted_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PermissionScope(Base):
    __tablename__ = "permission_scopes"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "platform",
            "account_id",
            "chat_key",
            name="uq_permission_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    platform: Mapped[str] = mapped_column(String(32), index=True)
    account_id: Mapped[str] = mapped_column(String(128), index=True)
    chat_key: Mapped[str] = mapped_column(String(255), index=True)
    read_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    write_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    relay_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


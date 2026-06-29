from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enums import UserRole


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        Index("ix_roles_name", "name", unique=True),
        Index("ix_roles_access_level", "access_level"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_level: Mapped[UserRole] = mapped_column(Enum(UserRole, name="role_access_level"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)

    users: Mapped[list["User"]] = relationship("User", back_populates="custom_role")

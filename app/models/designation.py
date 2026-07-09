from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enums import DesignationScope


class Designation(Base):
    __tablename__ = "designations"
    __table_args__ = (
        Index("ix_designations_name", "name", unique=True),
        Index("ix_designations_scope_level", "scope_level"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    scope_level: Mapped[DesignationScope] = mapped_column(Enum(DesignationScope, name="designation_scope", create_type=False), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    users: Mapped[list["User"]] = relationship("User", back_populates="designation")

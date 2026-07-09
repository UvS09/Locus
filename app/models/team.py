from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Team(Base):
    __tablename__ = "teams"
    __table_args__ = (
        Index("ix_teams_name", "name", unique=True),
        Index("ix_teams_manager_id", "manager_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    department: Mapped["Department | None"] = relationship("Department", back_populates="teams")
    manager: Mapped["User | None"] = relationship("User", back_populates="managed_team", foreign_keys=[manager_id], post_update=True)
    members: Mapped[list["User"]] = relationship("User", back_populates="team", foreign_keys="User.team_id")
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="team")
    work_items: Mapped[list["WorkItem"]] = relationship("WorkItem")

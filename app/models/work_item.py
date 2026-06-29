from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enums import TaskPriority
from app.utils.work_item_levels import WorkItemLevel, WorkItemStatus


class WorkItem(Base):
    __tablename__ = "work_items"
    __table_args__ = (
        CheckConstraint("progress_percent >= 0 AND progress_percent <= 100", name="ck_work_items_progress_percent"),
        Index("ix_work_items_parent_id", "parent_id"),
        Index("ix_work_items_level", "level"),
        Index("ix_work_items_assigned_to_id", "assigned_to_id"),
        Index("ix_work_items_status", "status"),
        Index("ix_work_items_due_date", "due_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[WorkItemLevel] = mapped_column(Enum(WorkItemLevel, name="work_item_level"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[WorkItemStatus] = mapped_column(Enum(WorkItemStatus, name="work_item_status"), default=WorkItemStatus.PENDING, nullable=False)
    priority: Mapped[TaskPriority] = mapped_column(Enum(TaskPriority, name="work_item_priority"), default=TaskPriority.MEDIUM, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("work_items.id", ondelete="CASCADE"), nullable=True)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    parent: Mapped["WorkItem | None"] = relationship("WorkItem", remote_side="WorkItem.id", back_populates="children")
    children: Mapped[list["WorkItem"]] = relationship("WorkItem", back_populates="parent", cascade="all, delete-orphan")
    team: Mapped["Team | None"] = relationship("Team", back_populates="work_items")
    assignee: Mapped["User | None"] = relationship("User", back_populates="assigned_work_items", foreign_keys=[assigned_to_id])
    creator: Mapped["User | None"] = relationship("User", back_populates="created_work_items", foreign_keys=[created_by_id])

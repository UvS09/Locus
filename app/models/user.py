from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.enums import UserRole


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_email", "email", unique=True),
        Index("ix_users_role", "role"),
        Index("ix_users_custom_role_id", "custom_role_id"),
        Index("ix_users_team_id", "team_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), nullable=False)
    custom_role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id", ondelete="SET NULL"), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    team: Mapped["Team | None"] = relationship("Team", back_populates="members", foreign_keys=[team_id])
    custom_role: Mapped["Role | None"] = relationship("Role", back_populates="users")
    managed_team: Mapped["Team | None"] = relationship(
        "Team",
        back_populates="manager",
        foreign_keys="Team.manager_id",
        uselist=False,
    )
    assigned_tasks: Mapped[list["Task"]] = relationship("Task", back_populates="assignee", foreign_keys="Task.assigned_to_id")
    created_tasks: Mapped[list["Task"]] = relationship("Task", back_populates="creator", foreign_keys="Task.created_by_id")
    assigned_work_items: Mapped[list["WorkItem"]] = relationship("WorkItem", foreign_keys="WorkItem.assigned_to_id")
    created_work_items: Mapped[list["WorkItem"]] = relationship("WorkItem", foreign_keys="WorkItem.created_by_id")
    comments: Mapped[list["Comment"]] = relationship("Comment", back_populates="author")
    notifications: Mapped[list["Notification"]] = relationship("Notification", back_populates="user")
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="actor")

    @property
    def display_role(self) -> str:
        return self.custom_role.name if self.custom_role else self.role.value

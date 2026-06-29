from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notification import Notification


class NotificationRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_for_user(self, user_id: int, limit: int | None = None) -> list[Notification]:
        stmt = select(Notification).where(Notification.user_id == user_id).order_by(Notification.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        return self.db.scalars(stmt).all()

    def unread_count(self, user_id: int) -> int:
        return len(self.db.scalars(select(Notification).where(Notification.user_id == user_id, Notification.is_read.is_(False))).all())

    def get_by_id(self, notification_id: int) -> Notification | None:
        return self.db.get(Notification, notification_id)

    def create(self, notification: Notification) -> Notification:
        self.db.add(notification)
        self.db.flush()
        return notification

    def mark_all_read(self, user_id: int) -> None:
        notifications = self.db.scalars(
            select(Notification).where(Notification.user_id == user_id, Notification.is_read.is_(False))
        ).all()
        now = datetime.now(UTC)
        for item in notifications:
            item.is_read = True
            item.read_at = now

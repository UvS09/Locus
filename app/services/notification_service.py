from datetime import UTC, datetime
import re

from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.task import Task
from app.models.user import User
from app.models.work_item import WorkItem
from app.repositories.notification_repository import NotificationRepository


class NotificationService:
    _WORK_ITEM_REFERENCE = re.compile(r"(Project|Milestone|Activity|Task|Sub-task) #(\d+)")

    def __init__(self, db: Session):
        self.db = db
        self.notification_repo = NotificationRepository(db)

    def create(self, *, user_id: int, message: str, task_id: int | None = None) -> Notification:
        notification = Notification(user_id=user_id, message=message, task_id=task_id)
        return self.notification_repo.create(notification)

    def list_for_user(self, user: User, limit: int | None = None) -> list[Notification]:
        notifications = self.notification_repo.list_for_user(user.id, limit=limit)
        for notification in notifications:
            notification.display_message = self._display_message(notification)
        return notifications

    def _display_message(self, notification: Notification) -> str:
        message = notification.message
        match = self._WORK_ITEM_REFERENCE.search(message)
        if not match:
            return message

        label, item_id = match.groups()
        legacy_task = self.db.get(Task, notification.task_id) if label == "Task" and notification.task_id else None
        item = None if legacy_task else self.db.get(WorkItem, int(item_id))
        if legacy_task:
            message = message.replace(match.group(0), f'Task "{legacy_task.title}"')
        elif item:
            message = message.replace(match.group(0), f'{label} "{item.title}"')

        return (
            message
            .replace(" status changed to COMPLETED", " completed")
            .replace(" status changed to PENDING", " reopened")
            .replace(" status changed to IN_PROGRESS", " started")
            .replace(" status changed to BLOCKED", " blocked")
            .replace(" was closed", " closed")
        )

    def unread_count(self, user: User) -> int:
        return self.notification_repo.unread_count(user.id)

    def mark_read(self, user: User, notification_id: int) -> None:
        notification = self.notification_repo.get_by_id(notification_id)
        if not notification or notification.user_id != user.id:
            raise ValueError("Notification not found.")
        notification.is_read = True
        notification.read_at = datetime.now(UTC)

    def mark_all_read(self, user: User) -> None:
        self.notification_repo.mark_all_read(user.id)

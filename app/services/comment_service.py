from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.comment import CommentCreate
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.services.task_service import TaskAccessMixin


class CommentService(TaskAccessMixin):
    def __init__(self, db: Session):
        self.db = db
        self.audit_service = AuditService(db)
        self.notification_service = NotificationService(db)

    def add_comment(self, actor: User, task_id: int, payload: CommentCreate) -> dict:
        task = self.get_accessible_task(self.db, actor, task_id)
        recipients = {task.assigned_to_id, task.created_by_id} - {None, actor.id}
        for user_id in recipients:
            self.notification_service.create(
                user_id=user_id,
                message=f'Comment on Task "{task.title}" by {actor.full_name}',
                task_id=task.id,
            )
        audit_log = self.audit_service.log_action(
            actor_user_id=actor.id,
            action="task_comment_added",
            entity_type="Task",
            entity_id=task.id,
            details={"content": payload.content},
        )
        return {"id": audit_log.id, "content": payload.content, "created_at": audit_log.created_at}

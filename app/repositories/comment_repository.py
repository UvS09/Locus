from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.comment import Comment


class CommentRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_for_task(self, task_id: int) -> list[Comment]:
        return self.db.scalars(select(Comment).where(Comment.task_id == task_id).order_by(Comment.created_at.asc())).all()

    def create(self, comment: Comment) -> Comment:
        self.db.add(comment)
        self.db.flush()
        return comment

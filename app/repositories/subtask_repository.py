from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.subtask import Subtask


class SubtaskRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, subtask_id: int) -> Subtask | None:
        return self.db.get(Subtask, subtask_id)

    def list_for_task(self, task_id: int) -> list[Subtask]:
        return self.db.scalars(select(Subtask).where(Subtask.task_id == task_id).order_by(Subtask.created_at.asc())).all()

    def create(self, subtask: Subtask) -> Subtask:
        self.db.add(subtask)
        self.db.flush()
        return subtask

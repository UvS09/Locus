from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.department import Department
from app.models.division import Division
from app.models.team import Team
from app.models.work_item import WorkItem
from app.utils.enums import TaskStatus
from app.utils.work_item_levels import WorkItemLevel, WorkItemStatus


class WorkItemRepository:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _team_load():
        return selectinload(WorkItem.team).selectinload(Team.department).selectinload(Department.division)

    def get_by_id(self, work_item_id: int) -> WorkItem | None:
        stmt = (
            select(WorkItem)
            .options(
                selectinload(WorkItem.children),
                selectinload(WorkItem.parent),
                selectinload(WorkItem.assignee),
                selectinload(WorkItem.creator),
                self._team_load(),
            )
            .where(WorkItem.id == work_item_id)
        )
        return self.db.scalar(stmt)

    def list_all(self) -> list[WorkItem]:
        stmt = (
            select(WorkItem)
            .options(selectinload(WorkItem.assignee), selectinload(WorkItem.creator), selectinload(WorkItem.parent), self._team_load())
            .order_by(WorkItem.created_at.desc())
        )
        return self.db.scalars(stmt).all()

    def list_for_team(self, team_id: int) -> list[WorkItem]:
        stmt = (
            select(WorkItem)
            .options(selectinload(WorkItem.assignee), selectinload(WorkItem.creator), selectinload(WorkItem.parent), self._team_load())
            .where(WorkItem.team_id == team_id)
            .order_by(WorkItem.created_at.desc())
        )
        return self.db.scalars(stmt).all()

    def list_for_assignee(self, user_id: int) -> list[WorkItem]:
        stmt = (
            select(WorkItem)
            .options(selectinload(WorkItem.assignee), selectinload(WorkItem.creator), selectinload(WorkItem.parent), self._team_load())
            .where(WorkItem.assigned_to_id == user_id)
            .order_by(WorkItem.created_at.desc())
        )
        return self.db.scalars(stmt).all()

    def list_children(self, parent_id: int) -> list[WorkItem]:
        stmt = (
            select(WorkItem)
            .options(selectinload(WorkItem.assignee), selectinload(WorkItem.creator), selectinload(WorkItem.parent), self._team_load())
            .where(WorkItem.parent_id == parent_id)
            .order_by(WorkItem.created_at.asc())
        )
        return self.db.scalars(stmt).all()

    def list_by_level(
        self,
        *,
        level: WorkItemLevel,
        parent_id: int | None = None,
        team_id: int | None = None,
        assigned_to_id: int | None = None,
    ) -> list[WorkItem]:
        stmt = (
            select(WorkItem)
            .options(selectinload(WorkItem.assignee), selectinload(WorkItem.creator), selectinload(WorkItem.parent), self._team_load())
            .where(WorkItem.level == level)
            .order_by(WorkItem.updated_at.desc())
        )
        if parent_id is not None:
            stmt = stmt.where(WorkItem.parent_id == parent_id)
        if team_id is not None:
            stmt = stmt.where(WorkItem.team_id == team_id)
        if assigned_to_id is not None:
            stmt = stmt.where(WorkItem.assigned_to_id == assigned_to_id)
        return self.db.scalars(stmt).all()

    def list_recent_for_assignee(self, user_id: int, limit: int = 10) -> list[WorkItem]:
        stmt = (
            select(WorkItem)
            .options(selectinload(WorkItem.parent))
            .where(WorkItem.assigned_to_id == user_id)
            .order_by(WorkItem.due_date.asc().nullslast(), WorkItem.updated_at.desc())
            .limit(limit)
        )
        return self.db.scalars(stmt).all()

    def list_recent_updates_for_team(self, team_id: int, limit: int = 8) -> list[WorkItem]:
        stmt = (
            select(WorkItem)
            .options(selectinload(WorkItem.assignee), selectinload(WorkItem.parent))
            .where(WorkItem.team_id == team_id)
            .order_by(WorkItem.updated_at.desc())
            .limit(limit)
        )
        return self.db.scalars(stmt).all()

    def count_by_status(
        self,
        *,
        team_id: int | None = None,
        assigned_to_id: int | None = None,
        status: TaskStatus | WorkItemStatus | None = None,
        level: WorkItemLevel | None = None,
    ) -> int:
        stmt = select(WorkItem)
        if team_id is not None:
            stmt = stmt.where(WorkItem.team_id == team_id)
        if assigned_to_id is not None:
            stmt = stmt.where(WorkItem.assigned_to_id == assigned_to_id)
        if status is not None:
            status_value = status.value if hasattr(status, "value") else status
            stmt = stmt.where(WorkItem.status == status_value)
        if level is not None:
            stmt = stmt.where(WorkItem.level == level)
        return len(self.db.scalars(stmt).all())

    def create(self, work_item: WorkItem) -> WorkItem:
        self.db.add(work_item)
        self.db.flush()
        return work_item

    def delete(self, work_item: WorkItem) -> None:
        self.db.delete(work_item)
        self.db.flush()

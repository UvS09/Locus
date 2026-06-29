from datetime import date

from pydantic import BaseModel, Field

from app.utils.enums import TaskPriority
from app.utils.work_item_levels import WorkItemLevel, WorkItemStatus


class WorkItemCreate(BaseModel):
    level: WorkItemLevel = WorkItemLevel.TASK
    title: str = Field(min_length=2, max_length=255)
    description: str = ""
    assigned_to_id: int | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: date | None = None
    parent_id: int | None = None


class WorkItemUpdate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: str = ""
    assigned_to_id: int | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: date | None = None
    status: WorkItemStatus = WorkItemStatus.PENDING

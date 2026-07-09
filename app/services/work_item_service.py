from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.models.team import Team
from app.models.user import User
from app.models.subtask import Subtask
from app.models.task import Task
from app.models.work_item import WorkItem
from app.repositories.user_repository import UserRepository
from app.repositories.work_item_repository import WorkItemRepository
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.utils.enums import DesignationScope, TaskStatus, UserRole
from app.utils.work_item_levels import WorkItemLevel, WorkItemStatus
from app.schemas.work_item import WorkItemCreate, WorkItemUpdate


_PARENT_LEVEL = {
    WorkItemLevel.OBJECTIVE: None,
    WorkItemLevel.WORKSTREAM: WorkItemLevel.OBJECTIVE,
    WorkItemLevel.ACTIVITY: WorkItemLevel.WORKSTREAM,
    WorkItemLevel.TASK: WorkItemLevel.ACTIVITY,
    WorkItemLevel.SUB_TASK: WorkItemLevel.TASK,
}


class TaskAccessMixin:
    @staticmethod
    def get_accessible_task(db: Session, actor: User, task_id: int) -> WorkItem:
        task = WorkItemRepository(db).get_by_id(task_id)
        if not task:
            raise ValueError("Task not found.")
        if WorkItemService(db)._can_view_item(actor, task):
            return task
        raise ValueError("You do not have access to this task.")


class WorkItemService:
    def __init__(self, db: Session):
        self.db = db
        self.work_item_repo = WorkItemRepository(db)
        self.user_repo = UserRepository(db)
        self.audit_service = AuditService(db)
        self.notification_service = NotificationService(db)

    def _sync_leaf_progress(self, work_item: WorkItem) -> WorkItem:
        if work_item.status == WorkItemStatus.CLOSED:
            work_item.progress_percent = 100
            if work_item.completed_at is None:
                work_item.completed_at = datetime.now(UTC)
            return work_item
        if work_item.status == WorkItemStatus.COMPLETED:
            work_item.progress_percent = 100
            if work_item.completed_at is None:
                work_item.completed_at = datetime.now(UTC)
            return work_item
        if work_item.status == WorkItemStatus.IN_PROGRESS:
            if work_item.progress_percent in {0, 100}:
                work_item.progress_percent = 50
            work_item.completed_at = None
            return work_item
        if work_item.status == WorkItemStatus.BLOCKED:
            # Blocking work changes its state, not the amount already completed.
            work_item.completed_at = None
            return work_item
        work_item.progress_percent = 0
        work_item.completed_at = None
        return work_item

    def _recalculate_progress(self, work_item: WorkItem) -> WorkItem:
        was_manually_blocked = work_item.status == WorkItemStatus.BLOCKED
        children = self.work_item_repo.list_children(work_item.id)
        work_item.children = children
        if not children:
            return self._sync_leaf_progress(work_item)
        total_progress = sum(child.progress_percent for child in children)
        completed_count = sum(1 for child in children if child.status in {WorkItemStatus.COMPLETED, WorkItemStatus.CLOSED})
        blocked_count = sum(1 for child in children if child.status == WorkItemStatus.BLOCKED)
        in_progress_count = sum(1 for child in children if child.status == WorkItemStatus.IN_PROGRESS)
        work_item.progress_percent = int(total_progress / len(children))
        if completed_count == len(children):
            work_item.status = WorkItemStatus.COMPLETED
            if work_item.completed_at is None:
                work_item.completed_at = datetime.now(UTC)
        elif was_manually_blocked:
            work_item.status = WorkItemStatus.BLOCKED
            work_item.completed_at = None
        elif in_progress_count or blocked_count or total_progress > 0:
            work_item.status = WorkItemStatus.IN_PROGRESS
            work_item.progress_percent = min(work_item.progress_percent, 99)
            work_item.completed_at = None
        else:
            work_item.status = WorkItemStatus.PENDING
            work_item.completed_at = None
        return work_item

    def _recalculate_tree_progress(self, work_item: WorkItem) -> WorkItem:
        children = self.work_item_repo.list_children(work_item.id)
        for child in children:
            self._recalculate_tree_progress(child)
        return self._recalculate_progress(work_item)

    def _refresh_ancestor_progress(self, item: WorkItem | None) -> None:
        cursor = item
        while cursor is not None:
            self._recalculate_tree_progress(cursor)
            cursor = cursor.parent

    def refresh_all_progress(self, *, team_id: int | None = None) -> None:
        roots = self.work_item_repo.list_by_level(level=WorkItemLevel.OBJECTIVE, team_id=team_id)
        for root in roots:
            self._recalculate_tree_progress(root)

    @staticmethod
    def _display_name(level: WorkItemLevel) -> str:
        labels = {
            WorkItemLevel.OBJECTIVE: "Project",
            WorkItemLevel.WORKSTREAM: "Milestone",
            WorkItemLevel.ACTIVITY: "Activity",
            WorkItemLevel.TASK: "Task",
            WorkItemLevel.SUB_TASK: "Sub-task",
        }
        return labels[level]

    def _notify_participants(self, item: WorkItem, actor: User, action: str) -> None:
        recipients = {item.assigned_to_id, item.created_by_id} - {None, actor.id}
        message = f'{self._display_name(item.level)} "{item.title}" {action} by {actor.full_name}'
        for user_id in recipients:
            self.notification_service.create(user_id=user_id, message=message, task_id=None)

    def _can_view_team(self, actor: User, team: Team | None) -> bool:
        if actor.role == UserRole.ADMIN:
            return True
        if actor.scope_level in {DesignationScope.SYSTEM_ADMINISTRATOR, DesignationScope.OPERATING_HEAD}:
            return True
        if team is None:
            return False
        if actor.team_id and team.id == actor.team_id:
            return True
        if actor.scope_level == DesignationScope.DIVISION_HEAD:
            return bool(actor.division_id and team.department and team.department.division_id == actor.division_id)
        if actor.scope_level == DesignationScope.DEPARTMENT_HEAD:
            return bool(actor.department_id and team.department_id == actor.department_id)
        return bool(
            (actor.team_id and team.id == actor.team_id)
            or (actor.department_id and team.department_id == actor.department_id)
        )

    def _can_view_user_scope(self, actor: User, user: User | None) -> bool:
        if user is None:
            return False
        if actor.id == user.id:
            return True
        if actor.role == UserRole.ADMIN:
            return True
        if actor.scope_level in {DesignationScope.SYSTEM_ADMINISTRATOR, DesignationScope.OPERATING_HEAD}:
            return True
        if actor.scope_level == DesignationScope.DIVISION_HEAD:
            return bool(actor.division_id and user.division_id == actor.division_id)
        if actor.scope_level == DesignationScope.DEPARTMENT_HEAD:
            return bool(actor.department_id and user.department_id == actor.department_id)
        return bool(
            (actor.team_id and user.team_id == actor.team_id)
            or (actor.department_id and user.department_id == actor.department_id)
            or actor.id == user.id
        )

    def _can_view_item(self, actor: User, item: WorkItem) -> bool:
        if self._can_view_team(actor, item.team):
            return True
        return self._can_view_user_scope(actor, item.creator) or self._can_view_user_scope(actor, item.assignee)

    def get_item_or_raise(self, work_item_id: int) -> WorkItem:
        item = self.work_item_repo.get_by_id(work_item_id)
        if not item:
            raise ValueError("Work item not found.")
        return item

    def get_accessible_work_item(self, actor: User, work_item_id: int) -> WorkItem:
        item = self.get_item_or_raise(work_item_id)
        if self._can_view_item(actor, item):
            return item
        raise ValueError("You do not have access to this work item.")

    def list_by_level(self, actor: User, *, level: WorkItemLevel, parent_id: int | None = None) -> list[WorkItem]:
        items = self.work_item_repo.list_by_level(level=level, parent_id=parent_id)
        return [item for item in items if self._can_view_item(actor, item)]

    def breadcrumb(self, item: WorkItem) -> list[WorkItem]:
        chain: list[WorkItem] = []
        cursor = item
        while cursor is not None:
            chain.append(cursor)
            cursor = cursor.parent
        return list(reversed(chain))

    def _validate_parent(self, level: WorkItemLevel, parent_id: int | None) -> WorkItem | None:
        expected_parent = _PARENT_LEVEL[level]
        if expected_parent is None:
            if parent_id is not None:
                raise ValueError(f"{level.title()} cannot have a parent.")
            return None
        if parent_id is None:
            raise ValueError(f"{level.title()} requires a parent.")
        parent = self.work_item_repo.get_by_id(parent_id)
        if not parent or parent.level != expected_parent:
            raise ValueError(f"{level.title()} must be created under a {expected_parent.title()}.")
        return parent

    def list_for_actor(self, actor: User) -> list[WorkItem]:
        return [item for item in self.work_item_repo.list_all() if self._can_view_item(actor, item)]

    def list_tasks_for_actor(self, actor: User) -> list[WorkItem]:
        return [item for item in self.list_for_actor(actor) if item.level == WorkItemLevel.TASK]

    def list_assigned_to_actor(self, actor: User) -> list[WorkItem]:
        return self.work_item_repo.list_for_assignee(actor.id)

    def list_created_by_actor(self, actor: User) -> list[WorkItem]:
        return [item for item in self.list_for_actor(actor) if item.created_by_id == actor.id]

    def can_edit_work_item(self, actor: User, item: WorkItem) -> bool:
        if actor.role == UserRole.ADMIN:
            return True
        if actor.role == UserRole.MANAGER and self._can_view_item(actor, item):
            return True
        if actor.role == UserRole.EMPLOYEE:
            return self._can_view_item(actor, item) and actor.id in {item.assigned_to_id, item.created_by_id}
        return False

    @staticmethod
    def can_create_level(actor: User, level: WorkItemLevel) -> bool:
        if actor.role == UserRole.MANAGER:
            return True
        if actor.role == UserRole.EMPLOYEE:
            return level != WorkItemLevel.OBJECTIVE
        return False

    def can_delete_work_item(self, actor: User, item: WorkItem) -> bool:
        return (
            actor.id == item.created_by_id
            and self.can_create_level(actor, item.level)
            and (actor.role == UserRole.ADMIN or self._can_view_item(actor, item))
        )

    def _subtree_owned_by(self, actor: User, item: WorkItem) -> bool:
        if not self.can_delete_work_item(actor, item):
            return False
        return all(self._subtree_owned_by(actor, child) for child in item.children)

    def can_delete_work_item_tree(self, actor: User, item: WorkItem) -> bool:
        return self._subtree_owned_by(actor, item)

    def create_work_item(self, actor: User, payload: WorkItemCreate) -> WorkItem:
        if actor.role == UserRole.ADMIN:
            raise ValueError("Admins cannot create delivery work items.")
        if actor.role == UserRole.EMPLOYEE and payload.level == WorkItemLevel.OBJECTIVE:
            raise ValueError("Employees can create milestones, activities, and tasks only.")
        if payload.level == WorkItemLevel.SUB_TASK:
            raise ValueError("Sub-tasks are no longer part of the active delivery workflow.")
        if actor.role not in {UserRole.MANAGER, UserRole.EMPLOYEE}:
            raise ValueError("You do not have permission to create work items.")
        parent = self._validate_parent(payload.level, payload.parent_id)
        if actor.role == UserRole.MANAGER and parent and not self._can_view_item(actor, parent):
            raise ValueError("Managers can create work only inside their visible scope.")
        if actor.role == UserRole.EMPLOYEE and parent and not self._can_view_item(actor, parent):
            raise ValueError("Employees can create work only inside their visible scope.")
        if payload.level == WorkItemLevel.OBJECTIVE and actor.role != UserRole.MANAGER:
            raise ValueError("Only managers can create projects.")
        assignee = actor
        item = WorkItem(
            level=payload.level,
            title=payload.title,
            description=payload.description,
            assigned_to_id=assignee.id if assignee else None,
            created_by_id=actor.id,
            team_id=(
                getattr(parent, "team_id", None)
                or actor.team_id
                or getattr(assignee, "team_id", None)
            ),
            priority=payload.priority,
            due_date=payload.due_date,
            parent_id=parent.id if parent else None,
        )
        self._sync_leaf_progress(item)
        self.work_item_repo.create(item)
        if parent:
            self._refresh_ancestor_progress(parent)
        self.audit_service.log_action(
            actor_user_id=actor.id,
            action=f"{item.level.value.lower()}_created",
            entity_type=self._display_name(item.level),
            entity_id=item.id,
            details={"parent_id": item.parent_id, "team_id": item.team_id},
        )
        return item

    def create_task(self, actor: User, payload: WorkItemCreate) -> WorkItem:
        if payload.level == WorkItemLevel.OBJECTIVE:
            raise ValueError("Task creation requires a milestone or activity parent.")
        return self.create_work_item(actor, payload)

    def update_work_item(self, actor: User, work_item_id: int, payload: WorkItemUpdate) -> WorkItem:
        item = self.get_accessible_work_item(actor, work_item_id)
        if not self.can_edit_work_item(actor, item):
            raise ValueError("You do not have permission to edit this work item.")
        previous_status = item.status
        item.title = payload.title
        item.description = payload.description
        item.priority = payload.priority
        item.due_date = payload.due_date
        if item.children:
            was_blocked = item.status == WorkItemStatus.BLOCKED
            self._recalculate_tree_progress(item)
            if payload.status == WorkItemStatus.BLOCKED:
                item.status = WorkItemStatus.BLOCKED
                item.completed_at = None
            elif was_blocked:
                item.status = payload.status
                item.completed_at = datetime.now(UTC) if payload.status == WorkItemStatus.COMPLETED else None
        else:
            item.status = payload.status
            self._sync_leaf_progress(item)
        self._refresh_ancestor_progress(item.parent)
        self.audit_service.log_action(
            actor_user_id=actor.id,
            action=f"{item.level.value.lower()}_updated",
            entity_type=self._display_name(item.level),
            entity_id=item.id,
            details={"status": item.status.value, "assignee_id": item.assigned_to_id},
        )
        if item.status != previous_status:
            action = {
                WorkItemStatus.COMPLETED: "completed",
                WorkItemStatus.PENDING: "reopened",
                WorkItemStatus.IN_PROGRESS: "started",
                WorkItemStatus.BLOCKED: "blocked",
                WorkItemStatus.CLOSED: "closed",
            }[item.status]
            self._notify_participants(item, actor, action)
        return item

    def update_task(self, actor: User, work_item_id: int, payload: WorkItemUpdate) -> WorkItem:
        return self.update_work_item(actor, work_item_id, payload)

    def close_work_item(self, actor: User, work_item_id: int) -> WorkItem:
        item = self.get_accessible_work_item(actor, work_item_id)
        if actor.role == UserRole.EMPLOYEE:
            raise ValueError("Employees cannot close work items.")
        self._recalculate_tree_progress(item)
        if item.status != WorkItemStatus.COMPLETED:
            raise ValueError("Only completed work items can be closed.")
        item.status = WorkItemStatus.CLOSED
        item.closed_at = datetime.now(UTC)
        self.audit_service.log_action(
            actor_user_id=actor.id,
            action=f"{item.level.value.lower()}_closed",
            entity_type=self._display_name(item.level),
            entity_id=item.id,
        )
        self._notify_participants(item, actor, "closed")
        self._refresh_ancestor_progress(item.parent)
        return item

    def close_task(self, actor: User, work_item_id: int) -> WorkItem:
        return self.close_work_item(actor, work_item_id)

    def delete_work_item(self, actor: User, work_item_id: int) -> tuple[WorkItemLevel, int | None, str]:
        item = self.get_accessible_work_item(actor, work_item_id)
        if not self.can_delete_work_item(actor, item):
            raise ValueError("You can delete only work items that you created.")
        if not self._subtree_owned_by(actor, item):
            raise ValueError("This item contains work created by another team member and cannot be deleted.")

        level = item.level
        parent_id = item.parent_id
        title = item.title
        parent = item.parent
        self.audit_service.log_action(
            actor_user_id=actor.id,
            action=f"{item.level.value.lower()}_deleted",
            entity_type=self._display_name(item.level),
            entity_id=item.id,
            details={"title": title, "parent_id": parent_id, "team_id": item.team_id},
        )
        self.work_item_repo.delete(item)
        if parent:
            self._refresh_ancestor_progress(parent)
        return level, parent_id, title

    def toggle_child_completion(self, actor: User, work_item_id: int, child_id: int) -> WorkItem:
        item = self.get_accessible_work_item(actor, work_item_id)
        child = self.get_accessible_work_item(actor, child_id)
        if not item or not child or child.parent_id != item.id:
            raise ValueError("Child work item not found.")
        if not self.can_edit_work_item(actor, child):
            raise ValueError("You do not have permission to update this work item.")
        child.status = WorkItemStatus.COMPLETED if child.status != WorkItemStatus.COMPLETED else WorkItemStatus.PENDING
        child.completed_at = datetime.now(UTC) if child.status == WorkItemStatus.COMPLETED else None
        self._sync_leaf_progress(child)
        self._recalculate_tree_progress(item)
        self._refresh_ancestor_progress(item.parent)
        self.audit_service.log_action(
            actor_user_id=actor.id,
            action=f"{child.level.value.lower()}_status_changed",
            entity_type=self._display_name(child.level),
            entity_id=child.id,
            details={"status": child.status.value},
        )
        action = "completed" if child.status == WorkItemStatus.COMPLETED else "reopened"
        self._notify_participants(child, actor, action)
        return item

    def toggle_subtask(self, actor: User, work_item_id: int, child_id: int) -> WorkItem:
        item = self.work_item_repo.get_by_id(work_item_id)
        if item:
            return self.toggle_child_completion(actor, work_item_id, child_id)

        legacy_task = self.db.get(Task, work_item_id)
        legacy_subtask = self.db.get(Subtask, child_id)
        if not legacy_task or not legacy_subtask or legacy_subtask.task_id != legacy_task.id:
            raise ValueError("Child work item not found.")
        if actor.role == UserRole.EMPLOYEE and legacy_task.assigned_to_id != actor.id:
            raise ValueError("Employees can update only their own task subtasks.")
        if actor.role == UserRole.EMPLOYEE and legacy_subtask.is_completed and legacy_task.due_date and date.today() > legacy_task.due_date:
            raise ValueError("Completed subtasks cannot be unchecked after the task due date has passed.")
        legacy_subtask.is_completed = not legacy_subtask.is_completed
        legacy_subtask.completed_at = datetime.now(UTC) if legacy_subtask.is_completed else None
        self.db.flush()
        subtasks = self.db.query(Subtask).filter(Subtask.task_id == legacy_task.id).all()
        completed_count = sum(1 for subtask in subtasks if subtask.is_completed)
        total_count = len(subtasks)
        legacy_task.progress_percent = int((completed_count / total_count) * 100) if total_count else 0
        if completed_count == 0:
            legacy_task.status = TaskStatus.PENDING
            legacy_task.completed_at = None
        elif completed_count == total_count:
            legacy_task.status = TaskStatus.COMPLETED
            legacy_task.completed_at = datetime.now(UTC)
        else:
            legacy_task.status = TaskStatus.IN_PROGRESS
            legacy_task.completed_at = None
        self.db.flush()
        return legacy_task

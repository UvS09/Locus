from datetime import date

from sqlalchemy.orm import Session

from app.models.role import Role
from app.repositories.audit_repository import AuditRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.team_repository import TeamRepository
from app.repositories.user_repository import UserRepository
from app.utils.enums import TaskStatus
from app.utils.work_item_levels import WorkItemLevel, WorkItemStatus


class ReportService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.team_repo = TeamRepository(db)
        self.task_repo = TaskRepository(db)
        self.audit_repo = AuditRepository(db)

    @staticmethod
    def _avg_progress(items: list) -> int:
        if not items:
            return 0
        return int(sum(item.progress_percent for item in items) / len(items))

    @staticmethod
    def _label_for_level(level: WorkItemLevel) -> str:
        return {
            WorkItemLevel.OBJECTIVE: "Project",
            WorkItemLevel.WORKSTREAM: "Milestone",
            WorkItemLevel.ACTIVITY: "Activity",
            WorkItemLevel.TASK: "Task",
            WorkItemLevel.SUB_TASK: "Sub-task",
        }[level]

    def _annotate_recent_updates(self, items: list) -> list:
        for item in items:
            chain = []
            cursor = item
            while cursor is not None:
                chain.append(cursor.title)
                cursor = cursor.parent
            item.category_label = self._label_for_level(item.level)
            item.project_path = " / ".join(reversed(chain))
        return items

    def _team_snapshots(self, team_id: int, team_items: list) -> dict:
        delivery_levels = {WorkItemLevel.WORKSTREAM, WorkItemLevel.ACTIVITY, WorkItemLevel.TASK}
        active_statuses = {WorkItemStatus.PENDING, WorkItemStatus.IN_PROGRESS, WorkItemStatus.BLOCKED}
        return {
            "active_members": len(self.user_repo.list_team_members(team_id)),
            "active_projects": sum(
                1 for item in team_items
                if item.level == WorkItemLevel.OBJECTIVE and item.status in active_statuses
            ),
            "open_work": sum(
                1 for item in team_items
                if item.level in delivery_levels and item.status in active_statuses
            ),
            "completed_today": sum(
                1 for item in team_items
                if item.level in delivery_levels
                and item.completed_at
                and item.completed_at.date() == date.today()
            ),
        }

    def admin_dashboard(self) -> dict:
        all_items = self.task_repo.list_all()
        objectives = [item for item in all_items if item.level == WorkItemLevel.OBJECTIVE]
        active_items = [item for item in all_items if item.status not in {WorkItemStatus.COMPLETED, WorkItemStatus.CLOSED}]
        custom_roles = self.db.query(Role).order_by(Role.name).all()
        users = self.user_repo.list_all()
        return {
            "total_users": self.user_repo.count(),
            "active_users": self.user_repo.count(active_only=True),
            "total_roles": len(custom_roles) + 3,
            "custom_roles": custom_roles,
            "role_distribution": [
                {
                    "name": role.name,
                    "access_level": role.access_level.value,
                    "count": sum(1 for user in users if user.custom_role_id == role.id),
                }
                for role in custom_roles
            ],
            "total_teams": len(self.team_repo.list_all()),
            "total_tasks": len(all_items),
            "active_tasks": len(active_items),
            "closed_tasks": self.task_repo.count_by_status(status=WorkItemStatus.CLOSED),
            "total_objectives": self.task_repo.count_by_status(level=WorkItemLevel.OBJECTIVE),
            "total_workstreams": self.task_repo.count_by_status(level=WorkItemLevel.WORKSTREAM),
            "total_activities": self.task_repo.count_by_status(level=WorkItemLevel.ACTIVITY),
            "total_task_items": self.task_repo.count_by_status(level=WorkItemLevel.TASK),
            "total_subtasks": self.task_repo.count_by_status(level=WorkItemLevel.SUB_TASK),
            "portfolio_progress": self._avg_progress(objectives),
            "recent_work_items": all_items[:10],
            "recent_audit_logs": self.audit_repo.list_recent(limit=10),
        }

    def manager_dashboard(self, team_id: int) -> dict:
        team_tasks = self.task_repo.list_for_team(team_id)
        objectives = [item for item in team_tasks if item.level == WorkItemLevel.OBJECTIVE]
        overdue_items = [
            task for task in team_tasks
            if task.due_date
            and task.due_date < date.today()
            and task.status not in {WorkItemStatus.COMPLETED, WorkItemStatus.CLOSED}
        ]
        blocked_items = [item for item in team_tasks if item.status == WorkItemStatus.BLOCKED]
        return {
            "blocked_count": self.task_repo.count_by_status(team_id=team_id, status=WorkItemStatus.BLOCKED),
            "overdue_count": len(overdue_items),
            "overdue_items": overdue_items[:8],
            "blocked_items": blocked_items[:8],
            "recent_updates": self._annotate_recent_updates(self.task_repo.list_recent_updates_for_team(team_id)),
            "objective_count": self.task_repo.count_by_status(team_id=team_id, level=WorkItemLevel.OBJECTIVE),
            "objective_progress": self._avg_progress(objectives),
            "snapshots": self._team_snapshots(team_id, team_tasks),
        }

    def manager_employee_analytics(self, team_id: int) -> dict:
        team_items = self.task_repo.list_for_team(team_id)
        employees = self.user_repo.list_team_members(team_id)
        delivery_levels = {WorkItemLevel.WORKSTREAM, WorkItemLevel.ACTIVITY, WorkItemLevel.TASK}
        report_items = [item for item in team_items if item.level in delivery_levels]
        active_statuses = {WorkItemStatus.PENDING, WorkItemStatus.IN_PROGRESS, WorkItemStatus.BLOCKED}

        employee_rows = []
        for employee in employees:
            assigned = [item for item in report_items if item.assigned_to_id == employee.id]
            overdue = [
                item for item in assigned
                if item.due_date
                and item.due_date < date.today()
                and item.status not in {WorkItemStatus.COMPLETED, WorkItemStatus.CLOSED}
            ]
            completed = [item for item in assigned if item.status in {WorkItemStatus.COMPLETED, WorkItemStatus.CLOSED}]
            employee_rows.append(
                {
                    "employee": employee,
                    "assigned": len(assigned),
                    "open": sum(1 for item in assigned if item.status in active_statuses),
                    "in_progress": sum(1 for item in assigned if item.status == WorkItemStatus.IN_PROGRESS),
                    "blocked": sum(1 for item in assigned if item.status == WorkItemStatus.BLOCKED),
                    "overdue": len(overdue),
                    "completed": len(completed),
                    "completion_rate": int((len(completed) / len(assigned)) * 100) if assigned else 0,
                    "avg_progress": self._avg_progress(assigned),
                }
            )

        status_counts = {"To Do": 0, "In Progress": 0, "Blocked": 0, "Completed": 0, "Overdue": 0}
        for item in report_items:
            is_overdue = (
                item.due_date
                and item.due_date < date.today()
                and item.status not in {WorkItemStatus.COMPLETED, WorkItemStatus.CLOSED}
            )
            if is_overdue:
                status_counts["Overdue"] += 1
            elif item.status == WorkItemStatus.PENDING:
                status_counts["To Do"] += 1
            elif item.status == WorkItemStatus.IN_PROGRESS:
                status_counts["In Progress"] += 1
            elif item.status == WorkItemStatus.BLOCKED:
                status_counts["Blocked"] += 1
            elif item.status in {WorkItemStatus.COMPLETED, WorkItemStatus.CLOSED}:
                status_counts["Completed"] += 1
        top_blocked = sorted(employee_rows, key=lambda row: row["blocked"], reverse=True)[:5]
        top_completed = sorted(employee_rows, key=lambda row: row["completed"], reverse=True)[:5]
        return {
            "employees": employee_rows,
            "status_counts": status_counts,
            "status_total": len(report_items),
            "status_chart": self._analytics_status_chart(status_counts) if report_items else "#e5e7eb 0% 100%",
            "top_blocked": top_blocked,
            "top_completed": top_completed,
            "totals": {
                "assigned": len(report_items),
                "open": sum(row["open"] for row in employee_rows),
                "blocked": sum(row["blocked"] for row in employee_rows),
                "completed": sum(row["completed"] for row in employee_rows),
                "overdue": sum(row["overdue"] for row in employee_rows),
            },
        }

    @staticmethod
    def _analytics_status_chart(status_counts: dict[str, int]) -> str:
        status_total = sum(status_counts.values()) or 1
        chart_colors = {
            "To Do": "#fee2e2",
            "In Progress": "#f87171",
            "Blocked": "#111111",
            "Completed": "#991b1b",
            "Overdue": "#d72638",
        }
        chart_segments = []
        cursor = 0
        for label, count in status_counts.items():
            next_cursor = cursor + (count / status_total) * 100
            chart_segments.append(f"{chart_colors[label]} {cursor:.2f}% {next_cursor:.2f}%")
            cursor = next_cursor
        return ", ".join(chart_segments)

    def employee_analytics(self, user_id: int) -> dict:
        user = self.user_repo.get_by_id(user_id)
        assigned_items = self.task_repo.list_for_assignee(user_id)
        delivery_items = [
            item for item in assigned_items
            if item.level in {WorkItemLevel.WORKSTREAM, WorkItemLevel.ACTIVITY, WorkItemLevel.TASK}
        ]
        overdue_items = [
            item for item in delivery_items
            if item.due_date
            and item.due_date < date.today()
            and item.status not in {WorkItemStatus.COMPLETED, WorkItemStatus.CLOSED}
        ]
        completed_items = [item for item in delivery_items if item.status in {WorkItemStatus.COMPLETED, WorkItemStatus.CLOSED}]
        status_counts = {"To Do": 0, "In Progress": 0, "Blocked": 0, "Completed": 0, "Overdue": 0}
        for item in delivery_items:
            is_overdue = (
                item.due_date
                and item.due_date < date.today()
                and item.status not in {WorkItemStatus.COMPLETED, WorkItemStatus.CLOSED}
            )
            if is_overdue:
                status_counts["Overdue"] += 1
            elif item.status == WorkItemStatus.PENDING:
                status_counts["To Do"] += 1
            elif item.status == WorkItemStatus.IN_PROGRESS:
                status_counts["In Progress"] += 1
            elif item.status == WorkItemStatus.BLOCKED:
                status_counts["Blocked"] += 1
            elif item.status in {WorkItemStatus.COMPLETED, WorkItemStatus.CLOSED}:
                status_counts["Completed"] += 1
        return {
            "employee": user,
            "work_items": delivery_items[:10],
            "status_counts": status_counts,
            "status_total": len(delivery_items),
            "status_chart": self._analytics_status_chart(status_counts) if delivery_items else "#e5e7eb 0% 100%",
            "totals": {
                "assigned": len(delivery_items),
                "open": sum(1 for item in delivery_items if item.status in {WorkItemStatus.PENDING, WorkItemStatus.IN_PROGRESS, WorkItemStatus.BLOCKED}),
                "blocked": sum(1 for item in delivery_items if item.status == WorkItemStatus.BLOCKED),
                "overdue": len(overdue_items),
                "completed": len(completed_items),
                "completion_rate": int((len(completed_items) / len(delivery_items)) * 100) if delivery_items else 0,
                "avg_progress": self._avg_progress(delivery_items),
            },
        }

    def employee_dashboard(self, user_id: int) -> dict:
        user = self.user_repo.get_by_id(user_id)
        assigned_items = self.task_repo.list_for_assignee(user_id)
        created_items = [item for item in self.task_repo.list_all() if item.created_by_id == user_id]
        team_items = self.task_repo.list_for_team(user.team_id) if user and user.team_id else []
        return {
            "assigned_tasks": assigned_items,
            "created_items": created_items[:8],
            "pending_count": self.task_repo.count_by_status(assigned_to_id=user_id, status=WorkItemStatus.PENDING),
            "in_progress_count": self.task_repo.count_by_status(assigned_to_id=user_id, status=WorkItemStatus.IN_PROGRESS),
            "blocked_count": self.task_repo.count_by_status(assigned_to_id=user_id, status=WorkItemStatus.BLOCKED),
            "completed_count": self.task_repo.count_by_status(assigned_to_id=user_id, status=WorkItemStatus.COMPLETED),
            "closed_count": self.task_repo.count_by_status(assigned_to_id=user_id, status=WorkItemStatus.CLOSED),
            "due_soon": self.task_repo.list_recent_for_assignee(user_id, limit=6),
            "snapshots": self._team_snapshots(user.team_id, team_items) if user and user.team_id else {
                "active_members": 0,
                "active_projects": 0,
                "open_work": 0,
                "completed_today": 0,
            },
        }

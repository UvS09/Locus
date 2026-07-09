from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.user import User
from app.models.role import Role
from app.models.team import Team
from app.models.department import Department
from app.models.division import Division
from app.repositories.audit_repository import AuditRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.team_repository import TeamRepository
from app.repositories.user_repository import UserRepository
from app.services.user_service import UserService
from app.services.work_item_service import WorkItemService
from app.utils.enums import DesignationScope, TaskStatus, UserRole
from app.utils.work_item_levels import WorkItemLevel, WorkItemStatus


class ReportService:
    PREFERRED_DIVISION_ORDER = [
        "AI and Data Science",
        "Application Development",
        "Application Run",
        "Security and Compliance",
        "Infrastructure",
        "1F",
        "2F",
        "3F",
        "4F",
    ]
    DIVISION_NAME_ALIASES = {
        "AI and Data Science": ["AI and Data Science"],
        "Application Development": ["Application Development", "Application Developement"],
        "Application Run": ["Application Run"],
        "Security and Compliance": ["Security and Compliance"],
        "Infrastructure": ["Infrastructure"],
        "1F": ["1F"],
        "2F": ["2F"],
        "3F": ["3F"],
        "4F": ["4F"],
    }
    ACTIVE_STATUSES = {WorkItemStatus.PENDING, WorkItemStatus.IN_PROGRESS, WorkItemStatus.BLOCKED}
    CLOSED_STATUSES = {WorkItemStatus.COMPLETED, WorkItemStatus.CLOSED}
    DELIVERY_LEVELS = {WorkItemLevel.WORKSTREAM, WorkItemLevel.ACTIVITY, WorkItemLevel.TASK}
    ROADMAP_LEVELS = (
        (WorkItemLevel.OBJECTIVE, "Projects"),
        (WorkItemLevel.WORKSTREAM, "Milestones"),
        (WorkItemLevel.ACTIVITY, "Activities"),
        (WorkItemLevel.TASK, "Tasks"),
    )

    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.team_repo = TeamRepository(db)
        self.task_repo = TaskRepository(db)
        self.audit_repo = AuditRepository(db)
        self.user_service = UserService(db)
        self.work_item_service = WorkItemService(db)

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
        return {
            "active_members": len(self.user_repo.list_team_members(team_id)),
            "active_projects": sum(
                1 for item in team_items
                if item.level == WorkItemLevel.OBJECTIVE and item.status in self.ACTIVE_STATUSES
            ),
            "open_work": sum(
                1 for item in team_items
                if item.level in self.DELIVERY_LEVELS and item.status in self.ACTIVE_STATUSES
            ),
            "completed_today": sum(
                1 for item in team_items
                if item.level in self.DELIVERY_LEVELS
                and item.completed_at
                and item.completed_at.date() == date.today()
            ),
        }

    @staticmethod
    def _completion_rate(items: list) -> int:
        if not items:
            return 0
        completed = sum(1 for item in items if item.status in ReportService.CLOSED_STATUSES)
        return int((completed / len(items)) * 100)

    @staticmethod
    def _workload_percent(open_work: int, member_count: int) -> int:
        if member_count <= 0:
            return 0
        return min(100, int((open_work / max(member_count, 1)) * 20))

    def _upcoming_deadlines(self, items: list, limit: int = 8) -> list:
        eligible = [
            item for item in items
            if item.due_date
            and item.due_date >= date.today()
            and item.status not in self.CLOSED_STATUSES
        ]
        return self._annotate_recent_updates(sorted(eligible, key=lambda item: (item.due_date, item.updated_at))[:limit])

    def _roadmap_metrics(self, items: list) -> list[dict]:
        metrics = []
        for level, label in self.ROADMAP_LEVELS:
            level_items = [item for item in items if item.level == level]
            metrics.append(
                {
                    "label": label,
                    "count": len(level_items),
                    "completion": self._completion_rate(level_items),
                    "active": sum(1 for item in level_items if item.status in self.ACTIVE_STATUSES),
                }
            )
        return metrics

    def _scope_row(self, *, name: str, href: str, users: list[User], items: list, entity_id: int | None = None) -> dict:
        active_members = [user for user in users if user.is_active]
        leaders = sorted(
            [user for user in users if user.scope_level in {DesignationScope.DIVISION_HEAD, DesignationScope.DEPARTMENT_HEAD}],
            key=lambda user: (-(user.designation.rank if user.designation else 0), user.full_name.lower()),
        )
        delivery_items = [item for item in items if item.level in self.DELIVERY_LEVELS]
        roadmap = self._roadmap_metrics(items)
        open_work = sum(1 for item in delivery_items if item.status in self.ACTIVE_STATUSES)
        blocked = sum(1 for item in delivery_items if item.status == WorkItemStatus.BLOCKED)
        overdue = sum(
            1 for item in delivery_items
            if item.due_date and item.due_date < date.today() and item.status not in self.CLOSED_STATUSES
        )
        return {
            "entity_id": entity_id,
            "name": name,
            "href": href,
            "members": len(active_members),
            "projects": len([item for item in items if item.level == WorkItemLevel.OBJECTIVE]),
            "milestones": len([item for item in items if item.level == WorkItemLevel.WORKSTREAM]),
            "activities": len([item for item in items if item.level == WorkItemLevel.ACTIVITY]),
            "tasks": len([item for item in items if item.level == WorkItemLevel.TASK]),
            "open": open_work,
            "completed": len([item for item in delivery_items if item.status in self.CLOSED_STATUSES]),
            "completed_today": sum(1 for item in delivery_items if item.completed_at and item.completed_at.date() == date.today()),
            "completion": self._completion_rate(delivery_items),
            "task_completion": self._completion_rate([item for item in items if item.level == WorkItemLevel.TASK]),
            "workload_percent": self._workload_percent(open_work, len(active_members)),
            "blocked": blocked,
            "overdue": overdue,
            "leaders": leaders[:3],
            "roadmap": roadmap,
        }

    def _ordered_division_rows(self, visible_users: list[User], visible_items: list) -> list[dict]:
        divisions = self.db.query(Division).order_by(Division.name).all()
        division_by_name = {division.name.casefold(): division for division in divisions}
        rows = []
        seen_names: set[str] = set()

        for division_name in self.PREFERRED_DIVISION_ORDER:
            seen_names.add(division_name.casefold())
            division = None
            for alias in self.DIVISION_NAME_ALIASES.get(division_name, [division_name]):
                division = division_by_name.get(alias.casefold())
                if division:
                    seen_names.add(alias.casefold())
                    break
            division_users = [user for user in visible_users if division and user.division_id == division.id]
            division_items = [item for item in visible_items if division and self._item_division_id(item) == division.id]
            rows.append(
                self._scope_row(
                    name=division_name,
                    href=f"/manager/team-members?division_id={division.id}" if division else "/manager/team-members",
                    users=division_users,
                    items=division_items,
                    entity_id=division.id if division else None,
                )
            )

        for division in divisions:
            if division.name.casefold() in seen_names:
                continue
            division_users = [user for user in visible_users if user.division_id == division.id]
            division_items = [item for item in visible_items if self._item_division_id(item) == division.id]
            if not division_users and not division_items:
                continue
            rows.append(
                self._scope_row(
                    name=division.name,
                    href=f"/manager/team-members?division_id={division.id}",
                    users=division_users,
                    items=division_items,
                    entity_id=division.id,
                )
            )
        return rows

    @staticmethod
    def _item_division_id(item) -> int | None:
        if item.team and item.team.department:
            return item.team.department.division_id
        if item.creator and item.creator.division_id:
            return item.creator.division_id
        if item.assignee and item.assignee.division_id:
            return item.assignee.division_id
        return None

    @staticmethod
    def _item_department_id(item) -> int | None:
        if item.team:
            return item.team.department_id
        if item.creator and item.creator.department_id:
            return item.creator.department_id
        if item.assignee and item.assignee.department_id:
            return item.assignee.department_id
        return None

    def admin_dashboard(self) -> dict:
        all_items = self.task_repo.list_all()
        objectives = [item for item in all_items if item.level == WorkItemLevel.OBJECTIVE]
        workstreams = [item for item in all_items if item.level == WorkItemLevel.WORKSTREAM]
        activities = [item for item in all_items if item.level == WorkItemLevel.ACTIVITY]
        task_items = [item for item in all_items if item.level == WorkItemLevel.TASK]
        active_items = [item for item in all_items if item.status not in {WorkItemStatus.COMPLETED, WorkItemStatus.CLOSED}]
        overdue_tasks = [
            item for item in task_items
            if item.due_date and item.due_date < date.today() and item.status not in {WorkItemStatus.COMPLETED, WorkItemStatus.CLOSED}
        ]
        custom_roles = self.db.query(Role).order_by(Role.name).all()
        users = self.user_repo.list_all()
        teams = self.team_repo.list_all()
        active_statuses = {WorkItemStatus.PENDING, WorkItemStatus.IN_PROGRESS, WorkItemStatus.BLOCKED}
        team_workload = []
        for team in teams:
            team_items = [item for item in all_items if item.team_id == team.id]
            team_workload.append(
                {
                    "team": team,
                    "active_members": len([user for user in users if user.team_id == team.id and user.is_active]),
                    "active_objectives": sum(
                        1 for item in team_items if item.level == WorkItemLevel.OBJECTIVE and item.status in active_statuses
                    ),
                    "active_tasks": sum(
                        1 for item in team_items if item.level == WorkItemLevel.TASK and item.status in active_statuses
                    ),
                    "overdue_tasks": sum(
                        1 for item in team_items
                        if item.level == WorkItemLevel.TASK
                        and item.due_date
                        and item.due_date < date.today()
                        and item.status not in {WorkItemStatus.COMPLETED, WorkItemStatus.CLOSED}
                    ),
                    "completion": self._completion_rate(
                        [item for item in team_items if item.level in {WorkItemLevel.WORKSTREAM, WorkItemLevel.ACTIVITY, WorkItemLevel.TASK}]
                    ),
                }
            )
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
            "overdue_tasks": len(overdue_tasks),
            "closed_tasks": self.task_repo.count_by_status(status=WorkItemStatus.CLOSED),
            "total_objectives": self.task_repo.count_by_status(level=WorkItemLevel.OBJECTIVE),
            "total_workstreams": self.task_repo.count_by_status(level=WorkItemLevel.WORKSTREAM),
            "total_activities": self.task_repo.count_by_status(level=WorkItemLevel.ACTIVITY),
            "total_task_items": self.task_repo.count_by_status(level=WorkItemLevel.TASK),
            "total_subtasks": self.task_repo.count_by_status(level=WorkItemLevel.SUB_TASK),
            "portfolio_progress": self._avg_progress(objectives),
            "objective_completion": self._completion_rate(objectives),
            "workstream_completion": self._completion_rate(workstreams),
            "activity_completion": self._completion_rate(activities),
            "active_objectives": sum(1 for item in objectives if item.status in active_statuses),
            "recent_work_items": all_items[:10],
            "recent_audit_logs": self.audit_repo.list_recent(limit=10),
            "recent_objectives": objectives[:5],
            "recent_completed_tasks": sorted(
                [item for item in task_items if item.completed_at],
                key=lambda item: item.completed_at,
                reverse=True,
            )[:5],
            "recent_updated_workstreams": sorted(workstreams, key=lambda item: item.updated_at, reverse=True)[:5],
            "team_workload": sorted(team_workload, key=lambda row: row["overdue_tasks"], reverse=True),
            "recent_notifications": self.db.query(Notification).order_by(Notification.created_at.desc()).limit(6).all(),
        }

    def admin_workspace(self) -> dict:
        all_items = self.task_repo.list_all()
        return {
            "objectives": [item for item in all_items if item.level == WorkItemLevel.OBJECTIVE],
            "tasks": [item for item in all_items if item.level == WorkItemLevel.TASK],
            "teams": self.team_repo.list_all(),
        }

    def admin_reports(self) -> dict:
        all_items = self.task_repo.list_all()
        teams = self.team_repo.list_all()
        all_users = self.user_repo.list_all()
        users = [user for user in all_users if user.role != UserRole.ADMIN]
        objectives = [item for item in all_items if item.level == WorkItemLevel.OBJECTIVE]
        workstreams = [item for item in all_items if item.level == WorkItemLevel.WORKSTREAM]
        activities = [item for item in all_items if item.level == WorkItemLevel.ACTIVITY]
        tasks = [item for item in all_items if item.level == WorkItemLevel.TASK]
        overdue_items = [
            item for item in all_items
            if item.due_date and item.due_date < date.today() and item.status not in {WorkItemStatus.COMPLETED, WorkItemStatus.CLOSED}
        ]

        employee_rows = []
        for user in [item for item in users if item.role == UserRole.EMPLOYEE]:
            assigned_items = [item for item in all_items if item.assigned_to_id == user.id and item.level in {WorkItemLevel.ACTIVITY, WorkItemLevel.TASK}]
            completed_count = sum(1 for item in assigned_items if item.status in {WorkItemStatus.COMPLETED, WorkItemStatus.CLOSED})
            employee_rows.append(
                {
                    "user": user,
                    "assigned": len(assigned_items),
                    "completed": completed_count,
                    "overdue": sum(
                        1 for item in assigned_items
                        if item.due_date and item.due_date < date.today() and item.status not in {WorkItemStatus.COMPLETED, WorkItemStatus.CLOSED}
                    ),
                    "avg_progress": self._avg_progress(assigned_items),
                    "completion_rate": int((completed_count / len(assigned_items)) * 100) if assigned_items else 0,
                }
            )

        manager_rows = []
        for user in [item for item in users if item.role == UserRole.MANAGER]:
            team_items = [item for item in all_items if item.team_id == user.team_id]
            manager_rows.append(
                {
                    "user": user,
                    "team_name": next((team.name for team in teams if team.id == user.team_id), "Unassigned"),
                    "open_work": sum(
                        1 for item in team_items
                        if item.level in {WorkItemLevel.WORKSTREAM, WorkItemLevel.ACTIVITY, WorkItemLevel.TASK}
                        and item.status in {WorkItemStatus.PENDING, WorkItemStatus.IN_PROGRESS, WorkItemStatus.BLOCKED}
                    ),
                    "completion_rate": self._completion_rate(
                        [item for item in team_items if item.level in {WorkItemLevel.WORKSTREAM, WorkItemLevel.ACTIVITY, WorkItemLevel.TASK}]
                    ),
                    "overdue": sum(
                        1 for item in team_items
                        if item.due_date and item.due_date < date.today() and item.status not in {WorkItemStatus.COMPLETED, WorkItemStatus.CLOSED}
                    ),
                }
            )

        team_rows = []
        for team in teams:
            team_items = [item for item in all_items if item.team_id == team.id]
            team_rows.append(
                {
                    "team": team,
                    "objective_completion": self._completion_rate(
                        [item for item in team_items if item.level == WorkItemLevel.OBJECTIVE]
                    ),
                    "task_completion": self._completion_rate(
                        [item for item in team_items if item.level == WorkItemLevel.TASK]
                    ),
                    "overdue": sum(
                        1 for item in team_items
                        if item.due_date and item.due_date < date.today() and item.status not in {WorkItemStatus.COMPLETED, WorkItemStatus.CLOSED}
                    ),
                    "active_members": len([user for user in users if user.team_id == team.id and user.is_active]),
                }
            )

        trends = []
        for days_ago in range(6, -1, -1):
            trend_date = date.today() - timedelta(days=days_ago)
            completed_that_day = [
                item for item in all_items
                if item.completed_at and item.completed_at.date() == trend_date
            ]
            trends.append({"date": trend_date, "completed": len(completed_that_day)})

        return {
            "user_summary": {
                "total_users": len(all_users),
                "active_users": len([user for user in all_users if user.is_active]),
                "administrators": len([user for user in all_users if user.role == UserRole.ADMIN]),
                "managers": len([user for user in all_users if user.role == UserRole.MANAGER]),
                "employees": len([user for user in all_users if user.role == UserRole.EMPLOYEE]),
                "operating_heads": len([user for user in all_users if user.scope_level.name == "OPERATING_HEAD"]),
            },
            "summary": {
                "objective_completion": self._completion_rate(objectives),
                "workstream_completion": self._completion_rate(workstreams),
                "activity_completion": self._completion_rate(activities),
                "task_completion": self._completion_rate(tasks),
                "overdue_work": len(overdue_items),
                "portfolio_progress": self._avg_progress(objectives),
            },
            "employee_productivity": sorted(employee_rows, key=lambda row: (row["completion_rate"], row["completed"]), reverse=True),
            "manager_productivity": sorted(manager_rows, key=lambda row: row["completion_rate"], reverse=True),
            "team_performance": sorted(team_rows, key=lambda row: row["task_completion"], reverse=True),
            "overdue_items": sorted(overdue_items, key=lambda item: item.due_date or date.today())[:12],
            "trends": trends,
        }

    def admin_audit_logs(self) -> dict:
        logs = self.audit_repo.list_recent(limit=200)
        actors = []
        seen_actor_ids = set()
        for log in logs:
            if log.actor and log.actor.id not in seen_actor_ids:
                actors.append(log.actor)
                seen_actor_ids.add(log.actor.id)
        actions = sorted({log.action for log in logs})
        entities = sorted({log.entity_type for log in logs})
        return {"logs": logs, "actors": actors, "actions": actions, "entities": entities}

    def manager_dashboard(self, actor: User) -> dict:
        visible_items = self.work_item_service.list_for_actor(actor)
        visible_users = [user for user in self.user_service.list_visible_users(actor) if user.role != UserRole.ADMIN]
        objectives = [item for item in visible_items if item.level == WorkItemLevel.OBJECTIVE]
        overdue_items = [
            task for task in visible_items
            if task.due_date
            and task.due_date < date.today()
            and task.status not in self.CLOSED_STATUSES
        ]
        blocked_items = [item for item in visible_items if item.status == WorkItemStatus.BLOCKED]
        delivery_items = [item for item in visible_items if item.level in self.DELIVERY_LEVELS]
        active_users = [user for user in visible_users if user.is_active]
        featured_members = sorted(
            active_users,
            key=lambda user: (
                -(user.designation.rank if user.designation else 0),
                user.full_name.lower(),
            ),
        )[:8]

        focus_label = "Organization"
        focus_rows: list[dict] = []
        if actor.scope_level == DesignationScope.OPERATING_HEAD:
            focus_label = "Divisions"
            focus_rows = self._ordered_division_rows(visible_users, visible_items)
        elif actor.scope_level == DesignationScope.DIVISION_HEAD:
            focus_label = "Departments"
            departments = self.db.query(Department).filter(Department.division_id == actor.division_id).order_by(Department.name).all()
            for department in departments:
                department_users = [user for user in visible_users if user.department_id == department.id]
                department_items = [item for item in visible_items if self._item_department_id(item) == department.id]
                focus_rows.append(
                    self._scope_row(
                        name=department.name,
                        href=f"/manager/team-members?department_id={department.id}",
                        users=department_users,
                        items=department_items,
                        entity_id=department.id,
                    )
                )
        else:
            focus_label = "Department"
            teams = self.db.query(Team).filter(Team.department_id == actor.department_id).order_by(Team.name).all() if actor.department_id else []
            for team in teams:
                team_users = [user for user in visible_users if user.team_id == team.id]
                team_items = [item for item in visible_items if item.team_id == team.id]
                focus_rows.append(
                    self._scope_row(
                        name=team.name,
                        href="/manager/team-members",
                        users=team_users,
                        items=team_items,
                        entity_id=team.id,
                    )
                )
        overall_completion = self._roadmap_metrics(visible_items)
        upcoming_deadlines = self._upcoming_deadlines(visible_items, limit=8)
        return {
            "scope_level": actor.scope_level.value,
            "scope_name": self.user_service.scope_label(actor),
            "blocked_count": len(blocked_items),
            "overdue_count": len(overdue_items),
            "overdue_items": overdue_items[:8],
            "blocked_items": blocked_items[:8],
            "recent_updates": self._annotate_recent_updates(sorted(visible_items, key=lambda item: item.updated_at, reverse=True)[:8]),
            "upcoming_deadlines": upcoming_deadlines,
            "objective_count": len(objectives),
            "objective_progress": self._avg_progress(objectives),
            "delivery_progress": self._avg_progress(delivery_items),
            "portfolio_completion": self._completion_rate(visible_items),
            "overall_completion": overall_completion,
            "division_count": len({row["name"] for row in focus_rows}) if actor.scope_level == DesignationScope.OPERATING_HEAD else len({user.division_id for user in visible_users if user.division_id}),
            "department_count": len({user.department_id for user in visible_users if user.department_id}),
            "team_count": len({user.team_id for user in visible_users if user.team_id}),
            "featured_members": featured_members,
            "designation_mix": [
                {
                    "label": "Operating Heads",
                    "count": len([user for user in active_users if user.scope_level == DesignationScope.OPERATING_HEAD]),
                },
                {
                    "label": "Division Heads",
                    "count": len([user for user in active_users if user.scope_level == DesignationScope.DIVISION_HEAD]),
                },
                {
                    "label": "Department Heads",
                    "count": len([user for user in active_users if user.scope_level == DesignationScope.DEPARTMENT_HEAD]),
                },
                {
                    "label": "Team Members",
                    "count": len([user for user in active_users if user.scope_level == DesignationScope.TEAM_MEMBER]),
                },
            ],
            "snapshots": {
                "active_members": len(active_users),
                "active_projects": sum(
                    1 for item in visible_items
                    if item.level == WorkItemLevel.OBJECTIVE and item.status in self.ACTIVE_STATUSES
                ),
                "open_work": sum(
                    1 for item in visible_items
                    if item.level in self.DELIVERY_LEVELS and item.status in self.ACTIVE_STATUSES
                ),
                "completed_today": sum(
                    1 for item in visible_items
                    if item.level in self.DELIVERY_LEVELS
                    and item.completed_at
                    and item.completed_at.date() == date.today()
                ),
            },
            "focus_label": focus_label,
            "focus_rows": focus_rows,
            "workload_rows": sorted(focus_rows, key=lambda row: (row["workload_percent"], row["open"]), reverse=True),
        }

    def manager_employee_analytics(self, actor: User) -> dict:
        team_items = self.work_item_service.list_for_actor(actor)
        employees = [user for user in self.user_service.list_visible_users(actor) if user.role == UserRole.EMPLOYEE]
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
            "scope_label": self.user_service.scope_label(actor),
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
        department_items = self.work_item_service.list_for_actor(user) if user else []
        delivery_items = [item for item in assigned_items if item.level in self.DELIVERY_LEVELS]
        upcoming_deadlines = self._upcoming_deadlines(delivery_items, limit=6)
        recent_updates = self._annotate_recent_updates(sorted(delivery_items, key=lambda item: item.updated_at, reverse=True)[:6])
        completed_count = sum(1 for item in delivery_items if item.status in self.CLOSED_STATUSES)
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
            "completion_rate": int((completed_count / len(delivery_items)) * 100) if delivery_items else 0,
            "avg_progress": self._avg_progress(delivery_items),
            "upcoming_deadlines": upcoming_deadlines,
            "recent_updates": recent_updates,
            "department_updates": self._annotate_recent_updates(sorted(department_items, key=lambda item: item.updated_at, reverse=True)[:6]),
            "department_open_work": sum(
                1 for item in department_items
                if item.level in self.DELIVERY_LEVELS
                and item.status in self.ACTIVE_STATUSES
            ),
        }

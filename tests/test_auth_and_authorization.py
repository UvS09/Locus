import os
from datetime import date, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

os.environ["APP_ENV"] = "test"
os.environ["SQLITE_DB_PATH"] = "test_task_manager.db"
os.environ["SECRET_KEY"] = "test-secret-key"

from app.config import get_settings

get_settings.cache_clear()

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import department, designation, division  # noqa: F401
from app.models.role import Role
from app.models.subtask import Subtask
from app.models.task import Task
from app.models.team import Team
from app.models.user import User
from app.models.work_item import WorkItem
from app.routes.common import redirect_with_message
from app.schemas.work_item import WorkItemCreate
from app.schemas.work_item import WorkItemUpdate
from app.services.task_service import TaskService
from app.utils.enums import TaskPriority, UserRole
from app.utils.security import hash_password
from app.utils.work_item_levels import WorkItemLevel, WorkItemStatus


def setup_module():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    team = Team(name="Alpha")
    db.add(team)
    db.flush()
    manager = User(
        full_name="Manager One",
        email="manager@honda.hmsi.in",
        role=UserRole.MANAGER,
        password_hash=hash_password("Password123"),
        team_id=team.id,
        must_change_password=False,
    )
    employee = User(
        full_name="Employee One",
        email="employee@honda.hmsi.in",
        role=UserRole.EMPLOYEE,
        password_hash=hash_password("Password123"),
        team_id=team.id,
        must_change_password=False,
    )
    outsider = User(
        full_name="Employee Two",
        email="employee2@honda.hmsi.in",
        role=UserRole.EMPLOYEE,
        password_hash=hash_password("Password123"),
        must_change_password=False,
    )
    db.add_all([manager, employee, outsider])
    db.flush()
    team.manager_id = manager.id
    db.commit()
    db.close()


def teardown_module():
    Base.metadata.drop_all(bind=engine)
    db_path = Path("test_task_manager.db")
    if db_path.exists():
        db_path.unlink()


def test_login_and_dashboard_redirect():
    client = TestClient(app)
    response = client.post(
        "/login",
        data={"email": "manager@honda.hmsi.in", "password": "Password123"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"


def test_manager_cannot_access_admin_dashboard():
    client = TestClient(app)
    client.post(
        "/login",
        data={"email": "manager@honda.hmsi.in", "password": "Password123"},
        follow_redirects=False,
    )
    response = client.get("/admin/dashboard")
    assert response.status_code == 403


def test_admin_can_create_and_assign_custom_role():
    db = SessionLocal()
    admin = User(
        full_name="Role Admin",
        email="role-admin@honda.hmsi.in",
        role=UserRole.ADMIN,
        password_hash=hash_password("Password123"),
        must_change_password=False,
    )
    db.add(admin)
    db.commit()
    db.close()

    client = TestClient(app)
    login_response = client.post(
        "/login",
        data={"email": "role-admin@honda.hmsi.in", "password": "Password123"},
        follow_redirects=False,
    )
    assert login_response.status_code == 303

    role_response = client.post(
        "/admin/roles",
        data={"name": "Supervisor", "access_level": "MANAGER", "description": "Leads a focused delivery pod."},
        follow_redirects=False,
    )
    assert role_response.status_code == 303

    db = SessionLocal()
    role = db.query(Role).filter(Role.name == "Supervisor").one()
    team = db.query(Team).filter(Team.name == "Alpha").one()
    db.close()

    user_response = client.post(
        "/admin/users",
        data={
            "full_name": "Supervisor One",
            "email": "supervisor@honda.hmsi.in",
            "role_key": f"custom:{role.id}",
            "team_id": str(team.id),
        },
        follow_redirects=False,
    )
    assert user_response.status_code == 303

    db = SessionLocal()
    supervisor = db.query(User).filter(User.email == "supervisor@honda.hmsi.in").one()
    assert supervisor.display_role == "Supervisor"
    assert supervisor.role == UserRole.MANAGER
    assert supervisor.custom_role_id == role.id
    db.close()


def test_manager_login_dashboard_renders_after_redirect():
    client = TestClient(app)
    response = client.post(
        "/login",
        data={"email": "manager@honda.hmsi.in", "password": "Password123"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Welcome back" in response.text
    assert "Manager One" in response.text


def test_redirect_with_message_preserves_existing_query_string():
    response = redirect_with_message("/create?level=OBJECTIVE", error="Sample issue")
    assert response.headers["location"] == "/create?level=OBJECTIVE&error=Sample+issue"


def test_manager_without_team_can_create_and_see_project():
    db = SessionLocal()
    manager = User(
        full_name="Scope Manager",
        email="scope-manager@honda.hmsi.in",
        role=UserRole.MANAGER,
        password_hash=hash_password("Password123"),
        must_change_password=False,
    )
    db.add(manager)
    db.commit()
    db.refresh(manager)

    service = TaskService(db)
    project = service.create_work_item(
        manager,
        WorkItemCreate(
            level=WorkItemLevel.OBJECTIVE,
            title="Teamless Project",
            description="Should still be visible to the creator.",
            priority=TaskPriority.MEDIUM,
            due_date=None,
            parent_id=None,
        ),
    )
    db.commit()

    visible_items = service.list_for_actor(manager)
    assert project.id is not None
    assert any(item.id == project.id for item in visible_items)

    db.delete(project)
    db.delete(manager)
    db.commit()
    db.close()


def test_employee_cannot_uncheck_completed_subtask_after_due_date():
    db = SessionLocal()
    manager = db.query(User).filter(User.email == "manager@honda.hmsi.in").one()
    employee = db.query(User).filter(User.email == "employee@honda.hmsi.in").one()
    task = Task(
        title="Locked Task",
        description="Past due task",
        assigned_to_id=employee.id,
        created_by_id=manager.id,
        team_id=employee.team_id,
        due_date=date.today() - timedelta(days=1),
    )
    db.add(task)
    db.flush()
    subtask = Subtask(task_id=task.id, title="Done item", is_completed=True)
    db.add(subtask)
    db.commit()

    service = TaskService(db)
    try:
        service.toggle_subtask(employee, task.id, subtask.id)
        assert False, "Expected overdue employee uncheck to fail."
    except ValueError as exc:
        assert str(exc) == "Completed subtasks cannot be unchecked after the task due date has passed."
    db.refresh(subtask)
    db.refresh(task)
    assert subtask.is_completed is True
    assert task.progress_percent == 0
    db.close()


def test_employee_can_check_incomplete_subtask_after_due_date():
    db = SessionLocal()
    manager = db.query(User).filter(User.email == "manager@honda.hmsi.in").one()
    employee = db.query(User).filter(User.email == "employee@honda.hmsi.in").one()
    task = Task(
        title="Overdue Task",
        description="Past due task",
        assigned_to_id=employee.id,
        created_by_id=manager.id,
        team_id=employee.team_id,
        due_date=date.today() - timedelta(days=1),
    )
    db.add(task)
    db.flush()
    subtask = Subtask(task_id=task.id, title="Todo item", is_completed=False)
    db.add(subtask)
    db.commit()

    service = TaskService(db)
    updated_task = service.toggle_subtask(employee, task.id, subtask.id)
    db.commit()
    db.refresh(subtask)
    assert subtask.is_completed is True
    assert updated_task.progress_percent == 100
    db.close()


def test_employee_can_uncheck_completed_subtask_on_due_date():
    db = SessionLocal()
    manager = db.query(User).filter(User.email == "manager@honda.hmsi.in").one()
    employee = db.query(User).filter(User.email == "employee@honda.hmsi.in").one()
    task = Task(
        title="Due Today Task",
        description="Due today",
        assigned_to_id=employee.id,
        created_by_id=manager.id,
        team_id=employee.team_id,
        due_date=date.today(),
    )
    db.add(task)
    db.flush()
    subtask = Subtask(task_id=task.id, title="Done item", is_completed=True)
    db.add(subtask)
    db.commit()

    service = TaskService(db)
    updated_task = service.toggle_subtask(employee, task.id, subtask.id)
    db.commit()
    db.refresh(subtask)
    assert subtask.is_completed is False
    assert updated_task.progress_percent == 0
    db.close()


def test_manager_can_uncheck_completed_subtask_after_due_date():
    db = SessionLocal()
    manager = db.query(User).filter(User.email == "manager@honda.hmsi.in").one()
    employee = db.query(User).filter(User.email == "employee@honda.hmsi.in").one()
    task = Task(
        title="Manager Override Task",
        description="Past due task",
        assigned_to_id=employee.id,
        created_by_id=manager.id,
        team_id=employee.team_id,
        due_date=date.today() - timedelta(days=1),
    )
    db.add(task)
    db.flush()
    subtask = Subtask(task_id=task.id, title="Done item", is_completed=True)
    db.add(subtask)
    db.commit()

    service = TaskService(db)
    updated_task = service.toggle_subtask(manager, task.id, subtask.id)
    db.commit()
    db.refresh(subtask)
    assert subtask.is_completed is False
    assert updated_task.progress_percent == 0
    db.close()


def test_admin_can_uncheck_completed_subtask_after_due_date():
    db = SessionLocal()
    team = db.query(Team).filter(Team.name == "Alpha").one()
    admin = User(
        full_name="Admin One",
        email="admin@honda.hmsi.in",
        role=UserRole.ADMIN,
        password_hash=hash_password("Password123"),
        must_change_password=False,
    )
    db.add(admin)
    db.flush()
    employee = db.query(User).filter(User.email == "employee@honda.hmsi.in").one()
    task = Task(
        title="Admin Override Task",
        description="Past due task",
        assigned_to_id=employee.id,
        created_by_id=admin.id,
        team_id=team.id,
        due_date=date.today() - timedelta(days=1),
    )
    db.add(task)
    db.flush()
    subtask = Subtask(task_id=task.id, title="Done item", is_completed=True)
    db.add(subtask)
    db.commit()

    service = TaskService(db)
    updated_task = service.toggle_subtask(admin, task.id, subtask.id)
    db.commit()
    db.refresh(subtask)
    assert subtask.is_completed is False
    assert updated_task.progress_percent == 0
    db.close()


def test_employee_can_toggle_when_due_date_is_none():
    db = SessionLocal()
    manager = db.query(User).filter(User.email == "manager@honda.hmsi.in").one()
    employee = db.query(User).filter(User.email == "employee@honda.hmsi.in").one()
    task = Task(
        title="No Due Date Task",
        description="No due date",
        assigned_to_id=employee.id,
        created_by_id=manager.id,
        team_id=employee.team_id,
        due_date=None,
    )
    db.add(task)
    db.flush()
    subtask = Subtask(task_id=task.id, title="Done item", is_completed=True)
    db.add(subtask)
    db.commit()

    service = TaskService(db)
    updated_task = service.toggle_subtask(employee, task.id, subtask.id)
    db.commit()
    db.refresh(subtask)
    assert subtask.is_completed is False
    assert updated_task.progress_percent == 0
    db.close()


def test_manager_can_create_objective_workstream_and_activity():
    db = SessionLocal()
    manager = db.query(User).filter(User.email == "manager@honda.hmsi.in").one()
    service = TaskService(db)

    objective = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.OBJECTIVE,
            "title": "Launch delivery program",
            "description": "Top level objective",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.HIGH,
            "due_date": None,
            "parent_id": None,
        })(),
    )
    workstream = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.WORKSTREAM,
            "title": "Platform rollout",
            "description": "Workstream",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.HIGH,
            "due_date": None,
            "parent_id": objective.id,
        })(),
    )
    activity = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.ACTIVITY,
            "title": "Pilot onboarding",
            "description": "Activity",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.MEDIUM,
            "due_date": None,
            "parent_id": workstream.id,
        })(),
    )
    db.commit()

    assert objective.level == WorkItemLevel.OBJECTIVE
    assert workstream.parent_id == objective.id
    assert activity.parent_id == workstream.id
    db.close()


def test_team_members_can_see_shared_hierarchy_and_parent_options():
    db = SessionLocal()
    manager = db.query(User).filter(User.email == "manager@honda.hmsi.in").one()
    service = TaskService(db)

    objective = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.OBJECTIVE,
            "title": "Shared objective",
            "description": "Visible to the full team",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.HIGH,
            "due_date": None,
            "parent_id": None,
        })(),
    )
    workstream = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.WORKSTREAM,
            "title": "Shared workstream",
            "description": "Visible to the full team",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.MEDIUM,
            "due_date": None,
            "parent_id": objective.id,
        })(),
    )
    workstream_id = workstream.id
    db.commit()
    db.close()

    client = TestClient(app)
    client.post(
        "/login",
        data={"email": "employee@honda.hmsi.in", "password": "Password123"},
        follow_redirects=False,
    )

    objectives_response = client.get("/objectives")
    assert objectives_response.status_code == 200
    assert "Shared objective" in objectives_response.text

    milestone_response = client.get(f"/workstreams/{workstream_id}")
    assert milestone_response.status_code == 200
    assert "Shared workstream" in milestone_response.text
    assert "Create Activity" in milestone_response.text

    create_response = client.get("/create", params={"level": WorkItemLevel.ACTIVITY.value}, follow_redirects=False)
    assert create_response.status_code == 303


def test_employee_cannot_create_objective():
    db = SessionLocal()
    employee = db.query(User).filter(User.email == "employee@honda.hmsi.in").one()
    service = TaskService(db)
    try:
        service.create_work_item(
            employee,
            type("Payload", (), {
                "level": WorkItemLevel.OBJECTIVE,
                "title": "Forbidden objective",
                "description": "Should fail",
                "assigned_to_id": employee.id,
                "priority": TaskPriority.HIGH,
                "due_date": None,
                "parent_id": None,
            })(),
        )
        assert False, "Expected employee objective creation to fail."
    except ValueError as exc:
        assert str(exc) == "Employees can create milestones, activities, and tasks only."
    db.close()


def test_blocking_work_does_not_inflate_progress():
    db = SessionLocal()
    manager = db.query(User).filter(User.email == "manager@honda.hmsi.in").one()
    service = TaskService(db)
    project = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.OBJECTIVE,
            "title": "Blocked progress project",
            "description": "",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.HIGH,
            "due_date": None,
            "parent_id": None,
        })(),
    )
    milestone = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.WORKSTREAM,
            "title": "Blocked progress milestone",
            "description": "",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.MEDIUM,
            "due_date": None,
            "parent_id": project.id,
        })(),
    )
    service.update_work_item(
        manager,
        milestone.id,
        WorkItemUpdate(
            title=milestone.title,
            description=milestone.description,
            assigned_to_id=manager.id,
            priority=milestone.priority,
            status=WorkItemStatus.BLOCKED,
            due_date=None,
        ),
    )
    db.commit()

    assert milestone.status == WorkItemStatus.BLOCKED
    assert milestone.progress_percent == 0
    assert project.status == WorkItemStatus.IN_PROGRESS
    assert project.progress_percent == 0
    db.close()


def test_blocked_parent_keeps_last_child_progress_and_renders_strike():
    db = SessionLocal()
    manager = db.query(User).filter(User.email == "manager@honda.hmsi.in").one()
    service = TaskService(db)
    project = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.OBJECTIVE,
            "title": "Blocked rollup project",
            "description": "",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.HIGH,
            "due_date": None,
            "parent_id": None,
        })(),
    )
    milestone = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.WORKSTREAM,
            "title": "Blocked rollup milestone",
            "description": "",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.MEDIUM,
            "due_date": None,
            "parent_id": project.id,
        })(),
    )
    activity = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.ACTIVITY,
            "title": "Blocked rollup activity",
            "description": "",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.MEDIUM,
            "due_date": None,
            "parent_id": milestone.id,
        })(),
    )
    first_task = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.TASK,
            "title": "Completed child",
            "description": "",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.MEDIUM,
            "due_date": None,
            "parent_id": activity.id,
        })(),
    )
    service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.TASK,
            "title": "Open child",
            "description": "",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.MEDIUM,
            "due_date": None,
            "parent_id": activity.id,
        })(),
    )
    service.update_work_item(
        manager,
        first_task.id,
        WorkItemUpdate(
            title=first_task.title,
            description=first_task.description,
            assigned_to_id=manager.id,
            priority=first_task.priority,
            status=WorkItemStatus.COMPLETED,
            due_date=None,
        ),
    )
    service.update_work_item(
        manager,
        activity.id,
        WorkItemUpdate(
            title=activity.title,
            description=activity.description,
            assigned_to_id=manager.id,
            priority=activity.priority,
            status=WorkItemStatus.BLOCKED,
            due_date=None,
        ),
    )
    db.commit()
    activity_id = activity.id

    assert activity.status == WorkItemStatus.BLOCKED
    assert activity.progress_percent == 50
    assert milestone.progress_percent == 50
    assert project.progress_percent == 50
    db.close()

    client = TestClient(app)
    client.post(
        "/login",
        data={"email": "manager@honda.hmsi.in", "password": "Password123"},
        follow_redirects=False,
    )
    response = client.get(f"/activities/{activity_id}")
    assert response.status_code == 200
    assert "progress-is-blocked" in response.text


def test_blocked_project_with_children_can_be_unblocked():
    db = SessionLocal()
    manager = db.query(User).filter(User.email == "manager@honda.hmsi.in").one()
    service = TaskService(db)
    project = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.OBJECTIVE,
            "title": "Manually blocked project",
            "description": "",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.HIGH,
            "due_date": None,
            "parent_id": None,
        })(),
    )
    service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.WORKSTREAM,
            "title": "Project milestone",
            "description": "",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.MEDIUM,
            "due_date": None,
            "parent_id": project.id,
        })(),
    )
    for status in (WorkItemStatus.BLOCKED, WorkItemStatus.IN_PROGRESS):
        service.update_work_item(
            manager,
            project.id,
            WorkItemUpdate(
                title=project.title,
                description=project.description,
                assigned_to_id=manager.id,
                priority=project.priority,
                status=status,
                due_date=None,
            ),
        )
        assert project.status == status
    db.close()


def test_reopened_in_progress_work_does_not_remain_at_100_percent():
    db = SessionLocal()
    manager = db.query(User).filter(User.email == "manager@honda.hmsi.in").one()
    service = TaskService(db)
    item = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.OBJECTIVE,
            "title": "Reopened progress project",
            "description": "",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.MEDIUM,
            "due_date": None,
            "parent_id": None,
        })(),
    )
    for status in (WorkItemStatus.COMPLETED, WorkItemStatus.IN_PROGRESS):
        service.update_work_item(
            manager,
            item.id,
            WorkItemUpdate(
                title=item.title,
                description=item.description,
                assigned_to_id=manager.id,
                priority=item.priority,
                status=status,
                due_date=None,
            ),
        )

    assert item.status == WorkItemStatus.IN_PROGRESS
    assert item.progress_percent == 50
    db.close()


def test_project_create_can_make_task_without_existing_hierarchy():
    db = SessionLocal()
    manager = db.query(User).filter(User.email == "manager@honda.hmsi.in").one()
    project = TaskService(db).create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.OBJECTIVE,
            "title": "Direct task project",
            "description": "",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.HIGH,
            "due_date": None,
            "parent_id": None,
        })(),
    )
    project_id = project.id
    db.commit()
    db.close()

    client = TestClient(app)
    client.post(
        "/login",
        data={"email": "manager@honda.hmsi.in", "password": "Password123"},
        follow_redirects=False,
    )
    response = client.post(
        f"/objectives/{project_id}/create",
        data={
            "level": WorkItemLevel.TASK.value,
            "title": "Directly created task",
            "description": "",
            "priority": TaskPriority.MEDIUM.value,
            "due_date": "",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    task = db.query(WorkItem).filter(WorkItem.title == "Directly created task").one()
    assert task.level == WorkItemLevel.TASK
    assert task.parent.level == WorkItemLevel.ACTIVITY
    assert task.parent.parent.level == WorkItemLevel.WORKSTREAM
    assert task.parent.parent.parent_id == project_id
    db.close()


def test_employee_can_create_task_inside_accessible_activity():
    db = SessionLocal()
    manager = db.query(User).filter(User.email == "manager@honda.hmsi.in").one()
    employee = db.query(User).filter(User.email == "employee@honda.hmsi.in").one()
    service = TaskService(db)
    objective = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.OBJECTIVE,
            "title": "Team objective",
            "description": "Objective",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.HIGH,
            "due_date": None,
            "parent_id": None,
        })(),
    )
    workstream = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.WORKSTREAM,
            "title": "Team workstream",
            "description": "Workstream",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.HIGH,
            "due_date": None,
            "parent_id": objective.id,
        })(),
    )
    activity = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.ACTIVITY,
            "title": "Team activity",
            "description": "Activity",
            "assigned_to_id": employee.id,
            "priority": TaskPriority.MEDIUM,
            "due_date": None,
            "parent_id": workstream.id,
        })(),
    )
    task = service.create_work_item(
        employee,
        type("Payload", (), {
            "level": WorkItemLevel.TASK,
            "title": "Employee task",
            "description": "Task",
            "assigned_to_id": employee.id,
            "priority": TaskPriority.LOW,
            "due_date": None,
            "parent_id": activity.id,
        })(),
    )
    db.commit()

    assert task.level == WorkItemLevel.TASK
    assert task.parent_id == activity.id
    assert task.assigned_to_id == employee.id
    db.close()


def test_manager_cannot_access_another_teams_hierarchy():
    db = SessionLocal()
    other_team = Team(name="Beta")
    db.add(other_team)
    db.flush()
    other_manager = User(
        full_name="Manager Two",
        email="manager2@honda.hmsi.in",
        role=UserRole.MANAGER,
        password_hash=hash_password("Password123"),
        team_id=other_team.id,
        must_change_password=False,
    )
    db.add(other_manager)
    db.flush()
    other_team.manager_id = other_manager.id
    service = TaskService(db)
    objective = service.create_work_item(
        other_manager,
        type("Payload", (), {
            "level": WorkItemLevel.OBJECTIVE,
            "title": "Other team objective",
            "description": "Objective",
            "assigned_to_id": other_manager.id,
            "priority": TaskPriority.HIGH,
            "due_date": None,
            "parent_id": None,
        })(),
    )
    db.commit()

    manager = db.query(User).filter(User.email == "manager@honda.hmsi.in").one()
    try:
        service.get_accessible_work_item(manager, objective.id)
        assert False, "Expected team boundary check to fail."
    except ValueError as exc:
        assert str(exc) == "You do not have access to this work item."
    db.close()


def test_login_page_uses_locus_and_honda_branding():
    response = TestClient(app).get("/login")

    assert response.status_code == 200
    assert "Sign in to Locus" in response.text
    assert "HONDA" in response.text
    assert "Enterprise Work Management" not in response.text


def test_objective_owner_is_always_the_creating_manager():
    db = SessionLocal()
    manager = db.query(User).filter(User.email == "manager@honda.hmsi.in").one()
    employee = db.query(User).filter(User.email == "employee@honda.hmsi.in").one()

    objective = TaskService(db).create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.OBJECTIVE,
            "title": "Manager owned objective",
            "description": "Ownership cannot be delegated",
            "assigned_to_id": employee.id,
            "priority": TaskPriority.HIGH,
            "due_date": None,
            "parent_id": None,
        })(),
    )
    db.commit()

    assert objective.assigned_to_id == manager.id
    db.close()


def test_completion_notification_names_task_and_actor():
    db = SessionLocal()
    manager = db.query(User).filter(User.email == "manager@honda.hmsi.in").one()
    employee = db.query(User).filter(User.email == "employee@honda.hmsi.in").one()
    service = TaskService(db)

    objective = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.OBJECTIVE,
            "title": "Notification objective",
            "description": "",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.HIGH,
            "due_date": None,
            "parent_id": None,
        })(),
    )
    workstream = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.WORKSTREAM,
            "title": "Notification workstream",
            "description": "",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.MEDIUM,
            "due_date": None,
            "parent_id": objective.id,
        })(),
    )
    activity = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.ACTIVITY,
            "title": "Notification activity",
            "description": "",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.MEDIUM,
            "due_date": None,
            "parent_id": workstream.id,
        })(),
    )
    task = service.create_work_item(
        employee,
        type("Payload", (), {
            "level": WorkItemLevel.TASK,
            "title": "Prepare pilot report",
            "description": "",
            "assigned_to_id": employee.id,
            "priority": TaskPriority.HIGH,
            "due_date": None,
            "parent_id": activity.id,
        })(),
    )
    service.update_work_item(
        manager,
        task.id,
        WorkItemUpdate(
            title=task.title,
            description=task.description,
            assigned_to_id=manager.id,
            priority=task.priority,
            status=WorkItemStatus.COMPLETED,
            due_date=None,
        ),
    )
    db.commit()

    notifications = service.notification_service.list_for_user(employee)
    assert any(
        notification.display_message == 'Task "Prepare pilot report" completed by Manager One'
        for notification in notifications
    )
    db.close()


def test_all_role_routes_render_without_server_errors():
    db = SessionLocal()
    manager = db.query(User).filter(User.email == "manager@honda.hmsi.in").one()
    employee = db.query(User).filter(User.email == "employee@honda.hmsi.in").one()
    admin = db.query(User).filter(User.email == "route-admin@honda.hmsi.in").one_or_none()
    if admin is None:
        admin = User(
            full_name="Route Admin",
            email="route-admin@honda.hmsi.in",
            role=UserRole.ADMIN,
            password_hash=hash_password("Password123"),
            must_change_password=False,
        )
        db.add(admin)
        db.flush()

    service = TaskService(db)
    objective = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.OBJECTIVE,
            "title": "Route objective",
            "description": "",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.HIGH,
            "due_date": None,
            "parent_id": None,
        })(),
    )
    workstream = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.WORKSTREAM,
            "title": "Route workstream",
            "description": "",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.MEDIUM,
            "due_date": None,
            "parent_id": objective.id,
        })(),
    )
    activity = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.ACTIVITY,
            "title": "Route activity",
            "description": "",
            "assigned_to_id": employee.id,
            "priority": TaskPriority.MEDIUM,
            "due_date": None,
            "parent_id": workstream.id,
        })(),
    )
    task = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.TASK,
            "title": "Route task",
            "description": "",
            "assigned_to_id": employee.id,
            "priority": TaskPriority.MEDIUM,
            "due_date": None,
            "parent_id": activity.id,
        })(),
    )
    db.commit()
    route_ids = (objective.id, workstream.id, activity.id, task.id)
    db.close()

    public_routes = ["/", "/health", "/login"]
    common_routes = [
        "/dashboard",
        "/change-password",
        "/objectives",
        f"/objectives/{route_ids[0]}",
        f"/workstreams/{route_ids[1]}",
        f"/activities/{route_ids[2]}",
        f"/activities/{route_ids[2]}?view=board",
        f"/tasks/{route_ids[3]}",
        "/subtasks",
        "/notifications",
    ]
    role_routes = {
        "manager@honda.hmsi.in": ["/manager/dashboard", "/manager/reports", "/manager/tasks", "/manager/team-members", "/create?level=OBJECTIVE"],
        "employee@honda.hmsi.in": ["/employee/dashboard", "/employee/analytics", "/employee/tasks", "/create?level=TASK"],
        "route-admin@honda.hmsi.in": ["/admin/dashboard", "/admin/users", "/admin/teams", "/admin/audit-logs", "/admin/reports"],
    }

    public_client = TestClient(app)
    for path in public_routes:
        assert public_client.get(path, follow_redirects=False).status_code < 500, path

    for email, paths in role_routes.items():
        client = TestClient(app, raise_server_exceptions=False)
        login_response = client.post(
            "/login",
            data={"email": email, "password": "Password123"},
            follow_redirects=False,
        )
        assert login_response.status_code == 303
        for path in common_routes + paths:
            assert client.get(path, follow_redirects=False).status_code < 500, f"{email}: {path}"


def test_manager_can_download_employee_analytics_excel():
    client = TestClient(app)
    client.post(
        "/login",
        data={"email": "manager@honda.hmsi.in", "password": "Password123"},
        follow_redirects=False,
    )
    response = client.get("/manager/reports/export")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert response.content[:2] == b"PK"
    assert "employee-analytics-" in response.headers["content-disposition"]


def test_employee_analytics_is_personal_and_sidebar_label_is_analytics():
    client = TestClient(app)
    client.post(
        "/login",
        data={"email": "employee@honda.hmsi.in", "password": "Password123"},
        follow_redirects=False,
    )
    response = client.get("/employee/analytics")
    assert response.status_code == 200
    assert "My Analytics" in response.text
    assert "My Progress" in response.text
    assert ">Analytics</span>" in response.text
    assert "Download Excel" not in response.text
    assert "Employee Workload Analytics" not in response.text


def test_creator_can_delete_own_work_item():
    db = SessionLocal()
    manager = db.query(User).filter(User.email == "manager@honda.hmsi.in").one()
    service = TaskService(db)
    objective = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.OBJECTIVE,
            "title": "Disposable objective",
            "description": "",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.MEDIUM,
            "due_date": None,
            "parent_id": None,
        })(),
    )
    workstream = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.WORKSTREAM,
            "title": "Disposable workstream",
            "description": "",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.MEDIUM,
            "due_date": None,
            "parent_id": objective.id,
        })(),
    )
    objective_id = objective.id
    workstream_id = workstream.id
    service.delete_work_item(manager, objective_id)
    db.commit()

    assert db.get(WorkItem, objective_id) is None
    assert db.get(WorkItem, workstream_id) is None
    db.close()


def test_assignee_cannot_delete_work_created_by_someone_else():
    db = SessionLocal()
    manager = db.query(User).filter(User.email == "manager@honda.hmsi.in").one()
    employee = db.query(User).filter(User.email == "employee@honda.hmsi.in").one()
    service = TaskService(db)
    objective = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.OBJECTIVE,
            "title": "Protected objective",
            "description": "",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.MEDIUM,
            "due_date": None,
            "parent_id": None,
        })(),
    )
    workstream = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.WORKSTREAM,
            "title": "Protected workstream",
            "description": "",
            "assigned_to_id": employee.id,
            "priority": TaskPriority.MEDIUM,
            "due_date": None,
            "parent_id": objective.id,
        })(),
    )
    db.commit()

    try:
        service.delete_work_item(employee, workstream.id)
        assert False, "Expected creator-only deletion to fail."
    except ValueError as exc:
        assert str(exc) == "You can delete only work items that you created."
    db.rollback()
    assert db.get(WorkItem, workstream.id) is not None
    db.close()


def test_parent_deletion_is_blocked_when_descendant_has_another_creator():
    db = SessionLocal()
    manager = db.query(User).filter(User.email == "manager@honda.hmsi.in").one()
    employee = db.query(User).filter(User.email == "employee@honda.hmsi.in").one()
    service = TaskService(db)
    objective = service.create_work_item(
        manager,
        type("Payload", (), {
            "level": WorkItemLevel.OBJECTIVE,
            "title": "Shared deletion objective",
            "description": "",
            "assigned_to_id": manager.id,
            "priority": TaskPriority.MEDIUM,
            "due_date": None,
            "parent_id": None,
        })(),
    )
    workstream = service.create_work_item(
        employee,
        type("Payload", (), {
            "level": WorkItemLevel.WORKSTREAM,
            "title": "Employee-owned child",
            "description": "",
            "assigned_to_id": employee.id,
            "priority": TaskPriority.MEDIUM,
            "due_date": None,
            "parent_id": objective.id,
        })(),
    )
    db.commit()

    try:
        service.delete_work_item(manager, objective.id)
        assert False, "Expected mixed-creator subtree deletion to fail."
    except ValueError as exc:
        assert str(exc) == "This item contains work created by another team member and cannot be deleted."
    db.rollback()
    assert db.get(WorkItem, objective.id) is not None
    assert db.get(WorkItem, workstream.id) is not None
    db.close()


def test_admin_panel_navigation_and_workspace_route_render():
    db = SessionLocal()
    admin = User(
        full_name="Dashboard Admin",
        email="dashboard-admin@honda.hmsi.in",
        role=UserRole.ADMIN,
        password_hash=hash_password("Password123"),
        must_change_password=False,
    )
    db.add(admin)
    db.commit()
    db.close()

    client = TestClient(app)
    login_response = client.post(
        "/login",
        data={"email": "dashboard-admin@honda.hmsi.in", "password": "Password123"},
        follow_redirects=False,
    )
    assert login_response.status_code == 303

    workspace_response = client.get("/admin/workspace")
    assert workspace_response.status_code == 200
    assert "Workspace" in workspace_response.text
    assert "Administration" in workspace_response.text
    assert "Audit Logs" in workspace_response.text

    reports_response = client.get("/admin/reports")
    assert reports_response.status_code == 200
    assert "Employee Productivity" in reports_response.text


def test_admin_can_update_user_email_and_delete_user_permanently():
    db = SessionLocal()
    admin = User(
        full_name="Lifecycle Admin",
        email="lifecycle-admin@honda.hmsi.in",
        role=UserRole.ADMIN,
        password_hash=hash_password("Password123"),
        must_change_password=False,
    )
    employee = User(
        full_name="Lifecycle Employee",
        email="lifecycle-employee@honda.hmsi.in",
        role=UserRole.EMPLOYEE,
        password_hash=hash_password("Password123"),
        must_change_password=False,
    )
    db.add_all([admin, employee])
    db.commit()
    employee_id = employee.id
    db.close()

    client = TestClient(app)
    login_response = client.post(
        "/login",
        data={"email": "lifecycle-admin@honda.hmsi.in", "password": "Password123"},
        follow_redirects=False,
    )
    assert login_response.status_code == 303

    update_response = client.post(
        f"/admin/users/{employee_id}",
        data={
            "full_name": "Lifecycle Employee Updated",
            "email": "updated-employee@honda.hmsi.in",
            "role_key": "system:EMPLOYEE",
            "team_id": "",
            "is_active": "true",
        },
        follow_redirects=False,
    )
    assert update_response.status_code == 303

    db = SessionLocal()
    updated_employee = db.query(User).filter(User.id == employee_id).one()
    assert updated_employee.email == "updated-employee@honda.hmsi.in"
    db.close()

    delete_response = client.post(f"/admin/users/{employee_id}/delete", follow_redirects=False)
    assert delete_response.status_code == 303

    db = SessionLocal()
    deleted_user = db.query(User).filter(User.id == employee_id).one_or_none()
    assert deleted_user is None

    replacement_user = User(
        full_name="Replacement Employee",
        email="updated-employee@honda.hmsi.in",
        role=UserRole.EMPLOYEE,
        password_hash=hash_password("Password123"),
        must_change_password=False,
    )
    db.add(replacement_user)
    db.commit()
    assert replacement_user.id is not None
    db.close()

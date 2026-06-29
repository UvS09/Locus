from datetime import date

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db_session
from app.dependencies.role_dependencies import require_roles
from app.models.user import User
from app.routes.common import build_context, redirect_with_message, templates
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.report_service import ReportService
from app.services.task_service import TaskService
from app.services.team_service import TeamService
from app.services.user_service import UserService
from app.utils.enums import TaskPriority, UserRole
from app.utils.work_item_levels import WorkItemLevel
from app.utils.xlsx_export import build_xlsx

router = APIRouter(prefix="/manager", tags=["manager"])


@router.get("/dashboard", response_class=HTMLResponse)
async def manager_dashboard(request: Request, current_user: User = Depends(require_roles(UserRole.MANAGER)), db: Session = Depends(get_db_session)):
    try:
        team = TeamService(db).get_team_for_manager(current_user)
        stats = ReportService(db).manager_dashboard(team.id)
    except Exception as exc:
        return templates.TemplateResponse(
            "manager/dashboard.html",
            build_context(request, current_user=current_user, db=db, team=None, stats=None, employees=[], priorities=list(TaskPriority), error=str(exc)),
            status_code=400,
        )
    employees = UserService(db).list_employees()
    return templates.TemplateResponse(
        "manager/dashboard.html",
        build_context(
            request,
            current_user=current_user,
            db=db,
            team=team,
            stats=stats,
            employees=employees,
            priorities=list(TaskPriority),
            detail_labels={
                WorkItemLevel.OBJECTIVE: "Project",
                WorkItemLevel.WORKSTREAM: "Milestone",
                WorkItemLevel.ACTIVITY: "Activity",
                WorkItemLevel.TASK: "Task",
                WorkItemLevel.SUB_TASK: "Sub-task",
            },
        ),
    )


@router.get("/reports", response_class=HTMLResponse)
async def manager_reports(
    request: Request,
    current_user: User = Depends(require_roles(UserRole.MANAGER)),
    db: Session = Depends(get_db_session),
):
    try:
        team = TeamService(db).get_team_for_manager(current_user)
        stats = ReportService(db).manager_employee_analytics(team.id)
    except Exception as exc:
        return templates.TemplateResponse(
            "manager/reports.html",
            build_context(request, current_user=current_user, db=db, team=None, stats=None, error=str(exc)),
            status_code=400,
        )
    return templates.TemplateResponse(
        "manager/reports.html",
        build_context(request, current_user=current_user, db=db, team=team, stats=stats),
    )


@router.get("/reports/export")
async def export_manager_reports(
    current_user: User = Depends(require_roles(UserRole.MANAGER)),
    db: Session = Depends(get_db_session),
):
    team = TeamService(db).get_team_for_manager(current_user)
    stats = ReportService(db).manager_employee_analytics(team.id)
    rows = [
        ["Employee", "Email", "Assigned Work", "Open", "In Progress", "Blocked", "Overdue", "Completed", "Completion Rate", "Average Progress"],
    ]
    for row in stats["employees"]:
        employee = row["employee"]
        rows.append(
            [
                employee.full_name,
                employee.email,
                row["assigned"],
                row["open"],
                row["in_progress"],
                row["blocked"],
                row["overdue"],
                row["completed"],
                f'{row["completion_rate"]}%',
                f'{row["avg_progress"]}%',
            ]
        )
    content = build_xlsx(rows, sheet_name="Employee Analytics")
    filename = f"employee-analytics-{date.today().isoformat()}.xlsx"
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/tasks", response_class=HTMLResponse)
async def manager_tasks(
    request: Request,
    status: str = Query(""),
    overdue: bool = Query(False),
    current_user: User = Depends(require_roles(UserRole.MANAGER)),
    db: Session = Depends(get_db_session),
):
    task_service = TaskService(db)
    employees = [user for user in UserService(db).list_employees() if user.team_id == current_user.team_id]
    tasks = task_service.list_tasks_for_actor(current_user)
    if status:
        tasks = [task for task in tasks if task.status.value == status]
    if overdue:
        tasks = [
            task for task in tasks
            if task.due_date and task.due_date < date.today() and task.status.value not in {"COMPLETED", "CLOSED"}
        ]
    return templates.TemplateResponse(
        "manager/tasks.html",
        build_context(
            request,
            current_user=current_user,
            db=db,
            tasks=tasks,
            employees=employees,
            priorities=list(TaskPriority),
            selected_status=status,
            selected_overdue=overdue,
        ),
    )


@router.post("/tasks")
async def create_task(
    title: str = Form(...),
    description: str = Form(""),
    priority: TaskPriority = Form(TaskPriority.MEDIUM),
    due_date: str | None = Form(None),
    current_user: User = Depends(require_roles(UserRole.MANAGER)),
    db: Session = Depends(get_db_session),
):
    task_service = TaskService(db)
    try:
        payload = TaskCreate(
            level=WorkItemLevel.TASK,
            title=title,
            description=description,
            priority=priority,
            due_date=due_date or None,
        )
        task_service.create_task(current_user, payload)
        db.commit()
        return redirect_with_message("/manager/tasks", message="Task created.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/manager/tasks", error=str(exc))


@router.post("/tasks/{task_id}")
async def update_task(
    task_id: int,
    title: str = Form(...),
    description: str = Form(""),
    priority: TaskPriority = Form(TaskPriority.MEDIUM),
    due_date: str | None = Form(None),
    current_user: User = Depends(require_roles(UserRole.MANAGER)),
    db: Session = Depends(get_db_session),
):
    task_service = TaskService(db)
    try:
        payload = TaskUpdate(
            title=title,
            description=description,
            priority=priority,
            due_date=due_date or None,
        )
        task_service.update_task(current_user, task_id, payload)
        db.commit()
        return redirect_with_message("/manager/tasks", message="Task updated.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/manager/tasks", error=str(exc))


@router.post("/tasks/{task_id}/close")
async def close_task(task_id: int, current_user: User = Depends(require_roles(UserRole.MANAGER)), db: Session = Depends(get_db_session)):
    task_service = TaskService(db)
    try:
        task_service.close_task(current_user, task_id)
        db.commit()
        return redirect_with_message("/manager/tasks", message="Task closed.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/manager/tasks", error=str(exc))


@router.get("/team-members", response_class=HTMLResponse)
async def team_members_page(request: Request, current_user: User = Depends(require_roles(UserRole.MANAGER)), db: Session = Depends(get_db_session)):
    employees = [user for user in UserService(db).list_employees() if user.team_id == current_user.team_id]
    return templates.TemplateResponse(
        "manager/team_members.html",
        build_context(request, current_user=current_user, db=db, employees=employees),
    )

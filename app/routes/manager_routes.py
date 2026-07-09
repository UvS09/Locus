from datetime import date

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db_session
from app.dependencies.role_dependencies import require_roles
from app.models.department import Department
from app.models.division import Division
from app.models.user import User
from app.routes.common import build_context, redirect_with_message, templates
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.report_service import ReportService
from app.services.task_service import TaskService
from app.services.user_service import UserService
from app.utils.report_exports import build_manager_report_pdf, build_manager_report_xlsx
from app.utils.enums import TaskPriority, UserRole
from app.utils.work_item_levels import WorkItemLevel

router = APIRouter(prefix="/manager", tags=["manager"])


@router.get("/dashboard", response_class=HTMLResponse)
async def manager_dashboard(request: Request, current_user: User = Depends(require_roles(UserRole.MANAGER)), db: Session = Depends(get_db_session)):
    stats = ReportService(db).manager_dashboard(current_user)
    visible_members = [user for user in UserService(db).list_visible_users(current_user) if user.role != UserRole.ADMIN]
    return templates.TemplateResponse(
        "manager/dashboard.html",
        build_context(
            request,
            current_user=current_user,
            db=db,
            stats=stats,
            visible_members=visible_members,
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
    stats = ReportService(db).manager_employee_analytics(current_user)
    return templates.TemplateResponse(
        "manager/reports.html",
        build_context(request, current_user=current_user, db=db, stats=stats),
    )


@router.get("/reports/export")
async def export_manager_reports(
    format: str = Query("xlsx"),
    current_user: User = Depends(require_roles(UserRole.MANAGER)),
    db: Session = Depends(get_db_session),
):
    stats = ReportService(db).manager_employee_analytics(current_user)
    safe_format = format.lower()
    filename_base = f"employee-analytics-{date.today().isoformat()}"
    if safe_format == "pdf":
        return Response(
            build_manager_report_pdf(stats),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename_base}.pdf"'},
        )
    content = build_manager_report_xlsx(stats)
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename_base}.xlsx"'},
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
    division_id = request.query_params.get("division_id", "").strip()
    department_id = request.query_params.get("department_id", "").strip()
    user_service = UserService(db)
    users = [user for user in user_service.list_visible_users(current_user) if user.role != UserRole.ADMIN]
    if division_id:
        users = [user for user in users if str(user.division_id or "") == division_id]
    if department_id:
        users = [user for user in users if str(user.department_id or "") == department_id]
    users = sorted(
        users,
        key=lambda user: (
            0 if user.is_active else 1,
            -(user.designation.rank if user.designation else 0),
            user.full_name.lower(),
        ),
    )
    selected_division = db.get(Division, int(division_id)) if division_id.isdigit() else None
    selected_department = db.get(Department, int(department_id)) if department_id.isdigit() else None
    division_heads = [user for user in users if user.scope_level == "DIVISION_HEAD"]
    department_groups: list[dict] = []
    grouped_departments = {}
    for member in users:
        department_key = member.department_id or 0
        if department_key not in grouped_departments:
            grouped_departments[department_key] = {
                "department": member.department,
                "heads": [],
                "members": [],
            }
        if member.scope_level == "DEPARTMENT_HEAD":
            grouped_departments[department_key]["heads"].append(member)
        elif member.scope_level != "DIVISION_HEAD":
            grouped_departments[department_key]["members"].append(member)
    for bucket in grouped_departments.values():
        bucket["heads"] = sorted(
            bucket["heads"],
            key=lambda user: (0 if user.is_active else 1, -(user.designation.rank if user.designation else 0), user.full_name.lower()),
        )
        bucket["members"] = sorted(
            bucket["members"],
            key=lambda user: (0 if user.is_active else 1, -(user.designation.rank if user.designation else 0), user.full_name.lower()),
        )
        department_groups.append(bucket)
    department_groups.sort(key=lambda bucket: (bucket["department"].name.lower() if bucket["department"] else "zzzz"))
    return templates.TemplateResponse(
        "manager/team_members.html",
        build_context(
            request,
            current_user=current_user,
            db=db,
            members=users,
            scope_title=selected_department.name if selected_department else selected_division.name if selected_division else user_service.scope_label(current_user),
            selected_division=selected_division,
            selected_department=selected_department,
            selected_division_id=division_id,
            selected_department_id=department_id,
            division_heads=division_heads,
            department_groups=department_groups,
        ),
    )

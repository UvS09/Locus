from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db_session
from app.dependencies.role_dependencies import require_roles
from app.models.user import User
from app.routes.common import build_context, redirect_with_message, templates
from app.services.report_service import ReportService
from app.services.task_service import TaskService
from app.utils.enums import UserRole

router = APIRouter(prefix="/employee", tags=["employee"])


@router.get("/dashboard", response_class=HTMLResponse)
async def employee_dashboard(request: Request, current_user: User = Depends(require_roles(UserRole.EMPLOYEE)), db: Session = Depends(get_db_session)):
    stats = ReportService(db).employee_dashboard(current_user.id)
    return templates.TemplateResponse(
        "employee/dashboard.html",
        build_context(request, current_user=current_user, db=db, stats=stats),
    )


@router.get("/analytics", response_class=HTMLResponse)
async def employee_analytics(request: Request, current_user: User = Depends(require_roles(UserRole.EMPLOYEE)), db: Session = Depends(get_db_session)):
    stats = ReportService(db).employee_analytics(current_user.id)
    return templates.TemplateResponse(
        "employee/analytics.html",
        build_context(request, current_user=current_user, db=db, stats=stats),
    )


@router.get("/tasks", response_class=HTMLResponse)
async def employee_tasks(
    request: Request,
    status: str = Query(""),
    overdue: bool = Query(False),
    current_user: User = Depends(require_roles(UserRole.EMPLOYEE)),
    db: Session = Depends(get_db_session),
):
    tasks = TaskService(db).list_tasks_for_actor(current_user)
    tasks = [task for task in tasks if task.assigned_to_id == current_user.id]
    if status:
        tasks = [task for task in tasks if task.status.value == status]
    if overdue:
        tasks = [
            task for task in tasks
            if task.due_date and task.due_date < date.today() and task.status.value not in {"COMPLETED", "CLOSED"}
        ]
    return templates.TemplateResponse(
        "employee/tasks.html",
        build_context(
            request,
            current_user=current_user,
            db=db,
            tasks=tasks,
            selected_status=status,
            selected_overdue=overdue,
        ),
    )

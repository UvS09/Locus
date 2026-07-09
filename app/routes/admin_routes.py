import csv
from datetime import date
from io import StringIO

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db_session
from app.dependencies.role_dependencies import require_roles
from app.models.user import User
from app.routes.common import build_context, redirect_with_message, templates
from app.schemas.team import TeamCreate
from app.schemas.user import UserCreate, UserUpdate
from app.services.report_service import ReportService
from app.services.team_service import TeamService
from app.services.user_service import UserService
from app.utils.report_exports import (
    build_admin_report_pdf,
    build_admin_report_xlsx,
    build_audit_pdf,
    build_audit_xlsx,
)
from app.utils.security import clear_auth_cookie, create_access_token, set_auth_cookie
from app.utils.enums import UserRole
from app.utils.work_item_levels import WorkItemStatus

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()


def _optional_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _role_selection(value: str) -> tuple[UserRole, int | None]:
    if value.startswith("custom:"):
        return UserRole.EMPLOYEE, int(value.removeprefix("custom:"))
    return UserRole(value.removeprefix("system:")), None


def _role_options(user_service: UserService) -> list[dict]:
    options = [{"value": f"system:{role.value}", "label": role.value, "access_level": role.value} for role in UserRole]
    options.extend(
        {
            "value": f"custom:{role.id}",
            "label": role.name,
            "access_level": role.access_level.value,
        }
        for role in user_service.list_custom_roles()
    )
    return options


def _filter_workspace_items(items: list, *, q: str = "", status: str = "", team_id: int | None = None) -> list:
    filtered = items
    if q:
        query = q.strip().lower()
        filtered = [
            item for item in filtered
            if query in item.title.lower()
            or query in (item.description or "").lower()
            or query in (item.assignee.full_name.lower() if item.assignee else "")
            or query in (item.team.name.lower() if item.team else "")
        ]
    if status:
        filtered = [item for item in filtered if item.status.value == status]
    if team_id:
        filtered = [item for item in filtered if item.team_id == team_id]
    return filtered


def _filter_users(users: list, *, q: str = "", role: str = "", team_id: int | None = None, status: str = "") -> list:
    filtered = users
    if q:
        query = q.strip().lower()
        filtered = [
            user for user in filtered
            if query in user.full_name.lower()
            or query in user.email.lower()
            or query in user.display_role.lower()
        ]
    if role:
        filtered = [user for user in filtered if user.role.value == role]
    if team_id:
        filtered = [user for user in filtered if user.team_id == team_id]
    if status:
        is_active = status == "active"
        filtered = [user for user in filtered if user.is_active == is_active]
    return filtered


def _reporting_manager_options(user_service: UserService) -> list[User]:
    return [user for user in user_service.list_users() if user.role in {UserRole.ADMIN, UserRole.MANAGER}]


def _filter_audit_logs(logs: list, *, actor_id: int | None = None, action: str = "", entity: str = "", logged_on: str = "") -> list:
    filtered = logs
    if actor_id:
        filtered = [log for log in filtered if log.actor_user_id == actor_id]
    if action:
        filtered = [log for log in filtered if log.action == action]
    if entity:
        filtered = [log for log in filtered if log.entity_type == entity]
    if logged_on:
        filtered = [log for log in filtered if log.created_at.date().isoformat() == logged_on]
    return filtered


def _csv_response(rows: list[list], filename: str) -> Response:
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerows(rows)
    return Response(
        buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _report_export_rows(stats: dict) -> list[list]:
    rows = [
        ["Metric", "Value"],
        ["Objective completion", f'{stats["summary"]["objective_completion"]}%'],
        ["Workstream completion", f'{stats["summary"]["workstream_completion"]}%'],
        ["Activity completion", f'{stats["summary"]["activity_completion"]}%'],
        ["Task completion", f'{stats["summary"]["task_completion"]}%'],
        ["Portfolio progress", f'{stats["summary"]["portfolio_progress"]}%'],
        ["Overdue work", stats["summary"]["overdue_work"]],
        [],
        ["Employee productivity"],
        ["Employee", "Email", "Assigned", "Completed", "Overdue", "Avg Progress", "Completion Rate"],
    ]
    for row in stats["employee_productivity"]:
        rows.append([
            row["user"].full_name,
            row["user"].email,
            row["assigned"],
            row["completed"],
            row["overdue"],
            f'{row["avg_progress"]}%',
            f'{row["completion_rate"]}%',
        ])
    rows.extend([
        [],
        ["Manager productivity"],
        ["Manager", "Team", "Open Work", "Overdue", "Completion Rate"],
    ])
    for row in stats["manager_productivity"]:
        rows.append([
            row["user"].full_name,
            row["team_name"],
            row["open_work"],
            row["overdue"],
            f'{row["completion_rate"]}%',
        ])
    rows.extend([
        [],
        ["Team performance"],
        ["Team", "Active Members", "Objective Completion", "Task Completion", "Overdue"],
    ])
    for row in stats["team_performance"]:
        rows.append([
            row["team"].name,
            row["active_members"],
            f'{row["objective_completion"]}%',
            f'{row["task_completion"]}%',
            row["overdue"],
        ])
    return rows


def _audit_export_rows(logs: list) -> list[list]:
    rows = [["Timestamp", "Actor", "Action", "Entity", "Entity ID", "Details"]]
    for log in logs:
        rows.append([
            log.created_at.isoformat(),
            log.actor.full_name if log.actor else "System",
            log.action,
            log.entity_type,
            log.entity_id or "",
            str(log.details or {}),
        ])
    return rows


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request, current_user: User = Depends(require_roles(UserRole.ADMIN)), db: Session = Depends(get_db_session)):
    stats = ReportService(db).admin_dashboard()
    return templates.TemplateResponse("admin/dashboard.html", build_context(request, current_user=current_user, db=db, stats=stats))


@router.get("/workspace", response_class=HTMLResponse)
async def workspace_page(
    request: Request,
    q: str = Query(""),
    status: str = Query(""),
    team_id: int | None = Query(None),
    view: str = Query("table"),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
):
    stats = ReportService(db).admin_workspace()
    objectives = _filter_workspace_items(stats["objectives"], q=q, status=status, team_id=team_id)
    tasks = _filter_workspace_items(stats["tasks"], q=q, status=status, team_id=team_id)
    task_board = {status_key.value: [] for status_key in WorkItemStatus}
    for task in tasks:
        task_board[task.status.value].append(task)
    return templates.TemplateResponse(
        "admin/workspace.html",
        build_context(
            request,
            current_user=current_user,
            db=db,
            workspace=stats,
            objectives=objectives,
            task_board=task_board,
            q=q,
            selected_status=status,
            selected_team_id=team_id,
            view=view if view in {"table", "kanban"} else "table",
            work_item_statuses=list(WorkItemStatus),
        ),
    )


@router.get("/users", response_class=HTMLResponse)
async def users_page(
    request: Request,
    q: str = Query(""),
    role: str = Query(""),
    team_id: int | None = Query(None),
    status: str = Query(""),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
):
    user_service = UserService(db)
    team_service = TeamService(db)
    users = _filter_users(user_service.list_users(), q=q, role=role, team_id=team_id, status=status)
    return templates.TemplateResponse(
        "admin/users.html",
        build_context(
            request,
            current_user=current_user,
            db=db,
            users=users,
            teams=team_service.list_teams(),
            roles=list(UserRole),
            designations=user_service.list_designations(),
            divisions=user_service.list_divisions(),
            departments=user_service.list_departments(),
            reporting_managers=_reporting_manager_options(user_service),
            custom_roles=user_service.list_custom_roles(),
            role_options=_role_options(user_service),
            allow_impersonation=not settings.is_production,
            q=q,
            selected_role=role,
            selected_team_id=team_id,
            selected_status=status,
        ),
    )


@router.post("/users")
async def create_user(
    full_name: str = Form(...),
    email: str = Form(...),
    role_key: str = Form(...),
    team_id: str | None = Form(None),
    designation_id: str | None = Form(None),
    department_id: str | None = Form(None),
    division_id: str | None = Form(None),
    reports_to_user_id: str | None = Form(None),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
):
    user_service = UserService(db)
    try:
        role, custom_role_id = _role_selection(role_key)
        user, temp_password = user_service.create_user(
            current_user,
            UserCreate(
                full_name=full_name,
                email=email,
                role=role,
                custom_role_id=custom_role_id,
                team_id=_optional_int(team_id),
                designation_id=_optional_int(designation_id),
                department_id=_optional_int(department_id),
                division_id=_optional_int(division_id),
                reports_to_user_id=_optional_int(reports_to_user_id),
            ),
        )
        db.commit()
        return redirect_with_message("/admin/users", message=f"Created {user.email}. Temporary password: {temp_password}")
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/admin/users", error=str(exc))


@router.post("/users/{user_id}")
async def update_user(
    user_id: int,
    full_name: str = Form(...),
    email: str = Form(...),
    role_key: str = Form(...),
    team_id: str | None = Form(None),
    designation_id: str | None = Form(None),
    department_id: str | None = Form(None),
    division_id: str | None = Form(None),
    reports_to_user_id: str | None = Form(None),
    is_active: bool = Form(False),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
):
    user_service = UserService(db)
    try:
        role, custom_role_id = _role_selection(role_key)
        user_service.update_user(
            current_user,
            user_id,
            UserUpdate(
                full_name=full_name,
                email=email,
                role=role,
                custom_role_id=custom_role_id,
                team_id=_optional_int(team_id),
                designation_id=_optional_int(designation_id),
                department_id=_optional_int(department_id),
                division_id=_optional_int(division_id),
                reports_to_user_id=_optional_int(reports_to_user_id),
                is_active=is_active,
            ),
        )
        db.commit()
        return redirect_with_message("/admin/users", message="User updated.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/admin/users", error=str(exc))


@router.post("/roles")
async def create_role(
    name: str = Form(...),
    access_level: UserRole = Form(...),
    description: str | None = Form(None),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
):
    user_service = UserService(db)
    try:
        role = user_service.create_role(current_user, name=name, access_level=access_level, description=description)
        db.commit()
        return redirect_with_message("/admin/users", message=f"Role {role.name} created.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/admin/users", error=str(exc))


@router.post("/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: int,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
):
    user_service = UserService(db)
    try:
        user_service.deactivate_user(current_user, user_id)
        db.commit()
        return redirect_with_message("/admin/users", message="User deactivated.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/admin/users", error=str(exc))


@router.post("/users/{user_id}/delete")
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
):
    user_service = UserService(db)
    try:
        deleted_user = user_service.delete_user(current_user, user_id)
        db.commit()
        if deleted_user.id == current_user.id:
            response = redirect_with_message("/login", message="Admin account deleted.")
            clear_auth_cookie(response)
            return response
        return redirect_with_message("/admin/users", message="User deleted.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/admin/users", error=str(exc))


@router.get("/teams", response_class=HTMLResponse)
async def teams_page(request: Request, current_user: User = Depends(require_roles(UserRole.ADMIN)), db: Session = Depends(get_db_session)):
    team_service = TeamService(db)
    user_service = UserService(db)
    return templates.TemplateResponse(
        "admin/teams.html",
        build_context(
            request,
            current_user=current_user,
            db=db,
            divisions=user_service.list_divisions(),
            departments=user_service.list_departments(),
            teams=team_service.list_teams(),
            managers=user_service.list_managers(),
            employees=user_service.list_employees(),
        ),
    )


@router.get("/administration", response_class=HTMLResponse)
async def administration_page(request: Request, current_user: User = Depends(require_roles(UserRole.ADMIN)), db: Session = Depends(get_db_session)):
    return await teams_page(request=request, current_user=current_user, db=db)


@router.post("/teams")
async def create_team(
    name: str = Form(...),
    description: str | None = Form(None),
    department_id: str = Form(...),
    manager_id: str | None = Form(None),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
):
    team_service = TeamService(db)
    try:
        team_service.create_team(
            current_user,
            TeamCreate(name=name, description=description, manager_id=_optional_int(manager_id), department_id=int(department_id)),
        )
        db.commit()
        return redirect_with_message("/admin/administration", message="Team created.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/admin/administration", error=str(exc))


@router.post("/divisions")
async def create_division(
    name: str = Form(...),
    description: str | None = Form(None),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
):
    user_service = UserService(db)
    try:
        user_service.create_division(current_user, name=name, description=description)
        db.commit()
        return redirect_with_message("/admin/administration", message="Division created.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/admin/administration", error=str(exc))


@router.post("/divisions/{division_id}/delete")
async def delete_division(
    division_id: int,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
):
    user_service = UserService(db)
    try:
        user_service.delete_division(current_user, division_id)
        db.commit()
        return redirect_with_message("/admin/administration", message="Division deleted.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/admin/administration", error=str(exc))


@router.post("/departments")
async def create_department(
    name: str = Form(...),
    division_id: int = Form(...),
    description: str | None = Form(None),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
):
    user_service = UserService(db)
    try:
        user_service.create_department(current_user, name=name, division_id=division_id, description=description)
        db.commit()
        return redirect_with_message("/admin/administration", message="Department created.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/admin/administration", error=str(exc))


@router.post("/departments/{department_id}/delete")
async def delete_department(
    department_id: int,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
):
    user_service = UserService(db)
    try:
        user_service.delete_department(current_user, department_id)
        db.commit()
        return redirect_with_message("/admin/administration", message="Department deleted.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/admin/administration", error=str(exc))


@router.post("/organization/create")
async def create_organization_node(
    entity_type: str = Form(...),
    name: str = Form(...),
    description: str | None = Form(None),
    division_id: str | None = Form(None),
    department_id: str | None = Form(None),
    manager_id: str | None = Form(None),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
):
    user_service = UserService(db)
    team_service = TeamService(db)
    try:
        normalized = entity_type.strip().lower()
        if normalized == "division":
            user_service.create_division(current_user, name=name, description=description)
        elif normalized == "department":
            resolved_division_id = _optional_int(division_id)
            if resolved_division_id is None:
                raise ValueError("Select a division before creating a department.")
            user_service.create_department(current_user, name=name, division_id=resolved_division_id, description=description)
        elif normalized == "team":
            resolved_department_id = _optional_int(department_id)
            if resolved_department_id is None:
                raise ValueError("Select a department before creating a team.")
            team_service.create_team(
                current_user,
                TeamCreate(
                    name=name,
                    description=description,
                    department_id=resolved_department_id,
                    manager_id=_optional_int(manager_id),
                ),
            )
        else:
            raise ValueError("Invalid organization type selected.")
        db.commit()
        return redirect_with_message("/admin/administration", message=f"{normalized.title()} created.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/admin/administration", error=str(exc))


@router.post("/teams/{team_id}/delete")
async def delete_team(
    team_id: int,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
):
    team_service = TeamService(db)
    try:
        team_service.delete_team(current_user, team_id)
        db.commit()
        return redirect_with_message("/admin/administration", message="Team deleted.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/admin/administration", error=str(exc))


@router.post("/teams/{team_id}/assign-manager")
async def assign_manager(
    team_id: int,
    manager_id: int = Form(...),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
): 
    team_service = TeamService(db)
    try:
        team_service.assign_manager(current_user, team_id, manager_id)
        db.commit()
        return redirect_with_message("/admin/administration", message="Manager assigned.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/admin/administration", error=str(exc))


@router.post("/teams/{team_id}/assign-members")
async def assign_members(
    team_id: int,
    user_ids: list[int] = Form([]),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
):
    team_service = TeamService(db)
    try:
        team_service.assign_members(current_user, team_id, user_ids)
        db.commit()
        return redirect_with_message("/admin/administration", message="Team members assigned.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/admin/administration", error=str(exc))


@router.get("/audit-logs", response_class=HTMLResponse)
async def audit_logs_page(
    request: Request,
    actor_id: int | None = Query(None),
    action: str = Query(""),
    entity: str = Query(""),
    logged_on: str = Query(""),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
):
    stats = ReportService(db).admin_audit_logs()
    logs = _filter_audit_logs(stats["logs"], actor_id=actor_id, action=action, entity=entity, logged_on=logged_on)
    return templates.TemplateResponse(
        "admin/audit_logs.html",
        build_context(
            request,
            current_user=current_user,
            db=db,
            audit_logs=logs,
            actors=stats["actors"],
            actions=stats["actions"],
            entities=stats["entities"],
            selected_actor_id=actor_id,
            selected_action=action,
            selected_entity=entity,
            selected_logged_on=logged_on,
        ),
    )


@router.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request, current_user: User = Depends(require_roles(UserRole.ADMIN)), db: Session = Depends(get_db_session)):
    stats = ReportService(db).admin_reports()
    return templates.TemplateResponse(
        "admin/reports.html",
        build_context(request, current_user=current_user, db=db, stats=stats),
    )


@router.get("/reports/export")
async def export_reports(
    format: str = Query("xlsx"),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
):
    stats = ReportService(db).admin_reports()
    rows = _report_export_rows(stats)
    safe_format = format.lower()
    today_label = date.today().isoformat()
    if safe_format == "csv":
        return _csv_response(rows, f"admin-reports-{today_label}.csv")
    if safe_format == "pdf":
        return Response(
            build_admin_report_pdf(stats),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="admin-reports-{today_label}.pdf"'},
        )
    content = build_admin_report_xlsx(stats)
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="admin-reports-{today_label}.xlsx"'},
    )


@router.get("/audit-logs/export")
async def export_audit_logs(
    format: str = Query("xlsx"),
    actor_id: int | None = Query(None),
    action: str = Query(""),
    entity: str = Query(""),
    logged_on: str = Query(""),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
):
    stats = ReportService(db).admin_audit_logs()
    logs = _filter_audit_logs(stats["logs"], actor_id=actor_id, action=action, entity=entity, logged_on=logged_on)
    rows = _audit_export_rows(logs)
    safe_format = format.lower()
    today_label = date.today().isoformat()
    if safe_format == "csv":
        return _csv_response(rows, f"audit-logs-{today_label}.csv")
    if safe_format == "pdf":
        return Response(
            build_audit_pdf(logs),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="audit-logs-{today_label}.pdf"'},
        )
    content = build_audit_xlsx(logs)
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="audit-logs-{today_label}.xlsx"'},
    )


@router.post("/users/{user_id}/impersonate")
async def impersonate_user(
    user_id: int,
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
) -> RedirectResponse:
    if settings.is_production:
        return redirect_with_message("/admin/users", error="Impersonation is disabled in production.")

    target_user = UserService(db).get_user(user_id)
    token, expires_at = create_access_token(target_user.email, extra_claims={"role": target_user.role, "impersonated_by": current_user.email})
    response = redirect_with_message("/dashboard", message=f"Now acting as {target_user.full_name}.")
    set_auth_cookie(response, token, expires_at)
    return response

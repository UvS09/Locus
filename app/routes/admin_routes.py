from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
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
from app.utils.security import create_access_token, set_auth_cookie
from app.utils.enums import UserRole

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


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request, current_user: User = Depends(require_roles(UserRole.ADMIN)), db: Session = Depends(get_db_session)):
    stats = ReportService(db).admin_dashboard()
    return templates.TemplateResponse("admin/dashboard.html", build_context(request, current_user=current_user, db=db, stats=stats))


@router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, current_user: User = Depends(require_roles(UserRole.ADMIN)), db: Session = Depends(get_db_session)):
    user_service = UserService(db)
    team_service = TeamService(db)
    return templates.TemplateResponse(
        "admin/users.html",
        build_context(
            request,
            current_user=current_user,
            db=db,
            users=user_service.list_users(),
            teams=team_service.list_teams(),
            roles=list(UserRole),
            custom_roles=user_service.list_custom_roles(),
            role_options=_role_options(user_service),
            allow_impersonation=not settings.is_production,
        ),
    )


@router.post("/users")
async def create_user(
    full_name: str = Form(...),
    email: str = Form(...),
    role_key: str = Form(...),
    team_id: str | None = Form(None),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
):
    user_service = UserService(db)
    try:
        role, custom_role_id = _role_selection(role_key)
        user, temp_password = user_service.create_user(
            current_user,
            UserCreate(full_name=full_name, email=email, role=role, custom_role_id=custom_role_id, team_id=_optional_int(team_id)),
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
    role_key: str = Form(...),
    team_id: str | None = Form(None),
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
            UserUpdate(full_name=full_name, role=role, custom_role_id=custom_role_id, team_id=_optional_int(team_id), is_active=is_active),
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
            teams=team_service.list_teams(),
            managers=user_service.list_managers(),
            employees=user_service.list_employees(),
        ),
    )


@router.post("/teams")
async def create_team(
    name: str = Form(...),
    description: str | None = Form(None),
    manager_id: str | None = Form(None),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
    db: Session = Depends(get_db_session),
):
    team_service = TeamService(db)
    try:
        team_service.create_team(
            current_user,
            TeamCreate(name=name, description=description, manager_id=_optional_int(manager_id)),
        )
        db.commit()
        return redirect_with_message("/admin/teams", message="Team created.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/admin/teams", error=str(exc))


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
        return redirect_with_message("/admin/teams", message="Manager assigned.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/admin/teams", error=str(exc))


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
        return redirect_with_message("/admin/teams", message="Team members assigned.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/admin/teams", error=str(exc))


@router.get("/audit-logs", response_class=HTMLResponse)
async def audit_logs_page(request: Request, current_user: User = Depends(require_roles(UserRole.ADMIN)), db: Session = Depends(get_db_session)):
    stats = ReportService(db).admin_dashboard()
    return templates.TemplateResponse(
        "admin/audit_logs.html",
        build_context(request, current_user=current_user, db=db, audit_logs=stats["recent_audit_logs"]),
    )


@router.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request, current_user: User = Depends(require_roles(UserRole.ADMIN)), db: Session = Depends(get_db_session)):
    stats = ReportService(db).admin_dashboard()
    return templates.TemplateResponse(
        "admin/reports.html",
        build_context(request, current_user=current_user, db=db, stats=stats),
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

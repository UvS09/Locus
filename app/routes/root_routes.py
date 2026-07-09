from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db_session
from app.dependencies.auth_dependencies import get_current_user_optional
from app.models.user import User
from app.routes.common import build_context, redirect_with_message, templates
from app.utils.enums import UserRole

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User | None = Depends(get_current_user_optional),
) -> HTMLResponse:
    if current_user:
        return redirect_with_message("/dashboard")
    return redirect_with_message("/login")


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/dashboard")
async def dashboard(current_user: User | None = Depends(get_current_user_optional)):
    if current_user is None:
        return redirect_with_message("/login")
    if current_user.role == UserRole.ADMIN:
        return redirect_with_message("/admin/dashboard")
    if current_user.role == UserRole.MANAGER:
        return redirect_with_message("/manager/dashboard")
    return redirect_with_message("/employee/dashboard")

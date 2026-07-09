from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db_session
from app.dependencies.auth_dependencies import get_current_user
from app.models.user import User
from app.routes.common import build_context, redirect_with_message, templates
from app.schemas.auth import ChangePasswordRequest, LoginRequest
from app.services.auth_service import AuthService
from app.services.user_service import UserService
from app.utils.security import clear_auth_cookie, create_access_token, set_auth_cookie

router = APIRouter()
settings = get_settings()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db_session)) -> HTMLResponse:
    can_signup = not UserService(db).has_any_users()
    return templates.TemplateResponse("auth/login.html", build_context(request, db=db, can_signup=can_signup))


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    remember_me: bool = Form(False),
    db: Session = Depends(get_db_session),
):
    auth_service = AuthService(db)
    try:
        user = auth_service.authenticate(LoginRequest(email=email, password=password, remember_me=remember_me))
        token, expires_at = create_access_token(user.email, remember_me=remember_me, extra_claims={"role": user.role})
        redirect_url = "/change-password" if user.must_change_password else "/dashboard"
        response = RedirectResponse(redirect_url, status_code=303)
        set_auth_cookie(response, token, expires_at)
        db.commit()
        return response
    except Exception as exc:
        db.rollback()
        return templates.TemplateResponse(
            "auth/login.html",
            build_context(
                request,
                db=db,
                error=str(exc),
                form_email=email,
                can_signup=not UserService(db).has_any_users(),
            ),
            status_code=400,
        )


@router.post("/logout")
async def logout() -> RedirectResponse:
    response = redirect_with_message("/login", message="You have been logged out.")
    clear_auth_cookie(response)
    return response


@router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, db: Session = Depends(get_db_session)):
    can_signup = not UserService(db).has_any_users()
    if not can_signup:
        return redirect_with_message("/login", error="Signup is disabled. Use an existing account.")
    return templates.TemplateResponse("auth/signup.html", build_context(request, db=db, can_signup=can_signup))


@router.post("/signup")
async def signup(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db_session),
):
    user_service = UserService(db)
    try:
        user = user_service.bootstrap_admin(full_name=full_name, email=email, password=password)
        token, expires_at = create_access_token(user.email, extra_claims={"role": user.role})
        response = RedirectResponse("/dashboard", status_code=303)
        set_auth_cookie(response, token, expires_at)
        db.commit()
        return response
    except Exception as exc:
        db.rollback()
        return templates.TemplateResponse(
            "auth/signup.html",
            build_context(
                request,
                db=db,
                error=str(exc),
                can_signup=not user_service.has_any_users(),
                form_full_name=full_name,
                form_email=email,
            ),
            status_code=400,
        )


@router.get("/change-password", response_class=HTMLResponse)
async def change_password_page(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
    return templates.TemplateResponse("auth/settings.html", build_context(request, current_user=current_user, db=db))


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
    return templates.TemplateResponse("auth/settings.html", build_context(request, current_user=current_user, db=db))


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
    return templates.TemplateResponse("auth/profile.html", build_context(request, current_user=current_user, db=db))


@router.post("/profile")
async def update_profile(
    request: Request,
    full_name: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    name = full_name.strip()
    if len(name) < 2:
        return templates.TemplateResponse(
            "auth/profile.html",
            build_context(request, current_user=current_user, db=db, error="Full name must be at least 2 characters."),
            status_code=400,
        )
    current_user.full_name = name
    db.commit()
    return redirect_with_message("/profile", message="Profile updated.")


@router.post("/change-password")
async def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    auth_service = AuthService(db)
    try:
        auth_service.change_password(
            current_user,
            ChangePasswordRequest(current_password=current_password, new_password=new_password),
        )
        db.commit()
        return redirect_with_message("/settings", message="Password changed successfully.")
    except Exception as exc:
        db.rollback()
        return templates.TemplateResponse(
            "auth/settings.html",
            build_context(request, current_user=current_user, db=db, error=str(exc)),
            status_code=400,
        )

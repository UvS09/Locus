from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db_session
from app.dependencies.auth_dependencies import get_current_user, get_current_user_optional
from app.models.user import User
from app.routes.common import build_context, redirect_with_message, templates
from app.config import get_settings
from app.utils.enums import UserRole

router = APIRouter()
settings = get_settings()


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
async def dashboard(request: Request, current_user: User | None = Depends(get_current_user_optional)):
    if current_user is None:
        return redirect_with_message("/login")
    if request.cookies.get("locus_presentation_mode") == "on":
        return redirect_with_message("/presentation")
    if current_user.role == UserRole.ADMIN:
        return redirect_with_message("/admin/dashboard")
    if current_user.role == UserRole.MANAGER:
        return redirect_with_message("/manager/dashboard")
    return redirect_with_message("/employee/dashboard")


def _presentation_portfolio(current_user: User) -> dict:
    """Return deterministic demo data without touching persisted application data."""
    today = date.today()
    projects = [
        {
            "name": "Incident Response Automation",
            "code": "APP-RUN-01",
            "owner": current_user.full_name,
            "team": "Incident Management",
            "status": "IN PROGRESS",
            "status_key": "in_progress",
            "progress": 82,
            "due": today + timedelta(days=34),
            "milestones": [
                {"name": "Alert classification rules", "progress": 100, "status": "Complete"},
                {"name": "Auto-assignment workflow", "progress": 84, "status": "On track"},
                {"name": "Major incident integration", "progress": 62, "status": "On track"},
            ],
        },
        {
            "name": "Application Monitoring Consolidation",
            "code": "APP-RUN-02",
            "owner": "Sneha Rao",
            "team": "Monitoring & Observability",
            "status": "IN PROGRESS",
            "status_key": "in_progress",
            "progress": 74,
            "due": today + timedelta(days=58),
            "milestones": [
                {"name": "Application inventory mapping", "progress": 100, "status": "Complete"},
                {"name": "Unified dashboard rollout", "progress": 78, "status": "On track"},
                {"name": "Legacy tool retirement", "progress": 46, "status": "At risk"},
            ],
        },
        {
            "name": "Production Stability Improvement",
            "code": "APP-RUN-03",
            "owner": "Priya Menon",
            "team": "Application Support",
            "status": "AT RISK",
            "status_key": "blocked",
            "progress": 58,
            "due": today + timedelta(days=21),
            "milestones": [
                {"name": "Recurring incident analysis", "progress": 100, "status": "Complete"},
                {"name": "Top defect remediation", "progress": 55, "status": "Blocked"},
                {"name": "Stability validation", "progress": 31, "status": "At risk"},
            ],
        },
        {
            "name": "Patch Compliance & Remediation",
            "code": "APP-RUN-04",
            "owner": "Amit Kumar",
            "team": "Release & Change",
            "status": "IN PROGRESS",
            "status_key": "in_progress",
            "progress": 79,
            "due": today + timedelta(days=43),
            "milestones": [
                {"name": "Critical server patching", "progress": 94, "status": "On track"},
                {"name": "Middleware remediation", "progress": 81, "status": "On track"},
                {"name": "Compliance sign-off", "progress": 62, "status": "On track"},
            ],
        },
        {
            "name": "Disaster Recovery Readiness",
            "code": "APP-RUN-05",
            "owner": "Rahul Verma",
            "team": "Continuity Management",
            "status": "COMPLETED",
            "status_key": "completed",
            "progress": 100,
            "due": today - timedelta(days=8),
            "milestones": [
                {"name": "Recovery runbook review", "progress": 100, "status": "Complete"},
                {"name": "Business application drill", "progress": 100, "status": "Complete"},
                {"name": "Audit closure", "progress": 100, "status": "Complete"},
            ],
        },
        {
            "name": "Service Request Automation",
            "code": "APP-RUN-06",
            "owner": "Nitin Sharma",
            "team": "Service Operations",
            "status": "PLANNED",
            "status_key": "pending",
            "progress": 34,
            "due": today + timedelta(days=82),
            "milestones": [
                {"name": "Request catalogue review", "progress": 68, "status": "On track"},
                {"name": "Approval workflow build", "progress": 27, "status": "On track"},
                {"name": "Self-service rollout", "progress": 8, "status": "Planned"},
            ],
        },
    ]
    return {
        "projects": projects,
        "metrics": {"projects": 16, "milestones": 56, "completion": 94, "on_track": 15},
        "trend": [82, 84, 86, 88, 90, 92, 94],
        "trend_labels": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul"],
        "status_mix": [
            {"label": "On track", "value": 69, "color": "#7f0d1a"},
            {"label": "Attention", "value": 17, "color": "#b51f2f"},
            {"label": "Critical", "value": 6, "color": "#df4b59"},
            {"label": "Complete", "value": 8, "color": "#f2a3aa"},
        ],
        "workload": [
            {"team": "Application Support", "value": 82},
            {"team": "Incident Management", "value": 76},
            {"team": "Monitoring & Observability", "value": 69},
            {"team": "Release & Change", "value": 73},
            {"team": "Database Operations", "value": 64},
        ],
        "recent_wins": [
            "Priority-one incident volume reduced by 28%",
            "Quarterly disaster recovery drill completed",
            "Critical application patch compliance reached 96%",
        ],
        "people": [
            {"name": current_user.full_name, "initials": "".join(part[0] for part in current_user.full_name.split()[:2]), "role": current_user.display_designation, "team": "Application Run", "load": 72, "accent": "red"},
            {"name": "Priya Menon", "initials": "PM", "role": "Application Support Lead", "team": "Application Support", "load": 78, "accent": "red-2"},
            {"name": "Nitin Sharma", "initials": "NS", "role": "Service Operations Lead", "team": "Service Operations", "load": 69, "accent": "red-3"},
            {"name": "Rahul Verma", "initials": "RV", "role": "Problem Management Lead", "team": "Incident & Problem Management", "load": 74, "accent": "red-4"},
            {"name": "Sneha Rao", "initials": "SR", "role": "Monitoring Lead", "team": "Monitoring & Observability", "load": 66, "accent": "red-5"},
            {"name": "Amit Kumar", "initials": "AK", "role": "Release & Change Lead", "team": "Release & Change", "load": 71, "accent": "red-6"},
        ],
        "departments": [
            {"name": "Application Support", "projects": 5, "members": 18, "completion": 92},
            {"name": "Incident & Problem Management", "projects": 4, "members": 14, "completion": 88},
            {"name": "Monitoring & Observability", "projects": 4, "members": 12, "completion": 90},
            {"name": "Release & Change", "projects": 3, "members": 11, "completion": 95},
        ],
    }


@router.get("/presentation", response_class=HTMLResponse)
async def presentation_dashboard(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    if request.cookies.get("locus_presentation_mode") != "on":
        return redirect_with_message("/dashboard")
    return templates.TemplateResponse(
        "presentation/dashboard.html",
        build_context(
            request,
            current_user=current_user,
            db=db,
            demo=_presentation_portfolio(current_user),
        ),
    )


@router.post("/presentation-mode")
async def toggle_presentation_mode(
    enabled: str = Form("off"),
    current_user: User = Depends(get_current_user),
):
    is_enabled = enabled == "on"
    target = "/presentation" if is_enabled else "/dashboard"
    response = RedirectResponse(target, status_code=303)
    response.set_cookie(
        "locus_presentation_mode",
        "on" if is_enabled else "off",
        max_age=60 * 60 * 8 if is_enabled else 0,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
    )
    return response

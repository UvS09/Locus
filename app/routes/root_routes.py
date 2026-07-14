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
            "name": "EV Market Readiness Program",
            "code": "EV-2026",
            "description": "Coordinate launch readiness across product, service, and dealer operations.",
            "owner": current_user.full_name,
            "team": "EV Strategy Office",
            "status": "IN PROGRESS",
            "status_key": "in_progress",
            "progress": 78,
            "due": today + timedelta(days=34),
            "milestones": [
                {"name": "Dealer charging readiness", "progress": 84, "status": "On track"},
                {"name": "Service technician certification", "progress": 72, "status": "On track"},
                {"name": "Launch communications", "progress": 61, "status": "At risk"},
            ],
        },
        {
            "name": "Digital Dealer Experience",
            "code": "DDX-41",
            "description": "Unify online discovery, booking, finance, and delivery touchpoints.",
            "owner": "Aarav Mehta",
            "team": "Customer Experience",
            "status": "IN PROGRESS",
            "status_key": "in_progress",
            "progress": 64,
            "due": today + timedelta(days=58),
            "milestones": [
                {"name": "Journey research", "progress": 100, "status": "Complete"},
                {"name": "Unified booking pilot", "progress": 69, "status": "On track"},
                {"name": "Dealer rollout", "progress": 38, "status": "At risk"},
            ],
        },
        {
            "name": "Plant Energy Optimization",
            "code": "PEO-18",
            "description": "Reduce energy intensity through smart metering and operating controls.",
            "owner": "Kavya Iyer",
            "team": "Manufacturing Excellence",
            "status": "AT RISK",
            "status_key": "blocked",
            "progress": 47,
            "due": today + timedelta(days=21),
            "milestones": [
                {"name": "Metering baseline", "progress": 100, "status": "Complete"},
                {"name": "Peak-load automation", "progress": 44, "status": "Blocked"},
                {"name": "Savings validation", "progress": 18, "status": "At risk"},
            ],
        },
        {
            "name": "Supply Chain Control Tower",
            "code": "SCCT-09",
            "description": "Create early-warning visibility for critical parts and supplier risk.",
            "owner": "Rohan Kapoor",
            "team": "Supply Chain",
            "status": "IN PROGRESS",
            "status_key": "in_progress",
            "progress": 71,
            "due": today + timedelta(days=43),
            "milestones": [
                {"name": "Supplier data integration", "progress": 88, "status": "On track"},
                {"name": "Risk scoring model", "progress": 76, "status": "On track"},
                {"name": "Command centre pilot", "progress": 49, "status": "On track"},
            ],
        },
        {
            "name": "Connected Service Platform",
            "code": "CSP-23",
            "description": "Improve uptime with proactive service alerts and guided diagnostics.",
            "owner": "Meera Nair",
            "team": "After Sales",
            "status": "COMPLETED",
            "status_key": "completed",
            "progress": 100,
            "due": today - timedelta(days=8),
            "milestones": [
                {"name": "Diagnostics API", "progress": 100, "status": "Complete"},
                {"name": "Service advisor pilot", "progress": 100, "status": "Complete"},
                {"name": "Production rollout", "progress": 100, "status": "Complete"},
            ],
        },
        {
            "name": "Regional Safety Leadership",
            "code": "RSL-12",
            "description": "Scale proactive safety observation and rapid countermeasure practices.",
            "owner": "Dev Malhotra",
            "team": "People & Safety",
            "status": "PLANNED",
            "status_key": "pending",
            "progress": 26,
            "due": today + timedelta(days=82),
            "milestones": [
                {"name": "Leadership workshops", "progress": 52, "status": "On track"},
                {"name": "Observation rollout", "progress": 19, "status": "On track"},
                {"name": "Regional scorecards", "progress": 8, "status": "Planned"},
            ],
        },
    ]
    return {
        "projects": projects,
        "metrics": {"projects": 18, "milestones": 67, "completion": 72, "on_track": 14},
        "trend": [42, 48, 53, 57, 63, 68, 72],
        "trend_labels": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul"],
        "status_mix": [
            {"label": "On track", "value": 61, "color": "#22a06b"},
            {"label": "At risk", "value": 22, "color": "#f0a12b"},
            {"label": "Blocked", "value": 9, "color": "#d94a4a"},
            {"label": "Complete", "value": 8, "color": "#315bd6"},
        ],
        "workload": [
            {"team": "EV Strategy", "value": 86},
            {"team": "Customer Experience", "value": 74},
            {"team": "Manufacturing", "value": 68},
            {"team": "Supply Chain", "value": 81},
            {"team": "After Sales", "value": 59},
        ],
        "recent_wins": [
            "Connected Service Platform moved to production",
            "Supplier risk model reached 92% validation accuracy",
            "124 service technicians completed EV certification",
        ],
        "people": [
            {"name": current_user.full_name, "initials": "".join(part[0] for part in current_user.full_name.split()[:2]), "role": current_user.display_designation, "team": "Portfolio Leadership", "load": 72, "accent": "red"},
            {"name": "Aarav Mehta", "initials": "AM", "role": "Program Manager", "team": "Customer Experience", "load": 68, "accent": "blue"},
            {"name": "Kavya Iyer", "initials": "KI", "role": "Plant Transformation Lead", "team": "Manufacturing Excellence", "load": 81, "accent": "orange"},
            {"name": "Rohan Kapoor", "initials": "RK", "role": "Supply Chain Lead", "team": "Supply Chain", "load": 76, "accent": "violet"},
            {"name": "Meera Nair", "initials": "MN", "role": "Service Product Owner", "team": "After Sales", "load": 59, "accent": "green"},
            {"name": "Dev Malhotra", "initials": "DM", "role": "Regional Safety Lead", "team": "People & Safety", "load": 64, "accent": "cyan"},
        ],
        "departments": [
            {"name": "Customer Experience", "projects": 5, "members": 18, "completion": 76},
            {"name": "Manufacturing Excellence", "projects": 4, "members": 24, "completion": 68},
            {"name": "Supply Chain", "projects": 4, "members": 16, "completion": 71},
            {"name": "After Sales", "projects": 3, "members": 21, "completion": 83},
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

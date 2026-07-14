from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.models.user import User
from app.services.notification_service import NotificationService
from app.utils.work_item_levels import WorkItemLevel

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _format_long_date(value: date | datetime | None) -> str:
    if value is None:
        return "-"
    return f"{value.day} {value.strftime('%B')} {value.year}"


def _format_long_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    return f"{_format_long_date(value)}, {value.strftime('%H:%M')}"


templates.env.filters["long_date"] = _format_long_date
templates.env.filters["long_datetime"] = _format_long_datetime

DETAIL_PATHS = {
    WorkItemLevel.OBJECTIVE: "/objectives/{id}",
    WorkItemLevel.WORKSTREAM: "/workstreams/{id}",
    WorkItemLevel.ACTIVITY: "/activities/{id}",
    WorkItemLevel.TASK: "/tasks/{id}",
    WorkItemLevel.SUB_TASK: "/tasks/{id}",
}


def build_context(
    request: Request,
    *,
    current_user: User | None = None,
    db: Session | None = None,
    **extra,
) -> dict:
    unread_count = 0
    notifications = []
    if current_user and db:
        notification_service = NotificationService(db)
        unread_count = notification_service.unread_count(current_user)
        notifications = notification_service.list_for_user(current_user, limit=5)
    create_levels = []
    if current_user:
        if current_user.role == "MANAGER":
            create_levels = ["OBJECTIVE", "WORKSTREAM", "ACTIVITY", "TASK"]
    return {
        "request": request,
        "current_user": current_user,
        "presentation_mode": request.cookies.get("locus_presentation_mode") == "on",
        "unread_count": unread_count,
        "nav_notifications": notifications,
        "today": date.today(),
        "global_create_levels": create_levels,
        "detail_paths": DETAIL_PATHS,
        **extra,
    }


def redirect_with_message(url: str, *, message: str | None = None, error: str | None = None, status_code: int = 303) -> RedirectResponse:
    params = {}
    if message:
        params["message"] = message
    if error:
        params["error"] = error
    if not params:
        return RedirectResponse(url, status_code=status_code)
    split = urlsplit(url)
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    query.update(params)
    target = urlunsplit((split.scheme, split.netloc, split.path, urlencode(query), split.fragment))
    return RedirectResponse(target, status_code=status_code)

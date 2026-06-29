from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db_session
from app.dependencies.auth_dependencies import get_current_user
from app.models.user import User
from app.routes.common import build_context, redirect_with_message, templates
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_class=HTMLResponse)
async def notifications_page(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
    notification_service = NotificationService(db)
    notifications = notification_service.list_for_user(current_user)
    return templates.TemplateResponse(
        "shared/notifications.html",
        build_context(request, current_user=current_user, db=db, notifications=notifications),
    )


@router.post("/{notification_id}/read")
async def mark_read(notification_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
    service = NotificationService(db)
    try:
        service.mark_read(current_user, notification_id)
        db.commit()
        return redirect_with_message("/notifications", message="Notification marked as read.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/notifications", error=str(exc))


@router.post("/read-all")
async def mark_all_read(current_user: User = Depends(get_current_user), db: Session = Depends(get_db_session)):
    service = NotificationService(db)
    service.mark_all_read(current_user)
    db.commit()
    return redirect_with_message("/notifications", message="All notifications marked as read.")

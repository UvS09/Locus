from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from app.database import get_db_session
from app.dependencies.auth_dependencies import get_current_user
from app.models.user import User
from app.routes.common import redirect_with_message
from app.schemas.comment import CommentCreate
from app.schemas.work_item import WorkItemCreate
from app.services.comment_service import CommentService
from app.services.task_service import TaskService
from app.utils.enums import UserRole
from app.utils.work_item_levels import WorkItemLevel

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("/{task_id}/comments")
async def add_comment(
    request: Request,
    task_id: int,
    content: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    comment_service = CommentService(db)
    try:
        comment_service.add_comment(current_user, task_id, CommentCreate(content=content))
        db.commit()
        target = request.headers.get("referer") or "/dashboard"
        return redirect_with_message(target, message="Comment added.")
    except Exception as exc:
        db.rollback()
        target = request.headers.get("referer") or "/dashboard"
        return redirect_with_message(target, error=str(exc))


@router.post("/{task_id}/subtasks")
async def add_subtask(
    request: Request,
    task_id: int,
    title: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    task_service = TaskService(db)
    try:
        task_service.create_task(current_user, WorkItemCreate(level=WorkItemLevel.SUB_TASK, title=title, parent_id=task_id))
        db.commit()
        target = request.headers.get("referer") or f"/tasks/{task_id}"
        return redirect_with_message(target, message="Subtask added.")
    except Exception as exc:
        db.rollback()
        target = request.headers.get("referer") or f"/tasks/{task_id}"
        return redirect_with_message(target, error=str(exc))


@router.post("/{task_id}/subtasks/{subtask_id}/toggle")
async def toggle_subtask(
    request: Request,
    task_id: int,
    subtask_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    task_service = TaskService(db)
    try:
        task_service.toggle_subtask(current_user, task_id, subtask_id)
        db.commit()
        target = request.headers.get("referer") or f"/tasks/{task_id}"
        return redirect_with_message(target, message="Subtask updated.")
    except Exception as exc:
        db.rollback()
        target = request.headers.get("referer") or f"/tasks/{task_id}"
        return redirect_with_message(target, error=str(exc))

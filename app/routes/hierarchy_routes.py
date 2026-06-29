from collections import defaultdict

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database import get_db_session
from app.dependencies.auth_dependencies import get_current_user
from app.models.user import User
from app.routes.common import build_context, redirect_with_message, templates
from app.schemas.work_item import WorkItemCreate, WorkItemUpdate
from app.services.audit_service import AuditService
from app.services.task_service import TaskService
from app.services.user_service import UserService
from app.utils.enums import TaskPriority, UserRole
from app.utils.work_item_levels import WorkItemLevel, WorkItemStatus

router = APIRouter(tags=["hierarchy"])

_LEVEL_TITLE = {
    WorkItemLevel.OBJECTIVE: "Project",
    WorkItemLevel.WORKSTREAM: "Milestone",
    WorkItemLevel.ACTIVITY: "Activity",
    WorkItemLevel.TASK: "Task",
    WorkItemLevel.SUB_TASK: "Sub-task",
}

_DETAIL_PATH = {
    WorkItemLevel.OBJECTIVE: "/objectives/{id}",
    WorkItemLevel.WORKSTREAM: "/workstreams/{id}",
    WorkItemLevel.ACTIVITY: "/activities/{id}",
    WorkItemLevel.TASK: "/tasks/{id}",
    WorkItemLevel.SUB_TASK: "/tasks/{id}",
}

_BOARD_COLUMNS = ["PENDING", "IN_PROGRESS", "BLOCKED", "COMPLETED", "CLOSED"]
_BOARD_LABELS = {
    "PENDING": "TO_DO",
    "IN_PROGRESS": "IN_PROGRESS",
    "BLOCKED": "BLOCKED",
    "COMPLETED": "COMPLETED",
    "CLOSED": "CLOSED",
}


def _item_link(item) -> str:
    if item.level == WorkItemLevel.SUB_TASK:
        return f"/tasks/{item.parent_id}"
    return _DETAIL_PATH[item.level].format(id=item.id)


def _create_redirect(level: WorkItemLevel, parent_id: int | None = None) -> str:
    if level == WorkItemLevel.OBJECTIVE:
        return "/objectives"
    if level == WorkItemLevel.WORKSTREAM and parent_id:
        return f"/objectives/{parent_id}"
    if level == WorkItemLevel.ACTIVITY and parent_id:
        return f"/workstreams/{parent_id}"
    if level == WorkItemLevel.TASK and parent_id:
        return f"/activities/{parent_id}"
    return f"/tasks/{parent_id}" if parent_id else "/dashboard"


def _build_board(items: list) -> dict[str, list]:
    board = defaultdict(list)
    for item in items:
        board[getattr(item.status, "value", str(item.status))].append(item)
    return {status: board.get(status, []) for status in _BOARD_COLUMNS}


def _build_milestone_board(items: list) -> dict[str, list]:
    board = {status: [] for status in ["PENDING", "IN_PROGRESS", "BLOCKED", "COMPLETED"]}
    for item in items:
        status = getattr(item.status, "value", str(item.status))
        if status == "CLOSED":
            board["COMPLETED"].append(item)
        elif status in board:
            board[status].append(item)
    return board


def _team_members(current_user: User, user_service: UserService) -> list[User]:
    if current_user.role == UserRole.ADMIN:
        return user_service.list_users()
    if current_user.team_id:
        return user_service.list_team_members(current_user.team_id)
    return []


def _filter_items(items: list, *, q: str = "", status: str = "", owner: str = "") -> list:
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
        filtered = [item for item in filtered if getattr(item.status, "value", str(item.status)) == status]
    return filtered


def _build_common_context(
    request: Request,
    db: Session,
    current_user: User,
    **extra,
) -> dict:
    return build_context(
        request,
        current_user=current_user,
        db=db,
        priorities=list(TaskPriority),
        work_item_statuses=list(WorkItemStatus),
        level_titles=_LEVEL_TITLE,
        detail_paths=_DETAIL_PATH,
        board_columns=_BOARD_COLUMNS,
        board_labels=_BOARD_LABELS,
        **extra,
    )


@router.get("/create", response_class=HTMLResponse)
async def create_work_item_page(
    request: Request,
    level: WorkItemLevel = Query(WorkItemLevel.TASK),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    service = TaskService(db)
    if current_user.role == UserRole.ADMIN:
        return redirect_with_message("/dashboard", error="Admins cannot create delivery work items.")
    if current_user.role == UserRole.EMPLOYEE:
        return redirect_with_message("/objectives", error="Create work from its project, milestone, or activity page.")
    if current_user.role == UserRole.EMPLOYEE and level == WorkItemLevel.OBJECTIVE:
        return redirect_with_message("/objectives", error="Employees cannot create projects.")
    return templates.TemplateResponse(
        "hierarchy/create.html",
        _build_common_context(
            request,
            db,
            current_user,
            selected_level=level,
            create_levels=[
                item for item in WorkItemLevel
                if item != WorkItemLevel.SUB_TASK
                and not (current_user.role == UserRole.EMPLOYEE and item == WorkItemLevel.OBJECTIVE)
            ],
            objectives=service.list_by_level(current_user, level=WorkItemLevel.OBJECTIVE),
            workstreams=service.list_by_level(current_user, level=WorkItemLevel.WORKSTREAM),
            activities=service.list_by_level(current_user, level=WorkItemLevel.ACTIVITY),
            tasks=service.list_by_level(current_user, level=WorkItemLevel.TASK),
            employees=_team_members(current_user, UserService(db)),
        ),
    )


@router.post("/create")
async def create_work_item_from_hub(
    level: WorkItemLevel = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    priority: TaskPriority = Form(TaskPriority.MEDIUM),
    due_date: str | None = Form(None),
    objective_id: str | None = Form(None),
    workstream_id: str | None = Form(None),
    activity_id: str | None = Form(None),
    task_parent_id: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    if current_user.role == UserRole.EMPLOYEE:
        return redirect_with_message("/objectives", error="Create work from its project, milestone, or activity page.")
    parent_lookup = {
        WorkItemLevel.WORKSTREAM: objective_id,
        WorkItemLevel.ACTIVITY: workstream_id,
        WorkItemLevel.TASK: activity_id,
        WorkItemLevel.SUB_TASK: task_parent_id,
    }
    parent_id = parent_lookup.get(level)
    service = TaskService(db)
    try:
        created_item = service.create_work_item(
            current_user,
            WorkItemCreate(
                level=level,
                title=title,
                description=description,
                priority=priority,
                due_date=due_date or None,
                parent_id=int(parent_id) if parent_id else None,
            ),
        )
        db.commit()
        return redirect_with_message(_item_link(created_item), message=f"{_LEVEL_TITLE[level]} created.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message(f"/create?level={level.value}", error=str(exc))


@router.get("/objectives", response_class=HTMLResponse)
async def objectives_page(
    request: Request,
    q: str = Query(""),
    status: str = Query(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    service = TaskService(db)
    objectives = _filter_items(service.list_by_level(current_user, level=WorkItemLevel.OBJECTIVE), q=q, status=status)
    return templates.TemplateResponse(
        "hierarchy/objectives.html",
        _build_common_context(
            request,
            db,
            current_user,
            objectives=objectives,
            create_allowed=current_user.role == UserRole.MANAGER,
            q=q,
            selected_status=status,
        ),
    )


@router.post("/objectives")
async def create_objective(
    title: str = Form(...),
    description: str = Form(""),
    priority: TaskPriority = Form(TaskPriority.MEDIUM),
    due_date: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    service = TaskService(db)
    try:
        service.create_work_item(
            current_user,
            WorkItemCreate(
                level=WorkItemLevel.OBJECTIVE,
                title=title,
                description=description,
                priority=priority,
                due_date=due_date or None,
            ),
        )
        db.commit()
        return redirect_with_message("/objectives", message="Project created.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/objectives", error=str(exc))


@router.get("/objectives/{objective_id}", response_class=HTMLResponse)
async def objective_detail(
    objective_id: int,
    request: Request,
    view: str = Query("table"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    service = TaskService(db)
    objective = service.get_accessible_work_item(current_user, objective_id)
    workstreams = service.list_by_level(current_user, level=WorkItemLevel.WORKSTREAM, parent_id=objective.id)
    workstream_ids = {item.id for item in workstreams}
    project_activities = [
        item for item in service.list_by_level(current_user, level=WorkItemLevel.ACTIVITY)
        if item.parent_id in workstream_ids
    ]
    audit_logs = AuditService(db).list_recent(limit=40)
    return templates.TemplateResponse(
        "hierarchy/detail.html",
        _build_common_context(
            request,
            db,
            current_user,
            item=objective,
            children=workstreams,
            child_board=_build_milestone_board(workstreams),
            child_view_mode="board" if view == "board" and current_user.role == UserRole.MANAGER else "table",
            breadcrumb=service.breadcrumb(objective),
            child_level=WorkItemLevel.WORKSTREAM,
            child_title="Milestones",
            create_action=f"/objectives/{objective.id}/workstreams",
            project_milestones=workstreams,
            project_activities=project_activities,
            create_allowed=current_user.role in {UserRole.MANAGER, UserRole.EMPLOYEE},
            employees=_team_members(current_user, UserService(db)),
            can_edit=service.can_edit_work_item(current_user, objective),
            can_delete=service.can_delete_work_item_tree(current_user, objective),
            audit_logs=[
                log for log in audit_logs
                if log.entity_id == objective.id or (log.details and log.details.get("parent_id") == objective.id)
            ],
        ),
    )


@router.post("/objectives/{objective_id}/create")
async def create_inside_project(
    objective_id: int,
    level: WorkItemLevel = Form(...),
    parent_id: str | None = Form(None),
    milestone_id: str | None = Form(None),
    title: str = Form(...),
    description: str = Form(""),
    priority: TaskPriority = Form(TaskPriority.MEDIUM),
    due_date: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    service = TaskService(db)
    try:
        project = service.get_accessible_work_item(current_user, objective_id)
        if project.level != WorkItemLevel.OBJECTIVE:
            raise ValueError("Project not found.")
        if level not in {WorkItemLevel.WORKSTREAM, WorkItemLevel.ACTIVITY, WorkItemLevel.TASK}:
            raise ValueError("Choose Milestone, Activity, or Task.")

        resolved_parent_id = objective_id if level == WorkItemLevel.WORKSTREAM else int(parent_id or 0)
        general_milestone = None
        if level in {WorkItemLevel.ACTIVITY, WorkItemLevel.TASK} and not resolved_parent_id and not milestone_id:
            general_milestone = next(
                (milestone for milestone in service.list_by_level(
                    current_user,
                    level=WorkItemLevel.WORKSTREAM,
                    parent_id=objective_id,
                ) if milestone.title == "General"),
                None,
            )
            if general_milestone is None:
                general_milestone = service.create_work_item(
                    current_user,
                    WorkItemCreate(
                        level=WorkItemLevel.WORKSTREAM,
                        title="General",
                        description="General delivery work for this project.",
                        priority=priority,
                        due_date=due_date or None,
                        parent_id=objective_id,
                    ),
                )
        if level == WorkItemLevel.ACTIVITY and not resolved_parent_id:
            resolved_parent_id = general_milestone.id
        if level == WorkItemLevel.TASK and not resolved_parent_id:
            selected_milestone = (
                service.get_accessible_work_item(current_user, int(milestone_id))
                if milestone_id
                else general_milestone
            )
            if selected_milestone.level != WorkItemLevel.WORKSTREAM or selected_milestone.parent_id != objective_id:
                raise ValueError("Select a milestone from this project.")
            general_activity = next(
                (
                    activity for activity in service.list_by_level(
                        current_user,
                        level=WorkItemLevel.ACTIVITY,
                        parent_id=selected_milestone.id,
                    )
                    if activity.title == "General Tasks"
                ),
                None,
            )
            if general_activity is None:
                general_activity = service.create_work_item(
                    current_user,
                    WorkItemCreate(
                        level=WorkItemLevel.ACTIVITY,
                        title="General Tasks",
                        description="Tasks created directly from the project.",
                        priority=priority,
                        due_date=due_date or None,
                        parent_id=selected_milestone.id,
                    ),
                )
            resolved_parent_id = general_activity.id
        parent = service.get_accessible_work_item(current_user, resolved_parent_id)
        chain_ids = {item.id for item in service.breadcrumb(parent)}
        if objective_id not in chain_ids:
            raise ValueError("The selected parent must belong to this project.")

        service.create_work_item(
            current_user,
            WorkItemCreate(
                level=level,
                title=title,
                description=description,
                priority=priority,
                due_date=due_date or None,
                parent_id=resolved_parent_id,
            ),
        )
        db.commit()
        return redirect_with_message(f"/objectives/{objective_id}", message=f"{_LEVEL_TITLE[level]} created.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message(f"/objectives/{objective_id}", error=str(exc))


@router.post("/objectives/{objective_id}/workstreams")
async def create_workstream(
    objective_id: int,
    title: str = Form(...),
    description: str = Form(""),
    priority: TaskPriority = Form(TaskPriority.MEDIUM),
    due_date: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    service = TaskService(db)
    try:
        service.create_work_item(
            current_user,
            WorkItemCreate(
                level=WorkItemLevel.WORKSTREAM,
                title=title,
                description=description,
                priority=priority,
                due_date=due_date or None,
                parent_id=objective_id,
            ),
        )
        db.commit()
        return redirect_with_message(f"/objectives/{objective_id}", message="Milestone created.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message(f"/objectives/{objective_id}", error=str(exc))


@router.get("/workstreams/{workstream_id}", response_class=HTMLResponse)
async def workstream_detail(
    workstream_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    service = TaskService(db)
    workstream = service.get_accessible_work_item(current_user, workstream_id)
    activities = service.list_by_level(current_user, level=WorkItemLevel.ACTIVITY, parent_id=workstream.id)
    audit_logs = AuditService(db).list_recent(limit=40)
    return templates.TemplateResponse(
        "hierarchy/detail.html",
        _build_common_context(
            request,
            db,
            current_user,
            item=workstream,
            children=activities,
            breadcrumb=service.breadcrumb(workstream),
            child_level=WorkItemLevel.ACTIVITY,
            child_title="Activities",
            create_action=f"/workstreams/{workstream.id}/activities",
            create_allowed=current_user.role in {UserRole.MANAGER, UserRole.EMPLOYEE},
            employees=_team_members(current_user, UserService(db)),
            can_edit=service.can_edit_work_item(current_user, workstream),
            can_delete=service.can_delete_work_item_tree(current_user, workstream),
            audit_logs=[
                log for log in audit_logs
                if log.entity_id == workstream.id or (log.details and log.details.get("parent_id") == workstream.id)
            ],
        ),
    )


@router.post("/workstreams/{workstream_id}/activities")
async def create_activity(
    workstream_id: int,
    title: str = Form(...),
    description: str = Form(""),
    priority: TaskPriority = Form(TaskPriority.MEDIUM),
    due_date: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    service = TaskService(db)
    try:
        service.create_work_item(
            current_user,
            WorkItemCreate(
                level=WorkItemLevel.ACTIVITY,
                title=title,
                description=description,
                priority=priority,
                due_date=due_date or None,
                parent_id=workstream_id,
            ),
        )
        db.commit()
        return redirect_with_message(f"/workstreams/{workstream_id}", message="Activity created.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message(f"/workstreams/{workstream_id}", error=str(exc))


@router.get("/activities/{activity_id}", response_class=HTMLResponse)
async def activity_detail(
    activity_id: int,
    request: Request,
    view: str = Query("table"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    service = TaskService(db)
    activity = service.get_accessible_work_item(current_user, activity_id)
    tasks = service.list_by_level(current_user, level=WorkItemLevel.TASK, parent_id=activity.id)
    audit_logs = AuditService(db).list_recent(limit=40)
    return templates.TemplateResponse(
        "hierarchy/activity_board.html",
        _build_common_context(
            request,
            db,
            current_user,
            item=activity,
            tasks=tasks,
            task_board=_build_board(tasks),
            view_mode="board" if view == "board" else "table",
            breadcrumb=service.breadcrumb(activity),
            create_allowed=current_user.role in {UserRole.MANAGER, UserRole.EMPLOYEE},
            employees=_team_members(current_user, UserService(db)),
            can_edit=service.can_edit_work_item(current_user, activity),
            can_delete=service.can_delete_work_item_tree(current_user, activity),
            audit_logs=[
                log for log in audit_logs
                if log.entity_id == activity.id or (log.details and log.details.get("parent_id") == activity.id)
            ],
        ),
    )


@router.post("/activities/{activity_id}/tasks")
async def create_activity_task(
    activity_id: int,
    title: str = Form(...),
    description: str = Form(""),
    priority: TaskPriority = Form(TaskPriority.MEDIUM),
    due_date: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    service = TaskService(db)
    try:
        service.create_work_item(
            current_user,
            WorkItemCreate(
                level=WorkItemLevel.TASK,
                title=title,
                description=description,
                priority=priority,
                due_date=due_date or None,
                parent_id=activity_id,
            ),
        )
        db.commit()
        return redirect_with_message(f"/activities/{activity_id}", message="Task created.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message(f"/activities/{activity_id}", error=str(exc))


@router.get("/tasks/{task_id}", response_class=HTMLResponse)
async def task_detail_page(
    task_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    service = TaskService(db)
    task = service.get_accessible_work_item(current_user, task_id)
    audit_logs = AuditService(db).list_recent(limit=80)
    item_logs = [log for log in audit_logs if log.entity_id == task.id]
    comment_logs = [log for log in item_logs if log.action == "task_comment_added"]
    return templates.TemplateResponse(
        "hierarchy/task_detail.html",
        _build_common_context(
            request,
            db,
            current_user,
            item=task,
            breadcrumb=service.breadcrumb(task),
            employees=_team_members(current_user, UserService(db)),
            can_edit=service.can_edit_work_item(current_user, task),
            can_delete=service.can_delete_work_item_tree(current_user, task),
            audit_logs=item_logs,
            comment_logs=comment_logs,
        ),
    )


@router.post("/tasks/{task_id}/work-item")
async def update_work_item(
    task_id: int,
    title: str = Form(...),
    description: str = Form(""),
    priority: TaskPriority = Form(TaskPriority.MEDIUM),
    status: WorkItemStatus = Form(WorkItemStatus.PENDING),
    due_date: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    service = TaskService(db)
    item = service.get_accessible_work_item(current_user, task_id)
    try:
        service.update_work_item(
            current_user,
            task_id,
            WorkItemUpdate(
                title=title,
                description=description,
                priority=priority,
                status=status,
                due_date=due_date or None,
            ),
        )
        db.commit()
        return redirect_with_message(_item_link(item), message=f"{_LEVEL_TITLE[item.level]} updated.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message(_item_link(item), error=str(exc))


@router.post("/tasks/{task_id}/close-work-item")
async def close_work_item_route(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    service = TaskService(db)
    item = service.get_accessible_work_item(current_user, task_id)
    try:
        service.close_work_item(current_user, task_id)
        db.commit()
        return redirect_with_message(_item_link(item), message=f"{_LEVEL_TITLE[item.level]} closed.")
    except Exception as exc:
        db.rollback()
        return redirect_with_message(_item_link(item), error=str(exc))


@router.post("/work-items/{work_item_id}/delete")
async def delete_work_item_route(
    work_item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    service = TaskService(db)
    try:
        level, parent_id, title = service.delete_work_item(current_user, work_item_id)
        db.commit()
        return redirect_with_message(
            _create_redirect(level, parent_id),
            message=f'{_LEVEL_TITLE[level]} "{title}" deleted.',
        )
    except Exception as exc:
        db.rollback()
        return redirect_with_message("/dashboard", error=str(exc))


@router.get("/subtasks", response_class=HTMLResponse)
async def subtask_list_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    service = TaskService(db)
    subtasks = service.list_by_level(current_user, level=WorkItemLevel.SUB_TASK)
    return templates.TemplateResponse(
        "hierarchy/subtasks.html",
        _build_common_context(
            request,
            db,
            current_user,
            subtasks=subtasks,
        ),
    )

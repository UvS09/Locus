from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""


engine = create_engine(
    settings.database_url,
    echo=settings.app_debug,
    future=True,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    class_=Session,
)


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _ensure_column(connection, inspector, table_name: str, column_name: str, ddl: str) -> bool:
    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    if column_name in existing_columns:
        return False
    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {ddl}"))
    return True


def init_db() -> None:
    from app.models import audit_log, comment, department, designation, division, notification, role, subtask, task, team, user, work_item  # noqa: F401
    from app.models.department import Department
    from app.models.designation import Designation
    from app.models.division import Division
    from app.models.team import Team
    from app.models.user import User
    from app.services.work_item_service import WorkItemService
    from app.models.work_item import WorkItem
    from app.utils.enums import DesignationScope, UserRole
    from app.utils.work_item_levels import WorkItemStatus

    Base.metadata.create_all(bind=engine)
    hierarchy_columns_added = False
    inspector = inspect(engine)
    with engine.begin() as connection:
        if "users" in inspector.get_table_names():
            hierarchy_columns_added |= _ensure_column(connection, inspector, "users", "custom_role_id", "custom_role_id INTEGER")
            hierarchy_columns_added |= _ensure_column(connection, inspector, "users", "designation_id", "designation_id INTEGER")
            hierarchy_columns_added |= _ensure_column(connection, inspector, "users", "department_id", "department_id INTEGER")
            hierarchy_columns_added |= _ensure_column(connection, inspector, "users", "division_id", "division_id INTEGER")
            hierarchy_columns_added |= _ensure_column(connection, inspector, "users", "reports_to_user_id", "reports_to_user_id INTEGER")
            hierarchy_columns_added |= _ensure_column(connection, inspector, "users", "manager_chain", "manager_chain TEXT")
            hierarchy_columns_added |= _ensure_column(connection, inspector, "users", "is_protected", "is_protected BOOLEAN NOT NULL DEFAULT 0")
        inspector = inspect(connection)
        if "teams" in inspector.get_table_names():
            hierarchy_columns_added |= _ensure_column(connection, inspector, "teams", "department_id", "department_id INTEGER")
    with SessionLocal.begin() as session:
        enterprise_division = session.query(Division).filter(Division.name == "Enterprise").one_or_none()
        if enterprise_division is None:
            enterprise_division = Division(name="Enterprise", description="Default organization division")
            session.add(enterprise_division)
            session.flush()

        general_department = session.query(Department).filter(Department.name == "General Department").one_or_none()
        if general_department is None:
            general_department = Department(
                name="General Department",
                description="Default department for migrated records",
                division_id=enterprise_division.id,
            )
            session.add(general_department)
            session.flush()

        designation_seed = [
            ("System Administrator", DesignationScope.SYSTEM_ADMINISTRATOR, 100, "Default designation for system admins."),
            ("Operating Head (CIO)", DesignationScope.OPERATING_HEAD, 90, "Organization-wide operating head."),
            ("Division Head", DesignationScope.DIVISION_HEAD, 80, "Leader for a division."),
            ("Department Head", DesignationScope.DEPARTMENT_HEAD, 70, "Leader for a department."),
            ("Team Member", DesignationScope.TEAM_MEMBER, 10, "Individual contributor."),
        ]
        designations: dict[str, Designation] = {}
        for name, scope_level, rank, description_text in designation_seed:
            item = session.query(Designation).filter(Designation.name == name).one_or_none()
            if item is None:
                item = Designation(name=name, scope_level=scope_level, rank=rank, description=description_text)
                session.add(item)
                session.flush()
            designations[name] = item

        for existing_team in session.query(Team).all():
            if existing_team.department_id is None:
                existing_team.department_id = general_department.id

        for existing_user in session.query(User).all():
            derived_department_id = existing_user.team.department_id if existing_user.team and existing_user.team.department_id else general_department.id
            existing_user.department_id = existing_user.department_id or derived_department_id
            resolved_department = session.get(Department, existing_user.department_id) if existing_user.department_id else None
            existing_user.division_id = (
                existing_user.division_id
                or (
                    resolved_department.division_id
                    if resolved_department and resolved_department.division_id
                    else enterprise_division.id
                )
            )
            if existing_user.designation_id is None:
                existing_user.designation_id = {
                    UserRole.ADMIN: designations["System Administrator"].id,
                    UserRole.MANAGER: designations["Department Head"].id,
                    UserRole.EMPLOYEE: designations["Team Member"].id,
                }[existing_user.role]
                if hierarchy_columns_added:
                    existing_user.is_protected = True
            if existing_user.role == UserRole.EMPLOYEE and existing_user.reports_to_user_id is None and existing_user.team and existing_user.team.manager_id:
                existing_user.reports_to_user_id = existing_user.team.manager_id
            if existing_user.reports_to_user_id:
                existing_user.manager_chain = str(existing_user.reports_to_user_id)

        session.query(WorkItem).filter(
            WorkItem.status == WorkItemStatus.BLOCKED,
            WorkItem.progress_percent == 25,
        ).update({WorkItem.progress_percent: 0}, synchronize_session=False)
        session.query(WorkItem).filter(
            WorkItem.status == WorkItemStatus.IN_PROGRESS,
            WorkItem.progress_percent == 100,
        ).update({WorkItem.progress_percent: 50}, synchronize_session=False)
        WorkItemService(session).refresh_all_progress()

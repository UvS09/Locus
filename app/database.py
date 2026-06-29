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


def init_db() -> None:
    from app.models import audit_log, comment, notification, role, subtask, task, team, user, work_item  # noqa: F401
    from app.services.work_item_service import WorkItemService
    from app.models.work_item import WorkItem
    from app.utils.work_item_levels import WorkItemStatus

    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    if "users" in inspector.get_table_names():
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "custom_role_id" not in user_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE users ADD COLUMN custom_role_id INTEGER"))
    with SessionLocal.begin() as session:
        session.query(WorkItem).filter(
            WorkItem.status == WorkItemStatus.BLOCKED,
            WorkItem.progress_percent == 25,
        ).update({WorkItem.progress_percent: 0}, synchronize_session=False)
        session.query(WorkItem).filter(
            WorkItem.status == WorkItemStatus.IN_PROGRESS,
            WorkItem.progress_percent == 100,
        ).update({WorkItem.progress_percent: 50}, synchronize_session=False)
        WorkItemService(session).refresh_all_progress()

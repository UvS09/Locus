from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.models.department import Department
from app.models.user import User
from app.utils.enums import UserRole


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[User]:
        stmt = (
            select(User)
            .options(
                selectinload(User.team),
                selectinload(User.designation),
                selectinload(User.department).selectinload(Department.division),
                selectinload(User.division),
                selectinload(User.manager),
                selectinload(User.custom_role),
            )
            .order_by(User.full_name)
        )
        return self.db.scalars(stmt).all()

    def list_by_role(self, role: UserRole) -> list[User]:
        stmt = (
            select(User)
            .options(
                selectinload(User.team),
                selectinload(User.designation),
                selectinload(User.department).selectinload(Department.division),
                selectinload(User.division),
                selectinload(User.manager),
                selectinload(User.custom_role),
            )
            .where(User.role == role, User.is_active.is_(True))
            .order_by(User.full_name)
        )
        return self.db.scalars(stmt).all()

    def list_team_members(self, team_id: int) -> list[User]:
        stmt = (
            select(User)
            .options(
                selectinload(User.team),
                selectinload(User.designation),
                selectinload(User.department).selectinload(Department.division),
                selectinload(User.division),
                selectinload(User.manager),
                selectinload(User.custom_role),
            )
            .where(User.team_id == team_id, User.is_active.is_(True))
            .order_by(User.full_name)
        )
        return self.db.scalars(stmt).all()

    def get_by_id(self, user_id: int) -> User | None:
        stmt = (
            select(User)
            .options(
                selectinload(User.team),
                selectinload(User.designation),
                selectinload(User.department).selectinload(Department.division),
                selectinload(User.division),
                selectinload(User.manager),
                selectinload(User.custom_role),
            )
            .where(User.id == user_id)
        )
        return self.db.scalar(stmt)

    def get_by_email(self, email: str) -> User | None:
        stmt = (
            select(User)
            .options(
                selectinload(User.team),
                selectinload(User.designation),
                selectinload(User.department).selectinload(Department.division),
                selectinload(User.division),
                selectinload(User.manager),
                selectinload(User.custom_role),
            )
            .where(User.email == email.lower())
        )
        return self.db.scalar(stmt)

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        return user

    def delete(self, user: User) -> None:
        self.db.delete(user)
        self.db.flush()

    def count(self, active_only: bool = False) -> int:
        stmt: Select[tuple[User]] = select(User)
        if active_only:
            stmt = stmt.where(User.is_active.is_(True))
        return len(self.db.scalars(stmt).all())

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.user import User
from app.utils.enums import UserRole


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self) -> list[User]:
        return self.db.scalars(select(User).order_by(User.full_name)).all()

    def list_by_role(self, role: UserRole) -> list[User]:
        return self.db.scalars(select(User).where(User.role == role, User.is_active.is_(True)).order_by(User.full_name)).all()

    def list_team_members(self, team_id: int) -> list[User]:
        return self.db.scalars(
            select(User).where(User.team_id == team_id, User.is_active.is_(True)).order_by(User.full_name)
        ).all()

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self.db.scalar(select(User).where(User.email == email.lower()))

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.flush()
        return user

    def count(self, active_only: bool = False) -> int:
        stmt: Select[tuple[User]] = select(User)
        if active_only:
            stmt = stmt.where(User.is_active.is_(True))
        return len(self.db.scalars(stmt).all())

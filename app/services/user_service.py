from app.config import get_settings
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.role import Role
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserUpdate
from app.services.audit_service import AuditService
from app.utils.enums import UserRole
from app.utils.password_generator import generate_temporary_password
from app.utils.security import hash_password

settings = get_settings()


class UserService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.audit_service = AuditService(db)

    def list_users(self) -> list[User]:
        return self.user_repo.list_all()

    def list_custom_roles(self) -> list[Role]:
        return self.db.scalars(select(Role).order_by(Role.name)).all()

    def create_role(self, actor: User, *, name: str, access_level: UserRole, description: str | None = None) -> Role:
        if actor.role != UserRole.ADMIN:
            raise ValueError("Only admins can create roles.")
        cleaned_name = name.strip()
        if len(cleaned_name) < 2:
            raise ValueError("Role name must be at least 2 characters.")
        existing = self.db.scalar(select(Role).where(func.lower(Role.name) == cleaned_name.lower()))
        if existing:
            raise ValueError("A role with this name already exists.")

        role = Role(name=cleaned_name, access_level=access_level, description=description.strip() if description else None)
        self.db.add(role)
        self.db.flush()
        self.audit_service.log_action(
            actor_user_id=actor.id,
            action="role_created",
            entity_type="Role",
            entity_id=role.id,
            details={"name": role.name, "access_level": role.access_level},
        )
        return role

    def has_any_users(self) -> bool:
        return self.user_repo.count() > 0

    def list_managers(self) -> list[User]:
        return self.user_repo.list_by_role(UserRole.MANAGER)

    def list_employees(self) -> list[User]:
        return self.user_repo.list_by_role(UserRole.EMPLOYEE)

    def list_team_members(self, team_id: int) -> list[User]:
        return self.user_repo.list_team_members(team_id)

    def get_user(self, user_id: int) -> User:
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError("User not found.")
        return user

    def create_user(self, actor: User, payload: UserCreate) -> tuple[User, str]:
        if actor.role != UserRole.ADMIN:
            raise ValueError("Only admins can create users.")
        if self.user_repo.get_by_email(payload.email):
            raise ValueError("A user with this email already exists.")

        custom_role = self._get_custom_role(payload.custom_role_id)
        access_role = custom_role.access_level if custom_role else payload.role
        temporary_password = generate_temporary_password()
        user = User(
            full_name=payload.full_name,
            email=payload.email.lower(),
            role=access_role,
            custom_role_id=custom_role.id if custom_role else None,
            team_id=payload.team_id,
            password_hash=hash_password(temporary_password),
            must_change_password=True,
            is_active=True,
        )
        self.user_repo.create(user)
        self.audit_service.log_action(
            actor_user_id=actor.id,
            action="user_created",
            entity_type="User",
            entity_id=user.id,
            details={"role": user.display_role, "access_level": user.role, "team_id": user.team_id},
        )
        return user, temporary_password

    def update_user(self, actor: User, user_id: int, payload: UserUpdate) -> User:
        if actor.role != UserRole.ADMIN:
            raise ValueError("Only admins can update users.")
        user = self.get_user(user_id)
        custom_role = self._get_custom_role(payload.custom_role_id)
        user.full_name = payload.full_name
        user.role = custom_role.access_level if custom_role else payload.role
        user.custom_role_id = custom_role.id if custom_role else None
        user.team_id = payload.team_id
        user.is_active = payload.is_active
        self.audit_service.log_action(
            actor_user_id=actor.id,
            action="user_updated",
            entity_type="User",
            entity_id=user.id,
            details={"role": user.display_role, "access_level": user.role, "team_id": user.team_id, "is_active": user.is_active},
        )
        return user

    def deactivate_user(self, actor: User, user_id: int) -> User:
        if actor.role != UserRole.ADMIN:
            raise ValueError("Only admins can deactivate users.")
        user = self.get_user(user_id)
        user.is_active = False
        self.audit_service.log_action(
            actor_user_id=actor.id,
            action="user_deactivated",
            entity_type="User",
            entity_id=user.id,
        )
        return user

    def bootstrap_admin(self, *, full_name: str, email: str, password: str) -> User:
        if settings.is_production:
            raise ValueError("Signup is disabled in production.")
        if self.has_any_users():
            raise ValueError("Signup is available only for the first local admin.")
        if not email.lower().endswith(settings.allowed_email_suffix):
            raise ValueError(f"Email must end with {settings.allowed_email_suffix}.")

        user = User(
            full_name=full_name,
            email=email.lower(),
            role=UserRole.ADMIN,
            password_hash=hash_password(password),
            must_change_password=False,
            is_active=True,
        )
        self.user_repo.create(user)
        self.audit_service.log_action(
            actor_user_id=user.id,
            action="bootstrap_admin_created",
            entity_type="User",
            entity_id=user.id,
        )
        return user

    def _get_custom_role(self, role_id: int | None) -> Role | None:
        if role_id is None:
            return None
        role = self.db.get(Role, role_id)
        if not role:
            raise ValueError("Custom role not found.")
        return role

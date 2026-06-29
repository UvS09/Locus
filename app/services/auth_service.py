from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import ChangePasswordRequest, LoginRequest
from app.services.audit_service import AuditService
from app.utils.security import hash_password, verify_password

settings = get_settings()


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)
        self.audit_service = AuditService(db)

    def authenticate(self, payload: LoginRequest) -> User:
        user = self.user_repo.get_by_email(payload.email)
        if not user or not verify_password(payload.password, user.password_hash):
            self.audit_service.log_action(
                actor_user_id=user.id if user else None,
                action="login_failed",
                entity_type="User",
                entity_id=user.id if user else None,
                details={"email": payload.email},
            )
            raise ValueError("Invalid email or password.")
        if not user.is_active:
            raise ValueError("This account has been deactivated.")
        user.last_login_at = datetime.now(UTC)
        self.audit_service.log_action(
            actor_user_id=user.id,
            action="login_success",
            entity_type="User",
            entity_id=user.id,
        )
        return user

    def change_password(self, user: User, payload: ChangePasswordRequest) -> None:
        if not verify_password(payload.current_password, user.password_hash):
            raise ValueError("Current password is incorrect.")
        user.password_hash = hash_password(payload.new_password)
        user.must_change_password = False
        self.audit_service.log_action(
            actor_user_id=user.id,
            action="password_changed",
            entity_type="User",
            entity_id=user.id,
        )

    def validate_allowed_email(self, email: str) -> None:
        if not email.lower().endswith(settings.allowed_email_suffix):
            raise ValueError(f"Email must end with {settings.allowed_email_suffix}.")

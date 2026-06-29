from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.repositories.audit_repository import AuditRepository


class AuditService:
    def __init__(self, db: Session):
        self.db = db
        self.audit_repo = AuditRepository(db)

    def log_action(self, *, actor_user_id: int | None, action: str, entity_type: str, entity_id: int | None, details: dict | None = None) -> AuditLog:
        audit_log = AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details or {},
        )
        return self.audit_repo.create(audit_log)

    def list_recent(self, limit: int = 20) -> list[AuditLog]:
        return self.audit_repo.list_recent(limit=limit)

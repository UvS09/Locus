from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_recent(self, limit: int = 20) -> list[AuditLog]:
        return self.db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()

    def create(self, audit_log: AuditLog) -> AuditLog:
        self.db.add(audit_log)
        self.db.flush()
        return audit_log

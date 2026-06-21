from sqlalchemy.orm import Session

from app.models import AuditLog


def audit(db: Session, tenant_id: str, action: str, details: dict | None = None) -> None:
    db.add(AuditLog(tenant_id=tenant_id, action=action, details=details or {}))

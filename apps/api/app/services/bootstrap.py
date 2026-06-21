from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Tenant, TenantMembership, User
from app.security import hash_password


def bootstrap_admin_user(db: Session) -> None:
    settings = get_settings()
    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        return

    tenant = db.get(Tenant, settings.default_tenant_id)
    if tenant is None:
        tenant = Tenant(id=settings.default_tenant_id, name="Default Tenant", industry="Unknown")
        db.add(tenant)
        db.flush()

    email = settings.bootstrap_admin_email.lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, display_name="Bootstrap Admin", password_hash=hash_password(settings.bootstrap_admin_password))
        db.add(user)
        db.flush()

    membership = db.scalar(
        select(TenantMembership).where(TenantMembership.tenant_id == tenant.id, TenantMembership.user_id == user.id)
    )
    if membership is None:
        db.add(TenantMembership(tenant_id=tenant.id, user_id=user.id, role="admin"))
    elif membership.role != "admin":
        membership.role = "admin"

    db.commit()

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import TenantMembership, User
from app.services.auth_tokens import create_access_token as encode_access_token
from app.services.auth_tokens import decode_access_token as decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    email: str
    tenant_id: str
    role: str


ROLE_ORDER = {"viewer": 0, "analyst": 1, "admin": 2}


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000)
    return f"pbkdf2_sha256${salt}${base64.urlsafe_b64encode(digest).decode('ascii')}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, salt, encoded_digest = password_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000)
    expected = base64.urlsafe_b64decode(encoded_digest.encode("ascii"))
    return hmac.compare_digest(actual, expected)


def create_access_token(user: User, tenant_id: str, role: str) -> str:
    settings = get_settings()
    return encode_access_token(
        {
            "sub": user.id,
            "email": user.email,
            "tenant_id": tenant_id,
            "role": role,
        },
        settings.auth_jwt_secret,
        settings.auth_token_ttl_minutes,
    )


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        return decode_token(token, settings.auth_jwt_secret)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token") from exc


def get_auth_context(
    token: Annotated[str | None, Depends(oauth2_scheme)] = None,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    db: Session = Depends(get_db),
) -> AuthContext:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required")
    payload = decode_access_token(token)
    token_tenant_id = str(payload.get("tenant_id") or "")
    tenant_id = x_tenant_id or token_tenant_id
    if tenant_id != token_tenant_id:
        membership = db.scalar(
            select(TenantMembership).where(TenantMembership.tenant_id == tenant_id, TenantMembership.user_id == payload.get("sub"))
        )
        if membership is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not a member of the requested tenant")
        role = membership.role
    else:
        role = str(payload.get("role") or "viewer")
    return AuthContext(user_id=str(payload["sub"]), email=str(payload.get("email") or ""), tenant_id=tenant_id, role=role)


def require_role(required_role: str):
    def dependency(context: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if ROLE_ORDER.get(context.role, -1) < ROLE_ORDER[required_role]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Requires {required_role} role")
        return context

    return dependency


def get_tenant_id(x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id")) -> str:
    if x_tenant_id:
        return x_tenant_id
    bootstrap_enabled = bool(get_settings().bootstrap_admin_email and get_settings().bootstrap_admin_password)
    if bootstrap_enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required")
    return get_settings().default_tenant_id

from fastapi import Header

from app.config import get_settings


def get_tenant_id(x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id")) -> str:
    return x_tenant_id or get_settings().default_tenant_id

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from jwt import InvalidTokenError

ALGORITHM = "HS256"


def create_access_token(payload: dict[str, Any], secret: str, ttl_minutes: int) -> str:
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=ttl_minutes)
    data = payload.copy()
    data.update({"iat": issued_at, "exp": expires_at})
    return jwt.encode(data, secret, algorithm=ALGORITHM)


def decode_access_token(token: str, secret: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, secret, algorithms=[ALGORITHM], options={"require": ["sub", "email", "tenant_id", "role", "exp", "iat"]})
    except InvalidTokenError as exc:
        raise ValueError("Invalid token") from exc

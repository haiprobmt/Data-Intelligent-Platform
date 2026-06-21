import pytest

from app.config import Settings, validate_security_settings
from app.services.auth_tokens import create_access_token, decode_access_token


def test_jwt_round_trip_requires_standard_claims():
    token = create_access_token(
        {
            "sub": "user-1",
            "email": "analyst@example.com",
            "tenant_id": "tenant-1",
            "role": "analyst",
        },
        "test-secret",
        30,
    )

    payload = decode_access_token(token, "test-secret")

    assert payload["sub"] == "user-1"
    assert payload["tenant_id"] == "tenant-1"
    assert payload["role"] == "analyst"


def test_invalid_jwt_secret_fails_non_local_environment():
    settings = Settings(environment="production", auth_jwt_secret="change-this-secret")

    with pytest.raises(RuntimeError):
        validate_security_settings(settings)

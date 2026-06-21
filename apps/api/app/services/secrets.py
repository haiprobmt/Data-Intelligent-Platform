import os

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ConnectionSecret, SourceSystem


def resolve_secret_reference(secret_reference: str | None) -> str:
    if not secret_reference:
        raise ValueError("A secret reference is required")
    if secret_reference.startswith("env://"):
        variable_name = secret_reference.removeprefix("env://")
        value = os.getenv(variable_name)
        if not value:
            raise ValueError(f"Environment variable {variable_name} is not set")
        return value
    if secret_reference.startswith("sqlite://"):
        return secret_reference
    if secret_reference.startswith(("kv://", "vault://", "secret://")):
        return _resolve_azure_key_vault_secret(secret_reference)
    raise ValueError("Use env://, kv://, vault://, secret://, or sqlite:// references; raw credentials are not accepted")


def _resolve_azure_key_vault_secret(secret_reference: str) -> str:
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
    except ImportError as exc:
        raise ValueError("Install azure-identity and azure-keyvault-secrets to use Key Vault references") from exc

    vault_url, secret_name = _parse_vault_reference(secret_reference)
    client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())
    secret = client.get_secret(secret_name)
    if not secret.value:
        raise ValueError(f"Secret {secret_name} is empty")
    return secret.value


def _parse_vault_reference(secret_reference: str) -> tuple[str, str]:
    if secret_reference.startswith("kv://"):
        remainder = secret_reference.removeprefix("kv://")
    elif secret_reference.startswith("vault://"):
        remainder = secret_reference.removeprefix("vault://")
    else:
        remainder = secret_reference.removeprefix("secret://")

    if "/" not in remainder:
        vault_name = remainder.split("#", 1)[0]
        secret_name = remainder.split("#", 1)[1] if "#" in remainder else ""
        if not secret_name:
            raise ValueError("Key Vault references must include a secret name")
        return f"https://{vault_name}.vault.azure.net", secret_name

    vault, secret_name = remainder.split("/", 1)
    if vault.startswith("https://"):
        vault_url = vault
    else:
        vault_url = f"https://{vault}.vault.azure.net"
    if not secret_name:
        raise ValueError("Key Vault references must include a secret name")
    return vault_url, secret_name


def validate_secret_reference_for_tenant(secret_reference: str | None, tenant_id: str) -> None:
    if not secret_reference:
        return
    if not secret_reference.startswith(("env://", "kv://", "vault://", "secret://", "sqlite://")):
        raise ValueError("Use env://, kv://, vault://, secret://, or sqlite:// references; raw credentials are not accepted")


def source_secret_reference(db: Session, tenant_id: str, source: SourceSystem) -> str | None:
    if source.secret_id:
        secret = db.get(ConnectionSecret, source.secret_id)
        if secret is None or secret.tenant_id != tenant_id:
            raise ValueError("Connection secret not found for tenant")
        return secret.reference
    return source.secret_reference


def provider_for_reference(reference: str) -> str:
    if reference.startswith("env://"):
        return "env"
    if reference.startswith("sqlite://"):
        return "sqlite"
    if reference.startswith(("kv://", "vault://", "secret://")):
        return "azure_key_vault"
    raise ValueError("Unsupported secret reference provider")

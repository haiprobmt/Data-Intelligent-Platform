from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Enterprise Data Intelligence Hub"
    database_url: str = "sqlite:///./hub.db"
    default_tenant_id: str = "11111111-1111-4111-8111-111111111111"
    cors_origins: str = "http://localhost:3000"
    upload_dir: str = "uploads"
    aws_bedrock_region: str = "us-east-1"
    aws_bedrock_model_id: str = "anthropic.claude-3-haiku-20240307-v1:0"
    auth_jwt_secret: str = "change-this-secret"
    auth_token_ttl_minutes: int = 480
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
    azure_tenant_id: str | None = None
    neo4j_uri: str | None = None
    neo4j_user: str | None = None
    neo4j_password: str | None = None
    job_backend: str = "background"
    profile_default_row_limit: int = 10000
    profile_default_max_columns: int = 50
    profile_default_timeout_seconds: int = 30

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

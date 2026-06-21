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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

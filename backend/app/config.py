from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str | None = None
    database_url_direct: str | None = None
    environment: str = "development"
    render: bool = False
    jwt_secret: str = "local-development-secret-change-before-deploy"
    access_token_minutes: int = 60
    demo_mode: bool = False
    auto_create_tables: bool = False
    cors_origins: str = "http://localhost:3000"
    admin_emails: str = ""
    integration_encryption_key: str = ""

    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore")


settings = Settings()

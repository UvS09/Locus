from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="Locus", alias="APP_NAME")
    app_env: Literal["development", "production", "test"] = Field(
        default="development",
        alias="APP_ENV",
    )
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    secret_key: str = Field(default="change-this-in-phase-4", alias="SECRET_KEY")
    access_token_expire_minutes: int = Field(default=120, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    remember_me_expire_days: int = Field(default=14, alias="REMEMBER_ME_EXPIRE_DAYS")
    cookie_name: str = Field(default="task_manager_access_token", alias="COOKIE_NAME")
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    cookie_samesite: Literal["lax", "strict", "none"] = Field(default="lax", alias="COOKIE_SAMESITE")
    allowed_email_domain: str = Field(default="honda.hmsi.in", alias="ALLOWED_EMAIL_DOMAIN")

    database_url_override: str | None = Field(default=None, alias="DATABASE_URL")
    sqlite_db_path: str = Field(default="task_manager.db", alias="SQLITE_DB_PATH")
    postgres_user: str = Field(default="postgres", alias="POSTGRES_USER")
    postgres_password: str = Field(default="postgres", alias="POSTGRES_PASSWORD")
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="task_manager", alias="POSTGRES_DB")
    init_db_on_startup: bool = Field(default=True, alias="INIT_DB_ON_STARTUP")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        if self.app_env in {"development", "test"}:
            return f"sqlite:///{(BASE_DIR / self.sqlite_db_path).resolve()}"

        return (
            "postgresql+psycopg://"
            f"{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def allowed_email_suffix(self) -> str:
        return f"@{self.allowed_email_domain}"


@lru_cache
def get_settings() -> Settings:
    return Settings()

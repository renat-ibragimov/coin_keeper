"""Application settings, sourced only from environment variables.

Mirrors the configuration block in docs/10-infra.md. Nothing here has a real
value as a default: secrets come from the environment, never from the code.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- core ---
    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")
    jwt_secret: str = Field(alias="JWT_SECRET")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    public_base_url: str = Field(alias="PUBLIC_BASE_URL")
    cors_origins: str = Field(default="", alias="CORS_ORIGINS")

    # --- object storage ---
    s3_endpoint: str = Field(alias="S3_ENDPOINT")
    # Signs presigned URLs against a browser-reachable host instead of the
    # docker-network one, when the two differ (docs/06-media-storage.md).
    s3_public_endpoint: str | None = Field(default=None, alias="S3_PUBLIC_ENDPOINT")
    s3_bucket: str = Field(default="coinkeeper-media", alias="S3_BUCKET")
    s3_access_key: str = Field(alias="S3_ACCESS_KEY")
    s3_secret_key: str = Field(alias="S3_SECRET_KEY")
    s3_region: str = Field(default="us-east-1", alias="S3_REGION")

    # --- auth, docs/07-auth.md ---
    allow_registration: bool = Field(default=True, alias="ALLOW_REGISTRATION")
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    email_verify_ttl_hours: int = 24
    password_reset_ttl_hours: int = 1
    password_min_length: int = 10
    refresh_cookie_name: str = "coinkeeper_refresh"
    cookie_secure: bool = Field(default=True, alias="COOKIE_SECURE")

    # --- mail, docs/10-infra.md ---
    mail_backend: Literal["console", "smtp"] = Field(default="console", alias="MAIL_BACKEND")
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="Bakost Numismatics <noreply@localhost>", alias="SMTP_FROM")
    smtp_starttls: bool = Field(default=True, alias="SMTP_STARTTLS")

    # --- external sources, wired up in stages 5 and 6 ---
    nbu_api_base: str = Field(
        default="https://bank.gov.ua/NBUStatService/v1/statdirectory", alias="NBU_API_BASE"
    )
    nbu_catalog_base: str = Field(
        default="https://bank.gov.ua/ua/numismatic-products", alias="NBU_CATALOG_BASE"
    )
    uacoins_base: str = Field(default="https://www.ua-coins.info", alias="UACOINS_BASE")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def model_post_init(self, _context: object) -> None:
        if self.mail_backend == "smtp" and not self.smtp_host:
            msg = "MAIL_BACKEND=smtp requires SMTP_HOST to be set"
            raise ValueError(msg)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

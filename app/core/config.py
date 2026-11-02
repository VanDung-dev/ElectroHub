from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", extra="ignore", hide_input_in_errors=True
    )

    secret_key: SecretStr = Field(min_length=32)
    cookie_secure: bool = False
    access_token_minutes: int = Field(default=60, ge=1, le=1440)
    log_level: str = "INFO"
    database_url: SecretStr | None = None
    sqlserver_host: str = "localhost"
    sqlserver_port: int = Field(default=1433, ge=1, le=65535)
    sqlserver_database: str = "ElectroHub"
    sqlserver_user: str = "sa"
    mssql_sa_password: SecretStr | None = None
    sqlserver_trust_certificate: bool = True
    site_url: str = "http://localhost:8000"
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    mail_from: str | None = None
    facebook_page_url: str | None = None
    zalo_page_url: str | None = None
    subiz_embed_code: str | None = None

    @model_validator(mode="after")
    def require_database_credentials(self):
        if not self.database_url and not self.mssql_sa_password:
            raise ValueError("Set MSSQL_SA_PASSWORD or DATABASE_URL")
        for name in ("smtp_password",):
            value = getattr(self, name)
            if value is not None and not value.get_secret_value().strip():
                setattr(self, name, None)
        return self

    @property
    def db_url(self) -> str | URL:
        if self.database_url:
            return self.database_url.get_secret_value()
        return URL.create(
            "mssql+pyodbc",
            username=self.sqlserver_user,
            password=self.mssql_sa_password.get_secret_value(),
            host=self.sqlserver_host,
            port=self.sqlserver_port,
            database=self.sqlserver_database,
            query={
                "driver": "ODBC Driver 18 for SQL Server",
                "Encrypt": "yes",
                "TrustServerCertificate": "yes" if self.sqlserver_trust_certificate else "no",
            },
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()

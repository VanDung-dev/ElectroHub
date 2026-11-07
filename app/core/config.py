import re
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, model_validator
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
    tawkto_embed_code: str | None = Field(
        default=None,
        validation_alias=AliasChoices("tawkto_embed_code", "tawk_to_embed_code"),
    )
    tawkto_property_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("tawkto_property_id", "property_id"),
    )
    tawkto_widget_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("tawkto_widget_id", "widget_id"),
    )

    # Payments. ``mock`` keeps the original simulated flow; ``sandbox`` and ``live``
    # call the real gateways and therefore require provider credentials.
    payment_mode: Literal["mock", "sandbox", "live"] = "mock"
    refund_hold_hours: int = Field(default=72, ge=0, le=24 * 30)
    # VAT applied to the discounted goods value (shipping stays untaxed).
    vat_percent: int = Field(default=10, ge=0, le=100)

    vnpay_tmn_code: str | None = None
    vnpay_hash_secret: SecretStr | None = None
    vnpay_pay_url: str = "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html"
    vnpay_api_url: str = "https://sandbox.vnpayment.vn/merchant_webapi/api/transaction"
    vnpay_expire_minutes: int = Field(default=15, ge=1, le=60)

    paypal_client_id: str | None = None
    paypal_client_secret: SecretStr | None = None
    paypal_api_base: str = "https://api-m.sandbox.paypal.com"
    paypal_webhook_id: str | None = None
    paypal_currency: str = "USD"
    paypal_vnd_per_usd: Decimal = Field(default=Decimal("25000"), gt=0)

    @model_validator(mode="after")
    def require_database_credentials(self):
        if not self.database_url and not self.mssql_sa_password:
            raise ValueError("Set MSSQL_SA_PASSWORD or DATABASE_URL")
        for name in ("smtp_password", "vnpay_hash_secret", "paypal_client_secret"):
            value = getattr(self, name)
            if value is not None and not value.get_secret_value().strip():
                setattr(self, name, None)
        for name in (
            "smtp_host",
            "smtp_username",
            "mail_from",
            "vnpay_tmn_code",
            "paypal_client_id",
            "paypal_webhook_id",
            "tawkto_property_id",
            "tawkto_widget_id",
            "tawkto_embed_code",
            "subiz_embed_code",
        ):
            value = getattr(self, name)
            if isinstance(value, str) and not value.strip():
                setattr(self, name, None)
        # ponytail: compile regexes once at module scope and cleanly extract widget credentials
        prop = self.tawkto_property_id or ""
        if "/" in prop or "tawk.to" in prop:
            m = re.search(r"([a-f0-9]{24})(?:/([a-zA-Z0-9]+))?", prop)
            if m:
                self.tawkto_property_id = m.group(1)
                if m.group(2) and not self.tawkto_widget_id:
                    self.tawkto_widget_id = m.group(2)
        widget = self.tawkto_widget_id or ""
        if "/" in widget or "tawk.to" in widget:
            m = re.search(r"([a-f0-9]{24})/([a-zA-Z0-9]+)", widget)
            if m:
                if not self.tawkto_property_id:
                    self.tawkto_property_id = m.group(1)
                self.tawkto_widget_id = m.group(2)
            else:
                self.tawkto_widget_id = widget.strip("/").split("/")[-1]
        self._validate_payment_configuration()
        return self

    def _validate_payment_configuration(self) -> None:
        """Fail fast instead of silently falling back to the simulated flow."""
        if self.payment_mode == "mock":
            return
        missing = [
            name
            for name, value in (
                ("VNPAY_TMN_CODE", self.vnpay_tmn_code),
                ("VNPAY_HASH_SECRET", self.vnpay_hash_secret),
                ("PAYPAL_CLIENT_ID", self.paypal_client_id),
                ("PAYPAL_CLIENT_SECRET", self.paypal_client_secret),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"PAYMENT_MODE={self.payment_mode} requires: {', '.join(missing)}")
        if self.payment_mode == "live":
            if not self.site_url.lower().startswith("https://"):
                raise ValueError("PAYMENT_MODE=live requires an HTTPS SITE_URL")
            if not self.cookie_secure:
                raise ValueError("PAYMENT_MODE=live requires COOKIE_SECURE=true")

    @property
    def base_url(self) -> str:
        return self.site_url.rstrip("/")

    @property
    def vnpay_return_url(self) -> str:
        # Derived from SITE_URL so there is only one place to change a tunnel/domain.
        return f"{self.base_url}/payments/vnpay/return"

    @property
    def vnpay_ipn_url(self) -> str:
        return f"{self.base_url}/api/v1/payments/vnpay/ipn"

    @property
    def paypal_return_url(self) -> str:
        return f"{self.base_url}/payments/paypal/return"

    @property
    def is_mock_payment(self) -> bool:
        return self.payment_mode == "mock"

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

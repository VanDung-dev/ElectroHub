from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [{"email": "customer@example.com", "password": "ExamplePassword123!"}]
        },
    )

    email: EmailStr = Field(max_length=254)
    password: SecretStr = Field(min_length=8, max_length=72)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()

    @field_validator("password")
    @classmethod
    def password_byte_limit(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().encode("utf-8")) > 72:
            raise ValueError("Mật khẩu tối đa 72 byte UTF-8")
        return value


class RegisterRequest(LoginRequest):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "email": "customer@example.com",
                    "password": "ExamplePassword123!",
                    "name": "Khách hàng",
                }
            ]
        }
    )

    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Tên không được để trống")
        if len(value.encode("utf-16-le")) > 200:
            raise ValueError("Tên vượt quá giới hạn NVARCHAR(100)")
        return value


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    name: str
    role: Literal["admin", "customer"]
    created_at: datetime


class DetailResponse(BaseModel):
    detail: str


class CsrfResponse(BaseModel):
    csrf_token: str

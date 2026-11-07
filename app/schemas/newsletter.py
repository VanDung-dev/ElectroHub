from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class SubscribeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    consent: Literal[True]


class CampaignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str = Field(min_length=3, max_length=160)
    body: str = Field(min_length=10, max_length=5000)

    @field_validator("subject")
    @classmethod
    def valid_subject(cls, value: str) -> str:
        value = value.strip()
        if "\r" in value or "\n" in value:
            raise ValueError("Tiêu đề không được chứa xuống dòng")
        return value


class SubscriberItem(BaseModel):
    id: int
    email: str
    created_at: datetime


class SubscriberListResponse(BaseModel):
    total: int
    items: list[SubscriberItem]


class CampaignItem(BaseModel):
    id: int
    subject: str
    body: str
    recipient_count: int
    sent_at: datetime
    status: str


class CampaignListResponse(BaseModel):
    total: int
    items: list[CampaignItem]


class PreviewEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str = Field(min_length=3, max_length=160)
    body: str = Field(min_length=10, max_length=5000)

    @field_validator("subject")
    @classmethod
    def valid_subject(cls, value: str) -> str:
        value = value.strip()
        if "\r" in value or "\n" in value:
            raise ValueError("Tiêu đề không được chứa xuống dòng")
        return value


class PreviewEmailResponse(BaseModel):
    subject: str
    html: str


class TemplateItem(BaseModel):
    id: str
    name: str
    subject: str
    body: str


class TemplateListResponse(BaseModel):
    items: list[TemplateItem]

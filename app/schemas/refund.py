from datetime import datetime
from typing import Literal

from pydantic import BaseModel

RefundStatus = Literal["scheduled", "processing", "succeeded", "failed", "rejected"]


class RefundInfo(BaseModel):
    id: int
    status: RefundStatus
    amount: int
    currency: str
    reason: str | None = None
    requested_at: datetime
    due_at: datetime
    confirmed_at: datetime | None = None
    provider_refund_id: str | None = None


class AdminRefundOut(RefundInfo):
    order_code: str
    order_total: int
    method: str
    payment_status: str
    provider: str
    requested_by: int | None = None
    confirmed_by: int | None = None
    # Computed server-side so the admin UI never has to trust the browser clock.
    due: bool


class RefundListResponse(BaseModel):
    items: list[AdminRefundOut]
    total: int


class RefundRejectRequest(BaseModel):
    reason: str = ""

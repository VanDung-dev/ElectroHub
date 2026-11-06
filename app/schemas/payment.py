from pydantic import BaseModel

from app.schemas.cart import OrderPayment
from app.schemas.refund import RefundInfo


class PaymentSessionOut(BaseModel):
    url: str
    provider: str
    simulation: bool
    amount_minor: int | None = None
    currency: str | None = None


class PaymentDetailsOut(OrderPayment):
    code: str
    total: int
    provider: str
    currency: str
    amount_minor: int | None = None
    attempt: int = 1
    simulation: bool = False
    refund: RefundInfo | None = None

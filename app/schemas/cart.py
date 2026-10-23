from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CartItemAdd(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"product_id": 1, "qty": 2}]},
    )

    product_id: int = Field(ge=1)
    qty: int = Field(default=1, ge=1, le=99)


class CartItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"qty": 3}]})

    qty: int = Field(ge=1, le=99)


class VoucherApply(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [{"code": "WELCOME10"}]}
    )

    code: str = Field(min_length=1, max_length=32)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("Mã voucher không được để trống")
        return value


class CartLine(BaseModel):
    id: int
    product_id: int
    slug: str
    name: str
    unit_price: int
    qty: int
    line_total: int
    stock: int


class CartVoucher(BaseModel):
    code: str
    percent: int
    max_discount: int
    discount: int


class CartResponse(BaseModel):
    items: list[CartLine]
    subtotal: int
    discount: int
    shipping_fee: int
    total: int
    voucher: CartVoucher | None = None


PaymentMethod = Literal["COD", "CHUYEN_KHOAN_MOCK"]
OrderStatus = Literal["pending", "confirmed", "shipping", "done", "cancelled"]


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "name": "Khách hàng",
                    "phone": "0901234567",
                    "address": "269/20 Lý Thường Kiệt, TP.HCM",
                    "payment_method": "COD",
                    "voucher_code": "WELCOME10",
                }
            ]
        },
    )

    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=10, max_length=10, pattern=r"^0\d{9}$")
    address: str = Field(min_length=5, max_length=255)
    payment_method: PaymentMethod = "COD"
    voucher_code: str | None = Field(default=None, max_length=32)

    @field_validator("name", "address")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Không được để trống")
        return value

    @field_validator("voucher_code")
    @classmethod
    def normalize_voucher(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        return value or None


class OrderAddress(BaseModel):
    name: str
    phone: str
    address: str


class OrderLine(BaseModel):
    product_id: int
    slug: str | None
    name: str
    price: int
    qty: int
    line_total: int


class OrderPayment(BaseModel):
    method: PaymentMethod
    status: Literal["pending", "paid", "failed", "refunded"]


class OrderResponse(BaseModel):
    code: str
    status: OrderStatus
    subtotal: int
    discount: int
    shipping_fee: int
    total: int
    voucher_code: str | None
    address: OrderAddress
    created_at: datetime
    items: list[OrderLine]
    payment: OrderPayment


class OrderSummary(BaseModel):
    code: str
    status: OrderStatus
    total: int
    item_count: int
    created_at: datetime


class OrderListResponse(BaseModel):
    items: list[OrderSummary]
    total: int
    page: int
    page_size: int


class PayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: PaymentMethod


class AdminOrderUpdate(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [{"status": "confirmed"}]}
    )

    status: OrderStatus

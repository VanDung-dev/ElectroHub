"""Shared types for payment gateway adapters."""

from dataclasses import dataclass, field


class PaymentGatewayError(Exception):
    """Raised when a provider call fails before a local state change is possible."""

    def __init__(self, message: str, *, debug_id: str | None = None) -> None:
        super().__init__(message)
        self.debug_id = debug_id


@dataclass(frozen=True)
class GatewayOutcome:
    """Provider result normalised to the local payment state machine."""

    status: str  # paid | pending | failed | refunded
    provider_status: str | None = None
    provider_txn_id: str | None = None
    amount_minor: int | None = None
    currency: str | None = None
    raw: dict = field(default_factory=dict)

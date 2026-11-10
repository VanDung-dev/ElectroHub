from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.deps import DbSession, require_admin, require_staff
from app.models.refund import utc_now
from app.models.user import User
from app.schemas.auth import DetailResponse
from app.schemas.refund import (
    AdminRefundOut,
    RefundInfo,
    RefundListResponse,
    RefundRejectRequest,
)
from app.services.payments import service as payment_service

router = APIRouter(
    prefix="/api/v1/admin/refunds",
    tags=["admin-refunds"],
    dependencies=[Depends(require_staff)],
    responses={
        401: {"model": DetailResponse},
        403: {"model": DetailResponse},
        404: {"model": DetailResponse},
        409: {"model": DetailResponse},
    },
)


def _refund_info(refund) -> RefundInfo:
    # ponytail: use pydantic from_attributes to avoid manual field mapping
    return RefundInfo.model_validate(refund)


@router.get("", response_model=RefundListResponse)
def list_refunds(
    db: DbSession,
    status: str | None = Query(None, pattern=r"^(scheduled|processing|succeeded|failed|rejected)$"),
    due: bool = Query(False, description="Chỉ các yêu cầu đã đủ thời gian giữ tiền"),
):
    now = utc_now()
    rows = payment_service.list_refunds(db, status=status, due_only=due)
    items = [
        AdminRefundOut(
            **_refund_info(refund).model_dump(),
            order_code=order.code,
            order_total=order.total,
            method=payment.method,
            payment_status=payment.status,
            provider=payment.provider,
            requested_by=refund.requested_by,
            confirmed_by=refund.confirmed_by,
            due=refund.due_at <= now,
        )
        for refund, order, payment in rows
    ]
    return RefundListResponse(items=items, total=len(items))


@router.post("/{refund_id}/confirm", response_model=RefundInfo)
def confirm_refund(
    refund_id: int,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
):
    """Shop confirms a refund after the hold window; this calls the gateway."""
    refund = payment_service.confirm_refund(db, refund_id, admin)
    return _refund_info(refund)


@router.post("/{refund_id}/reject", response_model=RefundInfo)
def reject_refund(
    refund_id: int,
    data: RefundRejectRequest,
    db: DbSession,
    admin: Annotated[User, Depends(require_admin)],
):
    refund = payment_service.reject_refund(db, refund_id, admin, data.reason)
    return _refund_info(refund)

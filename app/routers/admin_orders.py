from fastapi import APIRouter, Depends, Query

from app.core.deps import DbSession, require_admin
from app.schemas.auth import DetailResponse
from app.schemas.cart import AdminOrderUpdate, OrderListResponse, OrderResponse
from app.services import order_service

router = APIRouter(
    prefix="/api/v1/admin/orders",
    tags=["admin-orders"],
    dependencies=[Depends(require_admin)],
    responses={
        401: {"model": DetailResponse},
        403: {"model": DetailResponse},
        404: {"model": DetailResponse},
        409: {"model": DetailResponse},
    },
)


@router.get("", response_model=OrderListResponse)
def list_orders(
    db: DbSession,
    status: str | None = Query(None, pattern=r"^(pending|confirmed|shipping|done|cancelled)$"),
    q: str | None = Query(None, max_length=20, description="Tìm một phần mã đơn"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
):
    """Danh sách đơn cho admin, lọc theo trạng thái và mã đơn."""
    return order_service.list_all_orders(db, status=status, query=q, page=page, page_size=page_size)


@router.patch("/{code}", response_model=OrderResponse)
def update_status(code: str, data: AdminOrderUpdate, db: DbSession):
    """Đổi trạng thái đơn; hủy đơn sẽ hoàn kho và hoàn lượt voucher."""
    return order_service.update_order_status(db, code, data)

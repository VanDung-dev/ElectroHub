from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.schemas.auth import DetailResponse
from app.schemas.cart import CartItemAdd, CartItemUpdate, CartResponse, VoucherApply
from app.services import order_service

router = APIRouter(
    prefix="/api/v1/cart",
    tags=["cart"],
    responses={
        400: {"model": DetailResponse},
        401: {"model": DetailResponse},
        404: {"model": DetailResponse},
        409: {"model": DetailResponse},
    },
)


@router.get("", response_model=CartResponse)
def read_cart(user: CurrentUser, db: DbSession):
    """Giỏ hàng hiện tại kèm tạm tính, phí ship và tổng tiền."""
    return order_service.get_cart(db, user.id)


@router.post("/items", response_model=CartResponse)
def add_item(data: CartItemAdd, user: CurrentUser, db: DbSession):
    """Thêm sản phẩm; cộng dồn nếu sản phẩm đã có trong giỏ."""
    return order_service.add_item(db, user.id, data)


@router.put("/items/{item_id}", response_model=CartResponse)
def update_item(item_id: int, data: CartItemUpdate, user: CurrentUser, db: DbSession):
    """Đổi số lượng một dòng trong giỏ (1..99, không vượt tồn kho)."""
    return order_service.update_item(db, user.id, item_id, data.qty)


@router.delete("/items/{item_id}", response_model=CartResponse)
def delete_item(item_id: int, user: CurrentUser, db: DbSession):
    """Xóa một dòng khỏi giỏ và trả giỏ sau khi xóa."""
    return order_service.delete_item(db, user.id, item_id)


@router.post("/apply-voucher", response_model=CartResponse)
def apply_voucher(data: VoucherApply, user: CurrentUser, db: DbSession):
    """Xem trước giảm giá; voucher chỉ bị trừ lượt khi checkout thành công."""
    return order_service.apply_voucher(db, user.id, data.code)

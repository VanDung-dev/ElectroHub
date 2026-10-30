import secrets
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models.cart import CartItem
from app.models.order import Order, OrderItem
from app.models.payment import Payment
from app.models.product import Product
from app.models.user import User
from app.models.voucher import Voucher
from app.schemas.cart import (
    AdminOrderUpdate,
    CartItemAdd,
    CartLine,
    CartResponse,
    CartVoucher,
    CheckoutRequest,
    OrderAddress,
    OrderLine,
    OrderListResponse,
    OrderPayment,
    OrderResponse,
    OrderSummary,
    PayRequest,
)

SHIPPING_FEE = 30_000
CART_QTY_MAX = 99
ORDER_ALPHABET = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
ORDER_TRANSITIONS = {
    "pending": {"confirmed", "cancelled"},
    "confirmed": {"shipping", "cancelled"},
    "shipping": {"done"},
    "done": set(),
    "cancelled": set(),
}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def unit_price(product: Product) -> int:
    """Money is integer VND; a sale price always wins over the list price."""
    return product.sale_price if product.sale_price is not None else product.price


def resolve_voucher(
    db: Session, code: str, subtotal: int, *, lock: bool = False
) -> tuple[Voucher, int]:
    statement = select(Voucher).where(Voucher.code == code)
    if lock:
        statement = statement.with_for_update()
    voucher = db.scalar(statement)
    if voucher is None:
        raise HTTPException(404, "Voucher không tồn tại")
    if voucher.expired_at <= _now():
        raise HTTPException(409, "Voucher đã hết hạn")
    if voucher.qty_left <= 0:
        raise HTTPException(409, "Voucher đã hết lượt sử dụng")
    discount = min(subtotal * voucher.percent // 100, voucher.max_discount, subtotal)
    return voucher, discount


def _cart_rows(db: Session, user_id: int) -> list[tuple[CartItem, Product]]:
    return list(
        db.execute(
            select(CartItem, Product)
            .join(Product, Product.id == CartItem.product_id)
            .where(CartItem.user_id == user_id)
            .order_by(CartItem.id)
        ).all()
    )


def _quote(
    db: Session, rows: list[tuple[CartItem, Product]], voucher_code: str | None = None
) -> CartResponse:
    lines = [
        CartLine(
            id=item.id,
            product_id=product.id,
            slug=product.slug,
            name=product.name,
            unit_price=unit_price(product),
            qty=item.qty,
            line_total=unit_price(product) * item.qty,
            stock=product.stock,
        )
        for item, product in rows
    ]
    subtotal = sum(line.line_total for line in lines)
    applied: CartVoucher | None = None
    discount = 0
    if voucher_code and lines:
        voucher, discount = resolve_voucher(db, voucher_code, subtotal)
        applied = CartVoucher(
            code=voucher.code,
            percent=voucher.percent,
            max_discount=voucher.max_discount,
            discount=discount,
        )
    shipping_fee = SHIPPING_FEE if lines else 0
    return CartResponse(
        items=lines,
        subtotal=subtotal,
        discount=discount,
        shipping_fee=shipping_fee,
        total=max(subtotal - discount, 0) + shipping_fee,
        voucher=applied,
    )


def get_cart(db: Session, user_id: int, voucher_code: str | None = None) -> CartResponse:
    return _quote(db, _cart_rows(db, user_id), voucher_code)


def _ensure_available(product: Product, qty: int) -> None:
    if qty > CART_QTY_MAX:
        raise HTTPException(409, f"Số lượng tối đa {CART_QTY_MAX} mỗi sản phẩm")
    if product.stock <= 0:
        raise HTTPException(409, "Sản phẩm đã hết hàng")
    if qty > product.stock:
        raise HTTPException(409, f"Chỉ còn {product.stock} sản phẩm trong kho")


def _owned_item(db: Session, user_id: int, item_id: int) -> CartItem:
    item = db.scalar(select(CartItem).where(CartItem.id == item_id, CartItem.user_id == user_id))
    if item is None:
        raise HTTPException(404, "Sản phẩm không có trong giỏ hàng")
    return item


def add_item(db: Session, user_id: int, data: CartItemAdd) -> CartResponse:
    product = db.get(Product, data.product_id)
    if product is None:
        raise HTTPException(404, "Sản phẩm không tồn tại")
    item = db.scalar(
        select(CartItem).where(CartItem.user_id == user_id, CartItem.product_id == product.id)
    )
    qty = (item.qty if item else 0) + data.qty
    _ensure_available(product, qty)
    if item is None:
        db.add(CartItem(user_id=user_id, product_id=product.id, qty=qty))
    else:
        item.qty = qty
    db.commit()
    return get_cart(db, user_id)


def update_item(db: Session, user_id: int, item_id: int, qty: int) -> CartResponse:
    item = _owned_item(db, user_id, item_id)
    product = db.get(Product, item.product_id)
    if product is None:
        raise HTTPException(404, "Sản phẩm không tồn tại")
    _ensure_available(product, qty)
    item.qty = qty
    db.commit()
    return get_cart(db, user_id)


def delete_item(db: Session, user_id: int, item_id: int) -> CartResponse:
    item = _owned_item(db, user_id, item_id)
    db.delete(item)
    db.commit()
    return get_cart(db, user_id)


def apply_voucher(db: Session, user_id: int, code: str) -> CartResponse:
    rows = _cart_rows(db, user_id)
    if not rows:
        raise HTTPException(400, "Giỏ hàng đang trống")
    # Voucher is a price preview; checkout re-validates and consumes one turn atomically.
    return _quote(db, rows, code)


def _generate_order_code(db: Session) -> str:
    for _ in range(10):
        code = "EH-" + "".join(secrets.choice(ORDER_ALPHABET) for _ in range(4))
        if db.scalar(select(Order.id).where(Order.code == code)) is None:
            return code
    raise HTTPException(503, "Không sinh được mã đơn hàng, vui lòng thử lại")


def _order_response(db: Session, order: Order) -> OrderResponse:
    product_ids = [item.product_id for item in order.items]
    products = {
        product.id: product
        for product in db.scalars(select(Product).where(Product.id.in_(product_ids)))
    }
    lines = [
        OrderLine(
            product_id=item.product_id,
            slug=products[item.product_id].slug if item.product_id in products else None,
            name=(
                products[item.product_id].name
                if item.product_id in products
                else f"Sản phẩm #{item.product_id}"
            ),
            price=item.price,
            qty=item.qty,
            line_total=item.price * item.qty,
        )
        for item in order.items
    ]
    payment = order.payment
    return OrderResponse(
        code=order.code,
        status=order.status,
        subtotal=order.subtotal,
        discount=order.discount,
        shipping_fee=order.shipping_fee,
        total=order.total,
        voucher_code=order.voucher_code,
        address=OrderAddress(**order.address),
        created_at=order.created_at,
        items=lines,
        payment=(OrderPayment(method=payment.method, status=payment.status) if payment else None),
    )


def _summary_rows(db: Session, orders: list[Order]) -> list[OrderSummary]:
    counts: dict[int, int] = {}
    if orders:
        counts = dict(
            db.execute(
                select(OrderItem.order_id, func.sum(OrderItem.qty))
                .where(OrderItem.order_id.in_([order.id for order in orders]))
                .group_by(OrderItem.order_id)
            ).all()
        )
    return [
        OrderSummary(
            code=order.code,
            status=order.status,
            total=order.total,
            item_count=counts.get(order.id, 0),
            created_at=order.created_at,
        )
        for order in orders
    ]


def checkout(db: Session, user: User, data: CheckoutRequest) -> OrderResponse:
    rows = _cart_rows(db, user.id)
    if not rows:
        raise HTTPException(400, "Giỏ hàng đang trống")

    locked = {
        product.id: product
        for product in db.scalars(
            select(Product)
            .where(Product.id.in_([product.id for _, product in rows]))
            .with_for_update()
        )
    }
    subtotal = 0
    for item, product in rows:
        current = locked.get(item.product_id)
        if current is None:
            raise HTTPException(404, "Sản phẩm không tồn tại")
        if item.qty > current.stock:
            raise HTTPException(409, f"{current.name} chỉ còn {current.stock} sản phẩm trong kho")
        subtotal += unit_price(current) * item.qty

    voucher: Voucher | None = None
    discount = 0
    if data.voucher_code:
        voucher, discount = resolve_voucher(db, data.voucher_code, subtotal, lock=True)
    total = max(subtotal - discount, 0) + SHIPPING_FEE
    code = _generate_order_code(db)

    try:
        # Atomic guard: never trust the stock value read above when two carts race.
        for item, _ in rows:
            result = db.execute(
                update(Product)
                .where(Product.id == item.product_id, Product.stock >= item.qty)
                .values(stock=Product.stock - item.qty)
            )
            if result.rowcount != 1:
                raise HTTPException(409, "Sản phẩm vừa hết hàng, vui lòng kiểm tra lại giỏ")
        if voucher is not None:
            result = db.execute(
                update(Voucher)
                .where(Voucher.id == voucher.id, Voucher.qty_left >= 1)
                .values(qty_left=Voucher.qty_left - 1)
            )
            if result.rowcount != 1:
                raise HTTPException(409, "Voucher đã hết lượt sử dụng")

        order = Order(
            code=code,
            user_id=user.id,
            status="pending",
            subtotal=subtotal,
            discount=discount,
            shipping_fee=SHIPPING_FEE,
            total=total,
            voucher_code=data.voucher_code,
            address=OrderAddress(
                name=data.name, phone=data.phone, address=data.address
            ).model_dump(),
        )
        db.add(order)
        db.flush()
        for item, _ in rows:
            db.add(
                OrderItem(
                    order_id=order.id,
                    product_id=item.product_id,
                    price=unit_price(locked[item.product_id]),
                    qty=item.qty,
                )
            )
        db.add(
            Payment(
                order_id=order.id,
                method=data.payment_method,
                status="pending",
                payload={
                    "provider": "cod" if data.payment_method == "COD" else "chuyen_khoan_mock"
                },
            )
        )
        db.execute(delete(CartItem).where(CartItem.user_id == user.id))
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(order)
    return _order_response(db, order)


def list_user_orders(db: Session, user_id: int, page: int, page_size: int) -> OrderListResponse:
    total = db.scalar(select(func.count(Order.id)).where(Order.user_id == user_id)) or 0
    orders = list(
        db.scalars(
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.created_at.desc(), Order.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return OrderListResponse(
        items=_summary_rows(db, orders), total=total, page=page, page_size=page_size
    )


def list_all_orders(
    db: Session,
    *,
    status: str | None,
    query: str | None,
    page: int,
    page_size: int,
) -> OrderListResponse:
    filters = []
    if status:
        filters.append(Order.status == status)
    if query:
        filters.append(Order.code.like(f"%{query.strip().upper()}%"))
    total = db.scalar(select(func.count(Order.id)).where(*filters)) or 0
    orders = list(
        db.scalars(
            select(Order)
            .where(*filters)
            .order_by(Order.created_at.desc(), Order.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return OrderListResponse(
        items=_summary_rows(db, orders), total=total, page=page, page_size=page_size
    )


def _find_order(db: Session, code: str) -> Order:
    order = db.scalar(select(Order).where(Order.code == code.strip().upper()))
    if order is None:
        raise HTTPException(404, "Không tìm thấy đơn hàng")
    return order


def get_order_for_tracking(
    db: Session, code: str, user: User | None, phone: str | None
) -> OrderResponse:
    order = _find_order(db, code)
    allowed = user is not None and (user.id == order.user_id or user.role == "admin")
    if not allowed:
        if not phone:
            raise HTTPException(400, "Cần số điện thoại để tra cứu đơn hàng")
        if (order.address or {}).get("phone") != phone:
            raise HTTPException(404, "Không tìm thấy đơn hàng")
    return _order_response(db, order)


def pay_order(db: Session, user_id: int, code: str, data: PayRequest) -> OrderResponse:
    order = db.scalar(
        select(Order)
        .where(Order.code == code.strip().upper(), Order.user_id == user_id)
        .with_for_update()
    )
    if order is None:
        raise HTTPException(404, "Không tìm thấy đơn hàng")
    if order.status == "cancelled":
        raise HTTPException(409, "Đơn hàng đã bị hủy")
    payment = db.scalar(select(Payment).where(Payment.order_id == order.id).with_for_update())
    if payment is None:
        raise HTTPException(404, "Đơn hàng chưa có thông tin thanh toán")
    if payment.method != data.method:
        raise HTTPException(409, "Phương thức thanh toán không khớp với đơn hàng")
    if payment.status == "paid":
        raise HTTPException(409, "Đơn hàng đã được thanh toán")
    if payment.status == "refunded":
        raise HTTPException(409, "Đơn hàng đã được hoàn tiền")

    payload = dict(payment.payload or {})
    if data.method == "COD":
        # COD is collected on delivery; confirming it here does not mark the order paid.
        payload["confirmed_at"] = _now().isoformat()
    else:
        payment.status = "paid"
        payload.update(
            {
                "provider": "chuyen_khoan_mock",
                "paid_at": _now().isoformat(),
                "reference": f"MOCK-{secrets.token_hex(4).upper()}",
            }
        )
    payment.payload = payload
    db.commit()
    db.refresh(order)
    return _order_response(db, order)


def _restock(db: Session, order: Order) -> None:
    for item in order.items:
        db.execute(
            update(Product)
            .where(Product.id == item.product_id)
            .values(stock=Product.stock + item.qty)
        )
    if order.voucher_code:
        db.execute(
            update(Voucher)
            .where(Voucher.code == order.voucher_code)
            .values(qty_left=Voucher.qty_left + 1)
        )
    if order.payment is not None and order.payment.status == "paid":
        order.payment.status = "refunded"


def update_order_status(db: Session, code: str, data: AdminOrderUpdate) -> OrderResponse:
    order = db.scalar(select(Order).where(Order.code == code.strip().upper()).with_for_update())
    if order is None:
        raise HTTPException(404, "Không tìm thấy đơn hàng")
    if data.status == order.status:
        raise HTTPException(409, "Đơn hàng đã ở trạng thái này")
    if data.status not in ORDER_TRANSITIONS[order.status]:
        raise HTTPException(409, f"Không thể chuyển từ {order.status} sang {data.status}")
    try:
        if data.status == "cancelled":
            _restock(db, order)
        order.status = data.status
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(order)
    return _order_response(db, order)

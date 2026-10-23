from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cart import CartItem
from app.models.product import Product
from app.models.voucher import Voucher
from app.schemas.cart import (
    CartItemAdd,
    CartLine,
    CartResponse,
    CartVoucher,
)

SHIPPING_FEE = 30_000
CART_QTY_MAX = 99


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def unit_price(product: Product) -> int:
    """Money is integer VND; a sale price always wins over the list price."""
    return product.sale_price if product.sale_price is not None else product.price


def resolve_voucher(db: Session, code: str, subtotal: int) -> tuple[Voucher, int]:
    voucher = db.scalar(select(Voucher).where(Voucher.code == code))
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

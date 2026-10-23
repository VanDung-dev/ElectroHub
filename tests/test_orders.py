from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.voucher import Voucher
from tests.conftest import csrf_headers, login, register


def make_product(
    database,
    *,
    slug="esp32-devkit",
    sku="EH-001",
    name="ESP32 DevKit",
    price=100_000,
    sale_price=None,
    stock=10,
) -> int:
    with Session(database) as db:
        product = Product(
            slug=slug,
            sku=sku,
            name=name,
            price=price,
            sale_price=sale_price,
            stock=stock,
        )
        db.add(product)
        db.commit()
        db.refresh(product)
        return product.id


def make_voucher(
    database,
    *,
    code="WELCOME10",
    percent=10,
    max_discount=50_000,
    qty_left=5,
    expires_in_days=7,
) -> int:
    with Session(database) as db:
        voucher = Voucher(
            code=code,
            percent=percent,
            max_discount=max_discount,
            qty_left=qty_left,
            expired_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=expires_in_days),
        )
        db.add(voucher)
        db.commit()
        db.refresh(voucher)
        return voucher.id


def signed_in(client, email="customer@example.com"):
    response = register(client, email=email)
    assert response.status_code == 201
    assert login(client, email=email).status_code == 200
    return csrf_headers(client)


def add_to_cart(client, product_id, qty=1, headers=None):
    return client.post(
        "/api/v1/cart/items",
        json={"product_id": product_id, "qty": qty},
        headers=headers or csrf_headers(client),
    )


def test_cart_requires_login_and_csrf(client, database):
    product_id = make_product(database)
    assert client.get("/api/v1/cart").status_code == 401
    assert add_to_cart(client, product_id).status_code in {401, 403}
    signed_in(client)
    response = client.post("/api/v1/cart/items", json={"product_id": product_id, "qty": 1})
    assert (response.status_code, response.json()) == (
        403,
        {"detail": "CSRF token không hợp lệ"},
    )
    assert client.get("/api/v1/cart").json() == {
        "items": [],
        "subtotal": 0,
        "discount": 0,
        "shipping_fee": 0,
        "total": 0,
        "voucher": None,
    }


def test_cart_add_update_delete_uses_sale_price_and_integer_money(client, database):
    product_id = make_product(database, price=185_000, sale_price=165_000, stock=10)
    headers = signed_in(client)

    response = add_to_cart(client, product_id, 2, headers)
    assert response.status_code == 200
    cart = response.json()
    assert cart["items"] == [
        {
            "id": cart["items"][0]["id"],
            "product_id": product_id,
            "slug": "esp32-devkit",
            "name": "ESP32 DevKit",
            "unit_price": 165_000,
            "qty": 2,
            "line_total": 330_000,
            "stock": 10,
        }
    ]
    assert (cart["subtotal"], cart["shipping_fee"], cart["total"]) == (330_000, 30_000, 360_000)

    # Adding the same product accumulates instead of creating a second line.
    cart = add_to_cart(client, product_id, 1, headers).json()
    assert len(cart["items"]) == 1
    assert cart["items"][0]["qty"] == 3
    assert cart["total"] == 3 * 165_000 + 30_000

    item_id = cart["items"][0]["id"]
    cart = client.put(f"/api/v1/cart/items/{item_id}", json={"qty": 4}, headers=headers).json()
    assert cart["items"][0]["line_total"] == 660_000

    cart = client.delete(f"/api/v1/cart/items/{item_id}", headers=headers).json()
    assert cart["items"] == []
    assert cart["total"] == 0 and cart["shipping_fee"] == 0


@pytest.mark.parametrize(
    "qty,status,detail",
    [
        (0, 422, "Dữ liệu không hợp lệ"),
        (100, 422, "Dữ liệu không hợp lệ"),
        (4, 409, "Chỉ còn 3 sản phẩm trong kho"),
    ],
)
def test_cart_rejects_invalid_or_unavailable_qty(client, database, qty, status, detail):
    product_id = make_product(database, stock=3)
    headers = signed_in(client)
    response = add_to_cart(client, product_id, qty, headers)
    assert response.status_code == status
    assert response.json() == {"detail": detail}


def test_cart_rejects_missing_out_of_stock_and_accumulated_overflow(client, database):
    headers = signed_in(client)
    assert add_to_cart(client, 999, 1, headers).json() == {"detail": "Sản phẩm không tồn tại"}

    sold_out = make_product(database, slug="sold-out", sku="EH-002", stock=0)
    response = add_to_cart(client, sold_out, 1, headers)
    assert (response.status_code, response.json()) == (409, {"detail": "Sản phẩm đã hết hàng"})

    product_id = make_product(database, slug="esp32", sku="EH-003", stock=3)
    assert add_to_cart(client, product_id, 2, headers).status_code == 200
    response = add_to_cart(client, product_id, 2, headers)
    assert response.status_code == 409
    assert response.json() == {"detail": "Chỉ còn 3 sản phẩm trong kho"}

    response = add_to_cart(client, product_id, 99, headers)
    assert (response.status_code, response.json()) == (
        409,
        {"detail": "Số lượng tối đa 99 mỗi sản phẩm"},
    )


def test_cart_items_belong_to_the_signed_in_user(client, database):
    product_id = make_product(database)
    headers = signed_in(client)
    item_id = add_to_cart(client, product_id, 2, headers).json()["items"][0]["id"]

    other = signed_in(client, email="other@example.com")
    assert client.get("/api/v1/cart").json()["items"] == []
    response = client.put(f"/api/v1/cart/items/{item_id}", json={"qty": 1}, headers=other)
    assert (response.status_code, response.json()) == (
        404,
        {"detail": "Sản phẩm không có trong giỏ hàng"},
    )
    response = client.delete(f"/api/v1/cart/items/{item_id}", headers=other)
    assert response.status_code == 404


def test_cart_voucher_preview_discount_is_capped_and_not_consumed(client, database):
    product_id = make_product(database, price=500_000, stock=10)
    make_voucher(database, max_discount=40_000)
    headers = signed_in(client)
    assert add_to_cart(client, product_id, 1, headers).status_code == 200

    response = client.post(
        "/api/v1/cart/apply-voucher", json={"code": " welcome10 "}, headers=headers
    )
    assert response.status_code == 200
    cart = response.json()
    assert cart["voucher"] == {
        "code": "WELCOME10",
        "percent": 10,
        "max_discount": 40_000,
        "discount": 40_000,
    }
    assert (cart["subtotal"], cart["discount"], cart["total"]) == (500_000, 40_000, 490_000)

    with Session(database) as db:
        assert db.get(Voucher, 1).qty_left == 5  # preview only


@pytest.mark.parametrize(
    "kwargs,status,detail",
    [
        ({"expires_in_days": -1}, 409, "Voucher đã hết hạn"),
        ({"qty_left": 0}, 409, "Voucher đã hết lượt sử dụng"),
    ],
)
def test_cart_voucher_rejects_expired_or_exhausted(client, database, kwargs, status, detail):
    product_id = make_product(database)
    make_voucher(database, **kwargs)
    headers = signed_in(client)
    add_to_cart(client, product_id, 1, headers)
    response = client.post(
        "/api/v1/cart/apply-voucher", json={"code": "WELCOME10"}, headers=headers
    )
    assert (response.status_code, response.json()) == (status, {"detail": detail})


def test_cart_voucher_rejects_unknown_and_empty_cart(client, database):
    headers = signed_in(client)
    response = client.post("/api/v1/cart/apply-voucher", json={"code": "NOPE"}, headers=headers)
    assert (response.status_code, response.json()) == (
        400,
        {"detail": "Giỏ hàng đang trống"},
    )

    product_id = make_product(database)
    add_to_cart(client, product_id, 1, headers)
    response = client.post("/api/v1/cart/apply-voucher", json={"code": "NOPE"}, headers=headers)
    assert (response.status_code, response.json()) == (
        404,
        {"detail": "Voucher không tồn tại"},
    )

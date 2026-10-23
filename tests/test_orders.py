from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.order import Order, OrderItem
from app.models.payment import Payment
from app.models.product import Product
from app.models.user import User
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


def checkout(client, headers, **overrides):
    return client.post(
        "/api/v1/orders",
        json={
            "name": "Khách hàng",
            "phone": "0901234567",
            "address": "269/20 Lý Thường Kiệt, TP.HCM",
            "payment_method": "COD",
            **overrides,
        },
        headers=headers,
    )


def make_admin(client, database, email="admin@example.com"):
    register(client, email=email, name="Quản trị")
    with Session(database) as db:
        db.scalar(select(User).where(User.email == email)).role = "admin"
        db.commit()
    assert login(client, email=email).status_code == 200
    return csrf_headers(client)


def test_checkout_creates_order_decrements_stock_and_clears_cart(client, database):
    product_id = make_product(database, price=100_000, sale_price=90_000, stock=5)
    make_voucher(database, percent=10, max_discount=100_000)
    headers = signed_in(client)
    assert add_to_cart(client, product_id, 2, headers).status_code == 200

    response = checkout(client, headers, voucher_code="welcome10")
    assert response.status_code == 201
    order = response.json()
    assert order["code"].startswith("EH-") and len(order["code"]) == 7
    assert order["status"] == "pending"
    assert (order["subtotal"], order["discount"], order["shipping_fee"]) == (
        180_000,
        18_000,
        30_000,
    )
    assert order["total"] == 192_000
    assert order["voucher_code"] == "WELCOME10"
    assert order["address"]["phone"] == "0901234567"
    assert order["payment"] == {"method": "COD", "status": "pending"}
    assert order["items"] == [
        {
            "product_id": product_id,
            "slug": "esp32-devkit",
            "name": "ESP32 DevKit",
            "price": 90_000,
            "qty": 2,
            "line_total": 180_000,
        }
    ]

    with Session(database) as db:
        assert db.get(Product, product_id).stock == 3
        assert db.get(Voucher, 1).qty_left == 4
        saved = db.scalar(select(Order))
        assert saved.code == order["code"] and saved.total == 192_000
        assert saved.address["name"] == "Khách hàng"
        assert db.scalar(select(OrderItem)).price == 90_000
        assert db.scalar(select(Payment)).method == "COD"

    assert client.get("/api/v1/cart").json()["items"] == []
    history = client.get("/api/v1/orders").json()
    assert history["total"] == 1 and history["page_size"] == 10
    assert history["items"][0]["item_count"] == 2


def test_checkout_rejects_empty_cart_and_invalid_payload(client, database):
    headers = signed_in(client)
    response = checkout(client, headers)
    assert (response.status_code, response.json()) == (
        400,
        {"detail": "Giỏ hàng đang trống"},
    )

    product_id = make_product(database)
    add_to_cart(client, product_id, 1, headers)
    assert checkout(client, headers, phone="12345").status_code == 422
    assert checkout(client, headers, payment_method="VNPAY").status_code == 422
    assert checkout(client, headers, extra="x").status_code == 422


def test_checkout_rejects_stock_changed_after_cart_added(client, database):
    product_id = make_product(database, name="STM32", stock=5)
    headers = signed_in(client)
    add_to_cart(client, product_id, 2, headers)
    with Session(database) as db:
        db.get(Product, product_id).stock = 1
        db.commit()

    response = checkout(client, headers)
    assert (response.status_code, response.json()) == (
        409,
        {"detail": "STM32 chỉ còn 1 sản phẩm trong kho"},
    )
    with Session(database) as db:
        assert db.get(Product, product_id).stock == 1
        assert db.scalar(select(Order)) is None
    assert len(client.get("/api/v1/cart").json()["items"]) == 1


def test_checkout_is_atomic_when_a_later_line_is_short(client, database):
    first = make_product(database, slug="first", sku="EH-101", stock=5)
    second = make_product(database, slug="second", sku="EH-102", stock=5)
    headers = signed_in(client)
    add_to_cart(client, first, 2, headers)
    add_to_cart(client, second, 2, headers)
    with Session(database) as db:
        db.get(Product, second).stock = 0
        db.commit()

    assert checkout(client, headers).status_code == 409
    with Session(database) as db:
        assert db.get(Product, first).stock == 5
        assert db.get(Product, second).stock == 0
        assert db.scalar(select(Order)) is None
        assert len(db.scalars(select(OrderItem)).all()) == 0
    assert len(client.get("/api/v1/cart").json()["items"]) == 2


@pytest.mark.parametrize(
    "method,paid",
    [("COD", False), ("CHUYEN_KHOAN_MOCK", True)],
)
def test_pay_cod_confirms_and_transfer_mock_marks_paid(client, database, method, paid):
    product_id = make_product(database)
    headers = signed_in(client)
    add_to_cart(client, product_id, 1, headers)
    code = checkout(client, headers, payment_method=method).json()["code"]

    response = client.post(f"/api/v1/orders/{code}/pay", json={"method": method}, headers=headers)
    assert response.status_code == 200
    payment = response.json()["payment"]
    assert payment["status"] == ("paid" if paid else "pending")
    if paid:
        with Session(database) as db:
            saved = db.scalar(select(Payment))
            assert saved.status == "paid" and saved.payload["reference"].startswith("MOCK-")
        response = client.post(
            f"/api/v1/orders/{code}/pay", json={"method": method}, headers=headers
        )
        assert (response.status_code, response.json()) == (
            409,
            {"detail": "Đơn hàng đã được thanh toán"},
        )


def test_pay_rejects_wrong_method_and_other_users_order(client, database):
    product_id = make_product(database)
    headers = signed_in(client)
    add_to_cart(client, product_id, 1, headers)
    code = checkout(client, headers).json()["code"]
    response = client.post(
        f"/api/v1/orders/{code}/pay",
        json={"method": "CHUYEN_KHOAN_MOCK"},
        headers=headers,
    )
    assert (response.status_code, response.json()) == (
        409,
        {"detail": "Phương thức thanh toán không khớp với đơn hàng"},
    )

    other = signed_in(client, email="other@example.com")
    response = client.post(f"/api/v1/orders/{code}/pay", json={"method": "COD"}, headers=other)
    assert (response.status_code, response.json()) == (
        404,
        {"detail": "Không tìm thấy đơn hàng"},
    )


def test_tracking_requires_code_and_phone_but_owner_skips_phone(client, database):
    product_id = make_product(database)
    headers = signed_in(client)
    add_to_cart(client, product_id, 1, headers)
    code = checkout(client, headers).json()["code"]

    assert client.get(f"/api/v1/orders/{code}").status_code == 200
    client.cookies.clear()
    assert client.get(f"/api/v1/orders/{code}").status_code == 400
    assert client.get(f"/api/v1/orders/{code}?phone=0999999999").status_code == 404
    assert client.get(f"/api/v1/orders/{code}?phone=0901234567").status_code == 200
    assert client.get(f"/api/v1/orders/{code.lower()}?phone=0901234567").status_code == 200
    assert client.get("/api/v1/orders/EH-0000?phone=0901234567").status_code == 404


def test_order_history_is_scoped_to_the_signed_in_user(client, database):
    product_id = make_product(database)
    headers = signed_in(client)
    add_to_cart(client, product_id, 1, headers)
    checkout(client, headers)

    signed_in(client, email="other@example.com")
    history = client.get("/api/v1/orders").json()
    assert history["items"] == [] and history["total"] == 0


def test_admin_order_status_transitions_and_cancel_restores_stock_and_voucher(client, database):
    product_id = make_product(database, stock=5)
    make_voucher(database, qty_left=5)
    customer = signed_in(client)
    add_to_cart(client, product_id, 2, customer)
    code = checkout(client, customer, voucher_code="WELCOME10").json()["code"]

    assert client.get("/api/v1/admin/orders").status_code == 403
    client.post("/api/v1/auth/logout", headers=customer)
    assert client.get("/api/v1/admin/orders").status_code == 401

    admin = make_admin(client, database)
    listing = client.get("/api/v1/admin/orders").json()
    assert listing["total"] == 1 and listing["items"][0]["code"] == code
    assert client.get("/api/v1/admin/orders?status=done").json()["total"] == 0
    assert client.get(f"/api/v1/admin/orders?q={code[3:]}").json()["total"] == 1

    response = client.patch(
        f"/api/v1/admin/orders/{code}", json={"status": "shipping"}, headers=admin
    )
    assert response.status_code == 409
    for target in ["confirmed", "shipping", "done"]:
        response = client.patch(
            f"/api/v1/admin/orders/{code}", json={"status": target}, headers=admin
        )
        assert response.status_code == 200 and response.json()["status"] == target
    response = client.patch(f"/api/v1/admin/orders/{code}", json={"status": "done"}, headers=admin)
    assert response.status_code == 409

    with Session(database) as db:
        assert db.get(Product, product_id).stock == 3
        assert db.get(Voucher, 1).qty_left == 4

    # A second, paid order can still be cancelled: stock and voucher turn come back.
    login(client, email="customer@example.com")
    headers = csrf_headers(client)
    add_to_cart(client, product_id, 1, headers)
    cancel_code = checkout(client, headers, payment_method="CHUYEN_KHOAN_MOCK").json()["code"]
    client.post(
        f"/api/v1/orders/{cancel_code}/pay",
        json={"method": "CHUYEN_KHOAN_MOCK"},
        headers=headers,
    )
    admin = make_admin(client, database)
    response = client.patch(
        f"/api/v1/admin/orders/{cancel_code}",
        json={"status": "cancelled"},
        headers=admin,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["payment"]["status"] == "refunded"
    with Session(database) as db:
        assert db.get(Product, product_id).stock == 3
        assert db.get(Voucher, 1).qty_left == 4
        cancelled = db.scalar(select(Order).where(Order.code == cancel_code))
        assert db.scalar(select(Payment).where(Payment.order_id == cancelled.id)).status == (
            "refunded"
        )


def test_sales_mutations_require_csrf(client, database):
    product_id = make_product(database)
    signed_in(client)
    assert (
        client.post(
            "/api/v1/orders",
            json={
                "name": "Khách",
                "phone": "0901234567",
                "address": "269/20 Lý Thường Kiệt",
            },
        ).status_code
        == 403
    )
    add_to_cart(client, product_id, 1)
    headers = csrf_headers(client)
    assert client.post("/api/v1/orders", json={}, headers=headers).status_code == 422

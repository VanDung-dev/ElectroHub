from datetime import datetime

from sqlalchemy.orm import Session

from app.models.order import Order, OrderItem
from app.models.payment import Payment
from app.models.product import Product
from app.models.user import User
from tests.conftest import login, register


def _create_sample_orders(db: Session):
    user = db.query(User).filter_by(role="admin").first()
    if not user:
        user = User(email="admin@test.com", name="Admin User", role="admin")
        db.add(user)
        db.flush()

    p1 = Product(
        name="ESP32 DevKit V1",
        slug="esp32-devkit-v1",
        sku="ESP32-DEV-01",
        price=120000,
        stock=50,
    )
    p2 = Product(
        name="Raspberry Pi 4 Model B",
        slug="raspberry-pi-4",
        sku="RPI4-4GB",
        price=1800000,
        stock=20,
    )
    p3 = Product(
        name="Cảm biến nhiệt độ DHT22",
        slug="cam-bien-dht22",
        sku="DHT22-SEN",
        price=65000,
        stock=100,
    )
    db.add_all([p1, p2, p3])
    db.flush()

    # Order 1: Nov 2026, confirmed, VNPAY
    o1 = Order(
        code="ORD-NOV-01",
        user_id=user.id,
        status="done",
        subtotal=240000,
        discount=20000,
        vat=0,
        shipping_fee=30000,
        total=250000,
        address={"name": "Khách A", "phone": "0900000001", "address": "TP HCM"},
        created_at=datetime(2026, 11, 2, 10, 0, 0),
    )
    db.add(o1)
    db.flush()
    db.add(OrderItem(order_id=o1.id, product_id=p1.id, price=120000, qty=2))
    db.add(
        Payment(
            order_id=o1.id,
            method="VNPAY",
            status="paid",
            provider="vnpay",
            currency="VND",
            amount_minor=25000000,
        )
    )

    # Order 2: Nov 2026, confirmed, PAYPAL
    o2 = Order(
        code="ORD-NOV-02",
        user_id=user.id,
        status="confirmed",
        subtotal=1800000,
        discount=0,
        vat=0,
        shipping_fee=0,
        total=1800000,
        address={"name": "Khách B", "phone": "0900000002", "address": "Hà Nội"},
        created_at=datetime(2026, 11, 5, 14, 0, 0),
    )
    db.add(o2)
    db.flush()
    db.add(OrderItem(order_id=o2.id, product_id=p2.id, price=1800000, qty=1))
    db.add(
        Payment(
            order_id=o2.id,
            method="PAYPAL",
            status="paid",
            provider="paypal",
            currency="USD",
            amount_minor=7200,
        )
    )

    # Order 3: Oct 2026 (previous month), done, VNPAY
    o3 = Order(
        code="ORD-OCT-01",
        user_id=user.id,
        status="done",
        subtotal=130000,
        discount=0,
        vat=0,
        shipping_fee=20000,
        total=150000,
        address={"name": "Khách C", "phone": "0900000003", "address": "Đà Nẵng"},
        created_at=datetime(2026, 10, 15, 9, 0, 0),
    )
    db.add(o3)
    db.flush()
    db.add(OrderItem(order_id=o3.id, product_id=p3.id, price=65000, qty=2))
    db.add(
        Payment(
            order_id=o3.id,
            method="VNPAY",
            status="paid",
            provider="vnpay",
            currency="VND",
            amount_minor=15000000,
        )
    )

    # Order 4: Cancelled order (should NOT count as paid revenue)
    o4 = Order(
        code="ORD-NOV-CAN",
        user_id=user.id,
        status="cancelled",
        subtotal=500000,
        discount=0,
        vat=0,
        shipping_fee=30000,
        total=530000,
        address={"name": "Khách D", "phone": "0900000004", "address": "Cần Thơ"},
        created_at=datetime(2026, 11, 6, 11, 0, 0),
    )
    db.add(o4)
    db.commit()


def test_revenue_report_period_filtering_and_comparison(client, database):
    register(client, email="admin_rev@example.com", name="Admin User")
    with Session(database) as db:
        user = db.query(User).filter_by(email="admin_rev@example.com").first()
        user.role = "admin"
        db.commit()
        _create_sample_orders(db)

    login(client, email="admin_rev@example.com")

    # 1. Test filtering by month (November 2026)
    res_nov = client.get("/api/v1/auth/admin/revenue?period_type=month&year=2026&month=11")
    assert res_nov.status_code == 200
    data_nov = res_nov.json()

    assert data_nov["period"]["label"] == "Tháng 11/2026"
    assert data_nov["period"]["prev_label"] == "Tháng 10/2026"
    # Nov paid orders: o1 (250,000) + o2 (1,800,000) = 2,050,000
    assert data_nov["total_revenue"] == 2050000
    assert data_nov["vnpay_revenue"] == 250000
    assert data_nov["paypal_revenue"] == 1800000
    assert data_nov["kpis"]["completed_orders"] == 2
    assert data_nov["kpis"]["cancelled_orders"] == 1
    assert data_nov["kpis"]["total_orders"] == 3
    # Compare with October 2026 (prev_revenue = 150,000)
    assert data_nov["kpis"]["prev_revenue"] == 150000
    assert data_nov["kpis"]["revenue_growth"] > 0

    # Verify top products in November
    top = data_nov["top_products"]
    assert len(top) == 2
    # Product 2 (Raspberry Pi) had 1,800,000 revenue
    assert top[0]["name"] == "Raspberry Pi 4 Model B"
    assert top[0]["revenue"] == 1800000
    # Product 1 (ESP32) had 240,000 revenue (2 x 120,000)
    assert top[1]["name"] == "ESP32 DevKit V1"
    assert top[1]["quantity_sold"] == 2

    # 2. Test filtering by quarter (Q4 2026 includes Oct and Nov)
    res_q4 = client.get("/api/v1/auth/admin/revenue?period_type=quarter&year=2026&quarter=4")
    assert res_q4.status_code == 200
    data_q4 = res_q4.json()
    assert data_q4["period"]["label"] == "Quý 4/2026"
    # Total Q4: 250,000 + 1,800,000 + 150,000 = 2,200,000
    assert data_q4["total_revenue"] == 2200000
    assert data_q4["kpis"]["completed_orders"] == 3

    # 3. Test filtering by year (2026)
    res_y = client.get("/api/v1/auth/admin/revenue?period_type=year&year=2026")
    assert res_y.status_code == 200
    data_y = res_y.json()
    assert data_y["period"]["label"] == "Năm 2026"
    assert len(data_y["timeline_comparison"]["labels"]) == 12

    # 4. Test CSV export endpoint
    res_csv = client.get("/api/v1/auth/admin/revenue/export?period_type=month&year=2026&month=11")
    assert res_csv.status_code == 200
    assert res_csv.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=" in res_csv.headers["content-disposition"]
    csv_text = res_csv.text
    assert "BÁO CÁO DOANH THU" in csv_text
    assert "Tháng 11/2026" in csv_text
    assert "Raspberry Pi 4 Model B" in csv_text
    assert "ORD-NOV-01" in csv_text

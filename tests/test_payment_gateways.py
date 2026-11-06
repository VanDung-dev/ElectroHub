from urllib.parse import parse_qs, urlparse

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.order import Order
from app.models.payment import Payment
from app.services.payments import paypal, service, vnpay
from tests.test_orders import add_to_cart, checkout, make_product, signed_in


def sandbox_settings(**overrides) -> Settings:
    values = {
        "secret_key": "s" * 48,
        "database_url": "sqlite://",
        "payment_mode": "sandbox",
        "vnpay_tmn_code": "TESTCODE",
        "vnpay_hash_secret": SecretStr("test-secret"),
        "paypal_client_id": "client-id",
        "paypal_client_secret": SecretStr("client-secret"),
        "site_url": "https://demo.example",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_vnpay_sign_verify_roundtrip_and_tamper():
    params = {
        "vnp_Amount": "13000000",
        "vnp_OrderInfo": "Thanh toan don hang EH-ABCD",
        "vnp_TxnRef": "EHABCD01",
        "vnp_ReturnUrl": "https://demo.example/payments/vnpay/return",
    }
    signature = vnpay.sign_params(params, "secret")
    signed = {**params, "vnp_SecureHash": signature}

    assert vnpay.verify_callback(signed, "secret") is True
    assert vnpay.verify_callback({**signed, "vnp_Amount": "1"}, "secret") is False
    assert vnpay.verify_callback({**signed, "vnp_SecureHash": "0" * 128}, "secret") is False


def test_vnpay_build_url_signs_amount_and_derives_return_url():
    settings = sandbox_settings()
    url = vnpay.build_payment_url(
        settings,
        txn_ref="EHABCD01",
        amount_vnd=130_000,
        order_info="Thanh toán đơn hàng EH-ABCD",
        ip_addr="127.0.0.1",
    )
    query = {key: value[0] for key, value in parse_qs(urlparse(url).query).items()}

    assert query["vnp_Amount"] == "13000000"
    assert query["vnp_ReturnUrl"] == "https://demo.example/payments/vnpay/return"
    assert query["vnp_TxnRef"] == "EHABCD01"
    assert vnpay.verify_callback(query, "test-secret") is True
    assert vnpay.callback_params(query)["vnp_TmnCode"] == "TESTCODE"


def test_vnpay_callback_maps_success_and_failure():
    paid = vnpay.outcome_from_callback(
        {"vnp_ResponseCode": "00", "vnp_TransactionStatus": "00", "vnp_Amount": "100"}
    )
    failed = vnpay.outcome_from_callback(
        {"vnp_ResponseCode": "24", "vnp_TransactionStatus": "02", "vnp_Amount": "100"}
    )
    assert (paid.status, paid.amount_minor) == ("paid", 100)
    assert failed.status == "failed"
    assert failed.provider_status == "02"


def test_paypal_vnd_to_usd_rounds_to_cents():
    settings = sandbox_settings()
    assert paypal.vnd_to_usd_minor(settings, 250_000) == 1000
    assert paypal.vnd_to_usd_minor(settings, 25_400) == 102
    assert paypal.vnd_to_usd_minor(settings, 1) == 1
    assert paypal.minor_to_value(1000) == "10.00"


def test_paypal_webhook_event_mapping():
    event = {
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "id": "CAPTURE-1",
            "status": "COMPLETED",
            "amount": {"currency_code": "USD", "value": "10.00"},
            "supplementary_data": {"related_ids": {"order_id": "PAYPAL-ORDER-1"}},
        },
    }
    kind, status, txn_id, amount_minor, currency, order_id, _ = paypal.webhook_event(event)
    assert (kind, status, txn_id, amount_minor, currency, order_id) == (
        "payment",
        "paid",
        "CAPTURE-1",
        1000,
        "USD",
        "PAYPAL-ORDER-1",
    )


def test_txn_ref_is_alphanumeric_and_changes_per_attempt():
    assert service._txn_ref("EH-A1B2", 1) == "EHA1B201"
    assert service._txn_ref("EH-A1B2", 2) == "EHA1B202"
    assert service._txn_ref("EH-A1B2", 1).isalnum()


def test_sandbox_vnpay_session_builds_url_and_blocks_simulate(client, database, monkeypatch):
    settings = sandbox_settings()
    for target in (
        "app.services.order_service.get_settings",
        "app.services.payments.service.get_settings",
        "app.routers.payments.get_settings",
    ):
        monkeypatch.setattr(target, lambda: settings)

    product_id = make_product(database, price=100_000, stock=5)
    headers = signed_in(client)
    add_to_cart(client, product_id, 1, headers)
    code = checkout(client, headers, payment_method="VNPAY").json()["code"]

    response = client.post(f"/api/v1/payments/orders/{code}/session", json={}, headers=headers)
    assert response.status_code == 200
    session = response.json()
    assert session["provider"] == "vnpay" and session["simulation"] is False
    assert session["currency"] == "VND" and session["amount_minor"] == 14_000_000
    query = {key: value[0] for key, value in parse_qs(urlparse(session["url"]).query).items()}
    assert vnpay.verify_callback(query, "test-secret") is True

    blocked = client.post(
        f"/api/v1/payments/orders/{code}/simulate",
        json={"result": "paid"},
        headers=headers,
    )
    assert blocked.status_code == 409

    with Session(database) as db:
        order_id = db.scalar(select(Order.id).where(Order.code == code))
        payment = db.scalar(select(Payment).where(Payment.order_id == order_id))
        assert payment is not None
        assert payment.provider == "vnpay"
        assert payment.txn_ref and payment.attempt == 1


def test_vnpay_ipn_rejects_bad_signature_and_paypal_webhook_skips_csrf(client):
    ipn = client.get("/api/v1/payments/vnpay/ipn?vnp_TxnRef=NOPE")
    assert ipn.status_code == 200 and ipn.json()["RspCode"] == "97"

    # No CSRF header: webhooks must not be rejected by the global dependency.
    webhook = client.post("/api/v1/payments/paypal/webhook", json={})
    assert webhook.status_code == 200 and webhook.json() == {"status": "ignored"}

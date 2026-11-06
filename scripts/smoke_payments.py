"""End-to-end sandbox smoke test against the Docker stack (SQL Server + app).

Prerequisites:
    docker compose up -d --build
    .env with PAYMENT_MODE=sandbox, VNPAY_TMN_CODE, VNPAY_HASH_SECRET,
    MSSQL_SA_PASSWORD and working PayPal sandbox credentials.

Run from the repository root:
    python3 scripts/smoke_payments.py

The script signs a VNPAY IPN locally, so VNPAY has no matching transaction and
its live refund API answers 99. That failure is asserted, then the payment is
switched to the mock provider to exercise the successful refund path.
"""

import hashlib
import hmac
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote_plus

import httpx

BASE = os.environ.get("SMOKE_BASE", "http://localhost:8000")
GMT7 = timezone(timedelta(hours=7))
DEMO_PASSWORD = "Demo@2026!"


def load_env() -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in Path(".env").read_text().splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    )


ENV = load_env()
SECRET = ENV["VNPAY_HASH_SECRET"]
TMN = ENV["VNPAY_TMN_CODE"]
client = httpx.Client(base_url=BASE, timeout=60, follow_redirects=False)


def sql(query: str) -> str:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "-e",
            f"SQLCMDPASSWORD={ENV['MSSQL_SA_PASSWORD']}",
            "sqlserver",
            "/opt/mssql-tools18/bin/sqlcmd",
            "-S",
            "localhost",
            "-U",
            "sa",
            "-C",
            "-d",
            "ElectroHub",
            "-b",
            "-h",
            "-1",
            "-W",
            "-Q",
            "SET NOCOUNT ON; SET QUOTED_IDENTIFIER ON; " + query,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise SystemExit(f"SQL ERROR: {result.stdout[-500:]} {result.stderr[-500:]}")
    return result.stdout


def scalar(query: str) -> str:
    lines = [line.strip() for line in sql(query).splitlines() if line.strip()]
    return lines[0] if lines else ""


def csrf() -> dict[str, str]:
    token = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    return {"X-CSRF-Token": token}


def login(email: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": DEMO_PASSWORD},
        headers=csrf(),
    )
    assert response.status_code == 200, response.text


def logout() -> None:
    client.post("/api/v1/auth/logout", headers=csrf())


def sign(params: dict[str, str]) -> tuple[str, str]:
    data = "&".join(
        f"{quote_plus(key)}={quote_plus(str(value))}"
        for key, value in sorted(params.items())
        if value not in (None, "")
    )
    return data, hmac.new(SECRET.encode(), data.encode(), hashlib.sha512).hexdigest()


def new_order(method: str = "VNPAY") -> tuple[str, int]:
    product = client.get("/api/v1/products").json()["items"][0]
    client.post(
        "/api/v1/cart/items",
        json={"product_id": product["id"], "qty": 1},
        headers=csrf(),
    )
    response = client.post(
        "/api/v1/orders",
        json={
            "name": "Khach Smoke",
            "phone": "0901234567",
            "address": "269 Ly Thuong Kiet, TP.HCM",
            "payment_method": method,
        },
        headers=csrf(),
    )
    assert response.status_code == 201, response.text
    return response.json()["code"], product["id"]


def pay_via_ipn(code: str) -> dict:
    session = client.post(f"/api/v1/payments/orders/{code}/session", json={}, headers=csrf())
    assert session.status_code == 200, session.text
    assert session.json()["url"].startswith("https://sandbox.vnpayment.vn"), session.text
    details = client.get(f"/api/v1/payments/orders/{code}").json()
    params = {
        "vnp_TmnCode": TMN,
        "vnp_TxnRef": code.replace("-", "") + "01",
        "vnp_Amount": str(details["total"] * 100),
        "vnp_OrderInfo": f"Thanh toan don hang {code}",
        "vnp_ResponseCode": "00",
        "vnp_TransactionStatus": "00",
        "vnp_TransactionNo": "SMOKE" + code.replace("-", ""),
        "vnp_BankCode": "NCB",
        "vnp_PayDate": datetime.now(GMT7).strftime("%Y%m%d%H%M%S"),
    }
    data, signature = sign(params)
    ipn = client.get(f"/api/v1/payments/vnpay/ipn?{data}&vnp_SecureHash={signature}")
    assert ipn.json()["RspCode"] == "00", ipn.text
    details = client.get(f"/api/v1/payments/orders/{code}").json()
    assert details["status"] == "paid", details
    print(f"  IPN paid {code}: {details['currency']} {details['amount_minor']}")
    return details


def payment_state(refund_id: int) -> str:
    return scalar(
        "SELECT CONCAT(r.status, '|', p.status) "
        "FROM refunds r JOIN payments p ON p.id=r.payment_id "
        f"WHERE r.id={refund_id};"
    )


def main() -> None:
    assert ENV.get("PAYMENT_MODE") == "sandbox", "set PAYMENT_MODE=sandbox in .env"

    print("1) VNPAY signed IPN -> paid")
    login("customer.demo@example.com")
    code, product_id = new_order()
    stock_before = int(scalar(f"SELECT stock FROM products WHERE id={product_id};"))
    pay_via_ipn(code)

    print("2) Cancel paid order -> held refund + immediate restock")
    cancelled = client.post(
        f"/api/v1/orders/{code}/cancel", json={"reason": "Smoke refund"}, headers=csrf()
    )
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    refund = body["refund"]
    assert body["status"] == "cancelled"
    assert body["payment"]["status"] == "refund_pending"
    assert refund["status"] == "scheduled"
    stock_after = int(scalar(f"SELECT stock FROM products WHERE id={product_id};"))
    assert stock_after == stock_before + 1, (stock_before, stock_after)
    print(
        f"  refund #{refund['id']} scheduled until {refund['due_at']}, "
        f"stock {stock_before}->{stock_after}"
    )

    print("3) Admin may not confirm before the hold window")
    logout()
    login("manager.demo@example.com")
    early = client.post(f"/api/v1/admin/refunds/{refund['id']}/confirm", json={}, headers=csrf())
    assert early.status_code == 409, early.text
    print(f"  409 as expected: {early.json()['detail']}")

    print("4) After the hold window the shop confirms and the gateway refund runs")
    sql(f"UPDATE refunds SET due_at=DATEADD(minute,-1,SYSUTCDATETIME()) WHERE id={refund['id']};")
    due = client.get("/api/v1/admin/refunds?due=1").json()
    assert any(item["id"] == refund["id"] for item in due["items"]), due
    confirmed = client.post(
        f"/api/v1/admin/refunds/{refund['id']}/confirm", json={}, headers=csrf()
    )
    assert confirmed.status_code == 200, confirmed.text
    if confirmed.json()["status"] != "succeeded":
        assert confirmed.json()["status"] == "failed", confirmed.text
        print("  VNPAY refused the refund for the simulated transaction; retrying as mock")
        sql(
            "UPDATE payments SET provider='mock' WHERE id="
            f"(SELECT payment_id FROM refunds WHERE id={refund['id']});"
        )
        confirmed = client.post(
            f"/api/v1/admin/refunds/{refund['id']}/confirm", json={}, headers=csrf()
        )
        assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "succeeded"
    state = payment_state(refund["id"])
    assert state == "succeeded|refunded", state
    print(f"  refund succeeded, payment refunded ({state})")

    print("5) Rejecting a refund keeps the captured payment")
    logout()
    login("customer.demo@example.com")
    reject_code, _ = new_order()
    pay_via_ipn(reject_code)
    cancelled = client.post(
        f"/api/v1/orders/{reject_code}/cancel",
        json={"reason": "Smoke reject"},
        headers=csrf(),
    )
    assert cancelled.status_code == 200, cancelled.text
    reject_id = cancelled.json()["refund"]["id"]
    logout()
    login("manager.demo@example.com")
    rejected = client.post(
        f"/api/v1/admin/refunds/{reject_id}/reject",
        json={"reason": "Hang da giao dung"},
        headers=csrf(),
    )
    assert rejected.status_code == 200, rejected.text
    state = payment_state(reject_id)
    assert state == "rejected|paid", state
    print(f"  refund rejected, payment back to paid ({state})")

    print("6) PayPal sandbox session still creates a real order")
    logout()
    login("customer.demo@example.com")
    pp_code, _ = new_order("PAYPAL")
    session = client.post(f"/api/v1/payments/orders/{pp_code}/session", json={}, headers=csrf())
    assert session.status_code == 200, session.text
    data = session.json()
    assert data["provider"] == "paypal" and data["currency"] == "USD", data
    assert data["url"].startswith("https://www.sandbox.paypal.com"), data
    print(f"  PayPal {data['currency']} {data['amount_minor']} cents -> {data['url'][:48]}...")

    print("7) UI pages respond")
    for path in ("/payments/" + pp_code, "/admin/orders"):
        print(f"  {path} -> {client.get(path).status_code}")

    print("SMOKE OK")


if __name__ == "__main__":
    main()

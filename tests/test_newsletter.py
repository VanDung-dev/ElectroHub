from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.newsletter import EmailCampaign, NewsletterSubscriber
from app.models.user import User
from app.routers.newsletter import _unsubscribe_token
from app.services import email_service
from tests.conftest import csrf_headers, login, register


def make_admin(client, database, email="admin@example.com"):
    register(client, email=email, name="Quản trị")
    with Session(database) as db:
        user = db.scalar(select(User).where(User.email == email))
        user.role = "admin"
        db.commit()
    assert login(client, email=email).status_code == 200
    return csrf_headers(client)


def test_subscribe_creates_subscriber_and_duplicate_handles_gracefully(client, database, monkeypatch):
    sent_emails = []

    def fake_send_smtp(to_email, subject, text_content, html_content=None):
        sent_emails.append((to_email, subject, text_content, html_content))
        return True

    monkeypatch.setattr(email_service, "send_smtp_message", fake_send_smtp)

    # 1. Subscribe new email
    res = client.post(
        "/api/v1/newsletter/subscribe",
        json={"email": "tester@electrohub.vn", "consent": True},
        headers=csrf_headers(client),
    )
    assert res.status_code == 201
    assert "Đăng ký nhận tin thành công" in res.json()["detail"]

    # Verify in DB
    with Session(database) as db:
        sub = db.scalar(select(NewsletterSubscriber).where(NewsletterSubscriber.email == "tester@electrohub.vn"))
        assert sub is not None

    # Verify background task sent welcome email
    assert len(sent_emails) == 1
    assert sent_emails[0][0] == "tester@electrohub.vn"
    assert "WELCOME10" in sent_emails[0][2]
    assert "WELCOME10" in sent_emails[0][3]

    # 2. Duplicate subscribe
    res2 = client.post(
        "/api/v1/newsletter/subscribe",
        json={"email": "tester@electrohub.vn", "consent": True},
        headers=csrf_headers(client),
    )
    assert res2.status_code == 201
    assert "Email đã đăng ký nhận tin" in res2.json()["detail"]
    # No second welcome email sent
    assert len(sent_emails) == 1


def test_unsubscribe_success_and_invalid_token(client, database):
    with Session(database) as db:
        db.add(NewsletterSubscriber(email="leaving@electrohub.vn"))
        db.commit()

    token = _unsubscribe_token("leaving@electrohub.vn")

    # Invalid token (wrong signature)
    bad_res = client.post(
        "/api/v1/newsletter/unsubscribe",
        data={"token": "leaving@electrohub.vn|tampered_hash"},
        headers=csrf_headers(client),
    )
    assert bad_res.status_code == 400

    # Malformed token
    bad_format = client.post(
        "/api/v1/newsletter/unsubscribe",
        data={"token": "malformed_token_without_pipe"},
        headers=csrf_headers(client),
    )
    assert bad_format.status_code == 400

    # Valid token
    ok_res = client.post(
        "/api/v1/newsletter/unsubscribe",
        data={"token": token},
        headers=csrf_headers(client),
    )
    assert ok_res.status_code == 200
    assert "Đã hủy đăng ký nhận tin" in ok_res.json()["detail"]

    with Session(database) as db:
        sub = db.scalar(select(NewsletterSubscriber).where(NewsletterSubscriber.email == "leaving@electrohub.vn"))
        assert sub is None


def test_send_campaign_requires_admin_and_smtp(client, database, monkeypatch):
    # Customer user (not admin)
    register(client, email="cust@electrohub.vn")
    assert login(client, email="cust@electrohub.vn").status_code == 200
    cust_headers = csrf_headers(client)

    # 1. Non-admin forbidden
    res = client.post(
        "/api/v1/newsletter/send",
        json={"subject": "Khuyến mãi tháng", "body": "Nội dung khuyến mãi giảm 20% linh kiện."},
        headers=cust_headers,
    )
    assert res.status_code == 403

    # 2. Admin but without SMTP
    admin_headers = make_admin(client, database, email="admin1@electrohub.vn")
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", None)
    monkeypatch.setattr(settings, "mail_from", None)

    res_no_smtp = client.post(
        "/api/v1/newsletter/send",
        json={"subject": "Khuyến mãi tháng", "body": "Nội dung khuyến mãi giảm 20% linh kiện."},
        headers=admin_headers,
    )
    assert res_no_smtp.status_code == 503
    assert "Cần cấu hình SMTP_HOST và MAIL_FROM" in res_no_smtp.json()["detail"]


def test_admin_send_campaign_flow(client, database, monkeypatch):
    admin_headers = make_admin(client, database, email="admin2@electrohub.vn")

    # Add subscribers
    with Session(database) as db:
        db.add_all([
            NewsletterSubscriber(email="sub1@electrohub.vn"),
            NewsletterSubscriber(email="sub2@electrohub.vn"),
        ])
        db.commit()

    # Configure SMTP settings
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "mail_from", "noreply@electrohub.vn")

    class FakeSMTP:
        sent_messages = []

        def __init__(self, host, port, timeout=15):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def starttls(self):
            pass

        def login(self, username, password):
            pass

        def send_message(self, message):
            FakeSMTP.sent_messages.append(message)

    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

    # Send campaign
    res = client.post(
        "/api/v1/newsletter/send",
        json={"subject": "Siêu sale cuối tuần", "body": "Giảm giá 30% cho tất cả module ESP32 và cảm biến.\n\nĐặt hàng ngay hôm nay!"},
        headers=admin_headers,
    )
    assert res.status_code == 200
    assert "Đã bắt đầu gửi email marketing tới 2 người nhận" in res.json()["detail"]

    # Verify background task sent 2 messages and recorded campaign
    assert len(FakeSMTP.sent_messages) == 2
    with Session(database) as db:
        campaign = db.scalar(select(EmailCampaign).where(EmailCampaign.subject == "Siêu sale cuối tuần"))
        assert campaign is not None
        assert campaign.recipient_count == 2
        assert campaign.status == "sent"


def test_admin_subscriber_management(client, database):
    admin_headers = make_admin(client, database, email="admin3@electrohub.vn")

    with Session(database) as db:
        db.add_all([
            NewsletterSubscriber(email="alpha@domain.com"),
            NewsletterSubscriber(email="beta@domain.com"),
        ])
        db.commit()

    # 1. List subscribers
    list_res = client.get("/api/v1/admin/newsletter/subscribers", headers=admin_headers)
    assert list_res.status_code == 200
    data = list_res.json()
    assert data["total"] >= 2
    emails = [item["email"] for item in data["items"]]
    assert "alpha@domain.com" in emails
    assert "beta@domain.com" in emails

    # 2. Search subscriber
    search_res = client.get("/api/v1/admin/newsletter/subscribers?q=alpha", headers=admin_headers)
    assert search_res.status_code == 200
    assert search_res.json()["total"] == 1
    assert search_res.json()["items"][0]["email"] == "alpha@domain.com"

    # 3. Delete subscriber
    sub_id = search_res.json()["items"][0]["id"]
    del_res = client.delete(f"/api/v1/admin/newsletter/subscribers/{sub_id}", headers=admin_headers)
    assert del_res.status_code == 200

    # 4. Confirm deleted
    search_again = client.get("/api/v1/admin/newsletter/subscribers?q=alpha", headers=admin_headers)
    assert search_again.json()["total"] == 0

    # 5. Delete non-existent returns 404
    not_found = client.delete("/api/v1/admin/newsletter/subscribers/99999", headers=admin_headers)
    assert not_found.status_code == 404


def test_admin_campaign_history_and_preview(client, database):
    admin_headers = make_admin(client, database, email="admin4@electrohub.vn")

    # 1. Preview email
    preview_res = client.post(
        "/api/v1/admin/newsletter/preview",
        json={"subject": "Xem trước ưu đãi", "body": "Đoạn văn 1.\n\nĐoạn văn 2."},
        headers=admin_headers,
    )
    assert preview_res.status_code == 200
    assert "Xem trước ưu đãi" in preview_res.json()["html"]
    assert "Đoạn văn 1." in preview_res.json()["html"]

    # 2. Campaign list
    with Session(database) as db:
        db.add(EmailCampaign(subject="Chiến dịch trước đó", body="Nội dung cũ", recipient_count=5, status="sent"))
        db.commit()

    hist_res = client.get("/api/v1/admin/newsletter/campaigns", headers=admin_headers)
    assert hist_res.status_code == 200
    data = hist_res.json()
    assert data["total"] >= 1
    assert data["items"][0]["subject"] == "Chiến dịch trước đó"
    assert data["items"][0]["recipient_count"] == 5

    # 3. Visit admin newsletter page
    page_res = client.get("/admin/newsletter", headers=admin_headers)
    assert page_res.status_code == 200
    assert "Quản lý Email Marketing" in page_res.text
    assert "data-tab-target" in page_res.text

    # 4. Get templates
    tpl_res = client.get("/api/v1/admin/newsletter/templates", headers=admin_headers)
    assert tpl_res.status_code == 200
    templates = tpl_res.json()["items"]
    assert len(templates) >= 4
    assert any(t["id"] == "flash_sale" for t in templates)

    # 5. Verify single linebreaks are preserved as <br>
    multiline_body = "Dòng 1\nDòng 2\n\nĐoạn mới"
    _, html = email_service.render_campaign_email("test@example.com", "Tiêu đề", multiline_body)
    assert "Dòng 1<br>" in html
    assert "Dòng 2" in html

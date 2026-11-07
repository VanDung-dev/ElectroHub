# Nghiên cứu triển khai thanh toán sandbox — VNPAY & PayPal

[← Trang bắt đầu](README.md) · [API hiện tại](API-DESIGN.md#sales) · [DB hiện tại](DB-MIGRATION.md)

Tài liệu này trả lời câu hỏi: **làm thế nào để thay luồng thanh toán mô phỏng hiện tại bằng sandbox thật của VNPAY và PayPal**, vẫn giữ được state machine đơn hàng/payment đã có.

## 0. Kết luận nhanh

| Hạng mục | VNPAY sandbox | PayPal sandbox |
| --- | --- | --- |
| Bản chất | Redirect sang cổng VNPAY, ký HMAC-SHA512 | Redirect sang PayPal, gọi REST Orders API |
| Cần tài khoản | Đăng ký merchant sandbox để nhận `vnp_TmnCode` + `vnp_HashSecret` | Tài khoản developer + app sandbox để nhận `client_id` + `secret` |
| Cần public HTTPS | **Có**, cho IPN (server-to-server) | **Có**, cho webhook |
| Đơn vị tiền | VND, gửi `amount * 100` | **Không hỗ trợ VND** — phải quy đổi sang USD (hoặc bảng giá USD) |
| Kết quả cuối | IPN + Return URL | Capture API + webhook |
| Độ khó tích hợp | Trung bình (tự ký/verify query string) | Trung bình (OAuth, create/capture, verify webhook) |
| Phù hợp demo | Nội địa, thẻ ATM/QR | Quốc tế, tài khoản PayPal |

**Khuyến nghị:** làm **VNPAY trước** (một luồng redirect, ít API hơn), sau đó **PayPal**. Giữ `PAYMENT_MODE=mock` làm mặc định để toàn bộ test hiện tại vẫn chạy; bật `sandbox` bằng biến môi trường.

> **Trạng thái:** phần lớn thiết kế dưới đây đã được triển khai và chạy thử bằng Docker + SQL Server. Xem [13.4](#134-trạng-thái-triển-khai--việc-còn-lại) để biết việc còn phụ thuộc môi trường ngoài.

### Quyết định đã chốt (2026-11-06)

- Demo **cả hai**: VNPAY và PayPal.
- VNPAY thu **VND**; PayPal thu **USD** (quy đổi từ giá VND theo tỷ giá cấu hình).
- Hủy đơn đã thanh toán: tạo **yêu cầu hoàn tiền sau 72 giờ**, shop xác nhận mới gọi refund gateway.
- Sandbox dùng credential riêng của từng provider; hướng dẫn lấy ở [mục 13](#13-checklist-lấy-credential-sandbox).

---

## 1. Hiện trạng repo ban đầu và phần có thể giữ lại

> Mục này ghi lại trạng thái **trước khi** triển khai, để giải thích vì sao chọn kiến trúc bên dưới.

Luồng ban đầu **không phải sandbox**, chỉ là mô phỏng nội bộ:

- `app/schemas/cart.py:66` — chỉ nhận `PAYPAL | VNPAY`.
- `app/services/order_service.py:319-324` — tạo `Payment(payload={"provider": ..., "simulation": True})`.
- `app/routers/payments.py:54-59` — `session` trả URL nội bộ `/payments/{code}`.
- `app/routers/payments.py:62-85` — `simulate` ghi thẳng `paid/failed`.
- `app/services/order_service.py:401-419` — hủy đơn đã trả tiền mô phỏng thì restock + `refunded`.
- `guideline/HSHOP-ANALYSIS.md:77` — tài liệu cũ xác nhận "cả hai mô phỏng".

**Giữ nguyên, tái sử dụng:**

- Một `Payment`/`Order` (unique `order_id`).
- State machine `pending → paid → refunded`, `failed` được retry.
- Điều kiện admin chỉ chuyển `confirmed/shipping/done` khi `payment.status == "paid"` (`order_service.py:431-433`).
- Idempotency hiện có ở mức order (gọi `paid` lặp lại trả kết quả cũ).
- Cờ `payload.simulation` để phân biệt payment cũ/mock với payment thật.

**Phải thay:**

- `session` phải trả URL của gateway, không phải trang nội bộ.
- Thêm endpoint return/IPN/webhook.
- Thêm verify chữ ký + đối chiếu số tiền trước khi ghi DB.
- Thêm cột lưu mã giao dịch của provider (để refund/đối soát).
- Nới `require_csrf` cho webhook (xem mục 9).

---

## 2. Kiến trúc đề xuất

```text
Browser                FastAPI                         Gateway
  |                       |                               |
  |-- POST /session ----->|                               |
  |                       |-- create order / build URL -->|
  |<-- {url} -------------|                               |
  |-- redirect ------------------------------------------->|
  |                       |                               |
  |                       |<-- IPN (VNPAY, GET) ----------|
  |                       |<-- webhook (PayPal, POST) ----|
  |                       |    verify + update DB         |
  |<-- return URL --------|<------------------------------|
  |-- GET /payments/{code} -> đọc trạng thái từ DB        |
```

Nguyên tắc:

1. **Server tạo order/URL**, không bao giờ tin số tiền từ client.
2. **Gateway gọi server** (IPN/webhook) là nguồn xác nhận chính; return URL chỉ để hiển thị UX.
3. Mọi cập nhật `paid/failed/refunded` đi qua **một hàm duy nhất**, có lock + idempotency.
4. Return URL **có verify chữ ký**; với VNPAY có thể dùng thêm `querydr` để đối soát nếu IPN chưa tới.
5. Chỉ bật `sandbox` khi đã cấu hình đủ secret; nếu thiếu thì app báo lỗi cấu hình, không fallback im lặng sang mock.

### Cấu trúc code đề xuất

```text
app/services/payments/
  __init__.py
  base.py       # PaymentGateway protocol + PaymentResult
  vnpay.py      # build_payment_url, verify, querydr, refund
  paypal.py     # token, create_order, capture, verify_webhook, refund
  service.py    # apply_result, retry, refund orchestration
app/routers/payments.py   # session, details, return, ipn, webhook
```

Giữ `app/routers/payments.py` làm router mỏng; toàn bộ ký/verify/HTTP nằm trong `app/services/payments/`.

---

## 3. Cấu hình

Đã triển khai trong `app/core/config.py` và `.env.example`:

```dotenv
# mock | sandbox | live
PAYMENT_MODE=mock

# VNPAY (sandbox)
VNPAY_TMN_CODE=
VNPAY_HASH_SECRET=
VNPAY_PAY_URL=https://sandbox.vnpayment.vn/paymentv2/vpcpay.html
VNPAY_API_URL=https://sandbox.vnpayment.vn/merchant_webapi/api/transaction
VNPAY_EXPIRE_MINUTES=15

# PayPal (sandbox)
PAYPAL_CLIENT_ID=
PAYPAL_CLIENT_SECRET=
PAYPAL_API_BASE=https://api-m.sandbox.paypal.com
PAYPAL_WEBHOOK_ID=
PAYPAL_CURRENCY=USD
PAYPAL_VND_PER_USD=25000

# Hoàn tiền: chờ 72h rồi shop xác nhận
REFUND_HOLD_HOURS=72

# VAT trên giá trị hàng sau giảm giá (phí giao hàng không chịu VAT)
VAT_PERCENT=10
```

Return/IPN/webhook URL **không cấu hình riêng**; tất cả derive từ `SITE_URL`:

| URL | Giá trị suy ra |
| --- | --- |
| VNPAY Return | `{SITE_URL}/payments/vnpay/return` |
| VNPAY IPN | `{SITE_URL}/api/v1/payments/vnpay/ipn` |
| PayPal Return | `{SITE_URL}/payments/paypal/return` |
| PayPal Webhook | `{SITE_URL}/api/v1/payments/paypal/webhook` |

Quy tắc:

- `PAYMENT_MODE=mock` → giữ nguyên hành vi cũ, test chạy 100%, endpoint `simulate` còn hoạt động.
- `PAYMENT_MODE=sandbox` → fail-fast khi thiếu credential; `SITE_URL` phải là HTTPS public để nhận IPN/webhook.
- `PAYMENT_MODE=live` → thêm kiểm tra `COOKIE_SECURE=true`, không cho `http://`.
- Không commit `.env`; secret chỉ đọc từ env/secret manager.

`site_url` hiện tại (`http://localhost:8000`) **không đủ** cho IPN/webhook. Khi test local phải dùng tunnel (mục 11). Khi có URL public, đổi `SITE_URL` rồi tạo lại PayPal webhook với đúng `{SITE_URL}/api/v1/payments/paypal/webhook`.

### 3.1. VAT, tỷ giá và giỏ hàng

- `vat = round_half_up((subtotal - discount) * VAT_PERCENT / 100)`; phí giao hàng **không** chịu VAT.
- `total = subtotal - discount + vat + shipping_fee`, lưu `orders.vat` (migration `0012_order_vat`).
- Cart/checkout/trang thanh toán/chi tiết đơn đều hiển thị dòng VAT kèm `VAT_PERCENT`.
- Checkout hiển thị số tiền từng cổng ngay khi chọn phương thức:
  - PayPal: `USD = round(total / PAYPAL_VND_PER_USD, 2)` kèm tỷ giá và ghi chú "đã gồm VAT".
  - VNPAY: thu đúng `total` bằng VND, không quy đổi.
- **Cổng thanh toán mở trong tab mới** (kể cả QR VNPAY): checkout và nút "Thanh toán ngay" mở gateway sang tab mới, trang hiện tại giữ lại trên ElectroHub (tracking/trạng thái). Tab gốc tự cập nhật trạng thái + giỏ hàng qua tín hiệu `localStorage` hoặc khi quay lại focus tab.
- **Giỏ hàng chỉ bị xóa khi payment chuyển `paid`** (IPN/return/webhook/capture hoặc `simulate`). Checkout chỉ trừ kho và tạo order; nếu khách bỏ ngang cổng thanh toán, giỏ vẫn còn hàng.
- Khi thanh toán xác nhận, chỉ trừ đúng số lượng đã mua; sản phẩm/số lượng thêm sau checkout được giữ lại trong giỏ.

---

## 4. Data model & migration

### 4.1. Vấn đề của schema hiện tại

`payments` chỉ có `method`, `status`, `payload`. Không đủ để:

- Tra cứu giao dịch theo mã provider khi IPN/webhook tới.
- Refund đúng giao dịch.
- Phân biệt payment mock cũ và payment thật.
- Lưu số tiền/currency thực tế đã charge (PayPal USD khác VND).

### 4.2. Cột đề xuất (migration `0010_payment_gateway`)

```text
payments
  provider          NVARCHAR(16)  NOT NULL DEFAULT 'mock'   -- mock | vnpay | paypal
  txn_ref           NVARCHAR(64)  NULL UNIQUE               -- vnp_TxnRef / invoice_id
  provider_order_id NVARCHAR(64)  NULL                      -- PayPal order id
  provider_txn_id   NVARCHAR(64)  NULL                      -- capture id / vnp_TransactionNo
  provider_status   NVARCHAR(32)  NULL                      -- raw status từ provider
  currency          NVARCHAR(3)   NOT NULL DEFAULT 'VND'
  amount_minor      BIGINT        NULL                      -- VND*100 hoặc USD cents
  attempt           INT           NOT NULL DEFAULT 1
  paid_at           DATETIME2     NULL
  raw_payload       NVARCHAR(MAX) NULL                      -- JSON response/IPN đã lọc
```

- Giữ `payload` cũ để tương thích; backfill `provider='mock'` cho row cũ.
- Unique `txn_ref` là bắt buộc: VNPAY yêu cầu `vnp_TxnRef` **không trùng trong ngày**; retry phải sinh ref mới.
- `provider_order_id` + `provider_txn_id` nên có index để webhook tra nhanh.
- Không đổi `method` check constraint (`PAYPAL`, `VNPAY`); `provider` mới là nơi phân biệt mock/thật.

`txn_ref` nên là chuỗi **alphanumeric**, không dấu gạch: `EH` + code không gạch + attempt, ví dụ `EHA1B2C301`. Code hiện tại `EH-XXXX` có gạch; VNPAY ghi "Alphanumeric" nên tránh rủi ro.

---

## 5. VNPAY sandbox

### 5.1. Thông tin môi trường

| Thông số | Giá trị |
| --- | --- |
| Pay URL | `https://sandbox.vnpayment.vn/paymentv2/vpcpay.html` |
| API querydr/refund | `https://sandbox.vnpayment.vn/merchant_webapi/api/transaction` |
| Đăng ký merchant sandbox | `https://pay.vnpaytest.vn/dev-registration` |
| Version | `2.1.0` |
| Hash | HMAC-SHA512 |
| Tiền tệ | VND |
| IPN | GET, server-to-server, cần SSL public |

VNPAY gửi `vnp_TmnCode` và `vnp_HashSecret` qua email sau khi đăng ký. Không có secret thì không thể ký.

### 5.2. Tạo URL thanh toán

Tham số bắt buộc (theo tài liệu VNPAY):

```text
vnp_Version=2.1.0
vnp_Command=pay
vnp_TmnCode=<config>
vnp_Amount=<total_vnd * 100>
vnp_CurrCode=VND
vnp_TxnRef=<txn_ref duy nhất trong ngày>
vnp_OrderInfo=<mô tả không dấu, không ký tự đặc biệt>
vnp_OrderType=other
vnp_Locale=vn
vnp_IpAddr=<IP khách>
vnp_CreateDate=<yyyyMMddHHmmss GMT+7>
vnp_ExpireDate=<CreateDate + 15 phút, GMT+7>
vnp_ReturnUrl=<config>
```

Thuật toán ký (Python):

```python
import hmac
import hashlib
from urllib.parse import quote_plus


def _hash_data(params: dict[str, str]) -> str:
    items = sorted((k, v) for k, v in params.items() if v not in (None, ""))
    return "&".join(f"{quote_plus(k)}={quote_plus(str(v))}" for k, v in items)


def sign(params: dict[str, str], secret: str) -> str:
    data = _hash_data(params)
    return hmac.new(secret.encode(), data.encode(), hashlib.sha512).hexdigest()


def build_url(base: str, params: dict[str, str], secret: str) -> str:
    data = _hash_data(params)
    secure_hash = hmac.new(secret.encode(), data.encode(), hashlib.sha512).hexdigest()
    return f"{base}?{data}&vnp_SecureHash={secure_hash}"
```

Lưu ý thực chiến:

- `quote_plus` tương đương `urlencode` trong sample chính thức (space → `+`). Phải dùng **cùng một hàm** cho lúc ký và lúc verify.
- Không đưa `vnp_SecureHash` vào dữ liệu ký.
- Không dùng `float` cho tiền; `total` đang là `int` VND, chỉ nhân `100`.
- `vnp_OrderInfo` phải bỏ dấu tiếng Việt và ký tự đặc biệt; nên dùng `unicodedata.normalize("NFKD")` + lọc `[A-Za-z0-9 ]`.
- `vnp_IpAddr` lấy IP client. Nếu chạy sau reverse proxy, chỉ tin `X-Forwarded-For` khi proxy nằm trong danh sách tin cậy; nếu không, IP sai có thể bị VNPAY từ chối.
- `vnp_TxnRef` phải đổi mỗi lần retry. Lưu vào `payments.txn_ref` **trước khi** redirect.

### 5.3. Return URL

Người dùng được redirect về:

```text
GET /payments/vnpay/return?vnp_Amount=...&vnp_ResponseCode=00&vnp_TransactionStatus=00&vnp_TxnRef=...&vnp_SecureHash=...
```

Xử lý:

1. Lọc các tham số bắt đầu bằng `vnp_`.
2. Bỏ `vnp_SecureHash` (và `vnp_SecureHashType` nếu có).
3. Sort + build `hashData` + HMAC-SHA512, so sánh bằng `hmac.compare_digest`.
4. Kiểm tra `vnp_TmnCode` khớp config.
5. Tìm payment theo `vnp_TxnRef`.
6. Đối chiếu `vnp_Amount / 100 == order.total`.
7. Nếu `vnp_ResponseCode == "00"` **và** `vnp_TransactionStatus == "00"` → `paid`; ngược lại → `failed` (kèm mã lỗi).
8. Hiển thị trang kết quả; **không** tin query string nếu chữ ký sai.

Return URL vẫn có thể bị người dùng mở lại (replay). Vì vậy:

- Cập nhật phải idempotent.
- Chỉ áp dụng khi payment đang `pending/failed` và order chưa `cancelled`.
- Không cộng/trừ stock lần hai.

### 5.4. IPN URL (nguồn xác nhận chính)

```text
GET /api/v1/payments/vnpay/ipn?vnp_...
```

Xử lý theo đúng thứ tự tài liệu VNPAY khuyến nghị:

1. Verify checksum **trước tiên**.
2. Tìm order theo `vnp_TxnRef`.
3. Kiểm tra số tiền khớp.
4. Kiểm tra trạng thái payment chưa được xác nhận.
5. Cập nhật DB.
6. Trả JSON:

```json
{"RspCode": "00", "Message": "Confirm Success"}
```

Bảng phản hồi:

| RspCode | Khi nào |
| --- | --- |
| `00` | Đã cập nhật thành công |
| `01` | Không tìm thấy order |
| `02` | Order đã xác nhận trước đó |
| `04` | Số tiền không khớp |
| `97` | Chữ ký không hợp lệ |
| `99` | Lỗi khác |

VNPAY retry IPN tối đa **10 lần, cách 5 phút** nếu merchant trả `01/04/97/99` hoặc timeout. Vì vậy endpoint phải nhanh, idempotent, và trả `00` ngay khi đã ghi nhận.

IPN là **GET** nên không bị CSRF chặn; nhưng phải public HTTPS. Nếu chưa có tunnel/domain, IPN sẽ không bao giờ tới — đây là lý do phổ biến nhất khiến sandbox "treo" ở trạng thái pending.

### 5.5. Querydr & refund

Khi cần đối soát hoặc hoàn tiền, gọi `POST https://sandbox.vnpayment.vn/merchant_webapi/api/transaction` với JSON.

- `querydr`: tra theo `vnp_TxnRef` + `vnp_TransactionDate`.
- `refund`: `vnp_Command=refund`, `vnp_TransactionType=02` (toàn phần) / `03` (một phần).

**Chữ ký của querydr/refund không giống chữ ký tạo URL**: dữ liệu là chuỗi nối bằng `|` theo đúng thứ tự trong tài liệu, không phải query string sort. Ví dụ querydr:

```text
vnp_RequestId|vnp_Version|vnp_Command|vnp_TmnCode|vnp_TxnRef|
vnp_TransactionDate|vnp_CreateDate|vnp_IpAddr|vnp_OrderInfo
```

Refund:

```text
vnp_RequestId|vnp_Version|vnp_Command|vnp_TmnCode|vnp_TransactionType|
vnp_TxnRef|vnp_Amount|vnp_TransactionNo|vnp_TransactionDate|
vnp_CreateBy|vnp_CreateDate|vnp_IpAddr|vnp_OrderInfo
```

Đây là chỗ dễ copy nhầm code mẫu. Nên tách hàm `_sign_querydr` và `_sign_refund` riêng, có unit test.

Refund chỉ nên gọi khi:

- Payment đã `paid`, có `provider_txn_id` (chính là `vnp_TransactionNo`).
- Order đang bị hủy.
- Số tiền hoàn `<=` số tiền gốc.

Nếu refund thành công → `payment.status = refunded` → restock. Nếu refund lỗi → **không** restock, trả lỗi cho admin.

### 5.6. Mapping trạng thái

| VNPAY | Local |
| --- | --- |
| `vnp_ResponseCode=00` + `vnp_TransactionStatus=00` | `paid` |
| `24` (khách hủy) | `failed` |
| `11` (hết hạn) | `failed` |
| `51` (không đủ số dư) | `failed` |
| `07` (trừ tiền nhưng nghi ngờ) | `pending` + cảnh báo để đối soát thủ công |
| `04` (đảo giao dịch) | `failed`/`refunded` tùy `TransactionStatus` |

Luôn lưu raw `vnp_ResponseCode`, `vnp_TransactionStatus`, `vnp_TransactionNo`, `vnp_BankCode` vào `raw_payload` để tra cứu.

### 5.7. Test card sandbox

Theo trang demo chính thức của VNPAY (có thể thay đổi, kiểm tra lại trước khi test):

| Trường hợp | Thông tin |
| --- | --- |
| Thành công | NCB `9704198526191432198`, `NGUYEN VAN A`, `07/15`, OTP `123456` |
| Không đủ số dư | NCB `9704195798459170488` |
| Thẻ chưa kích hoạt | NCB `9704192181368742` |
| Thẻ bị khóa | NCB `9704193370791314` |
| Thẻ hết hạn | NCB `9704194841945513` |

Chỉ các thẻ trong danh sách demo mới dùng được ở môi trường test.

---

## 6. PayPal sandbox

### 6.1. Thông tin môi trường

| Thông số | Giá trị |
| --- | --- |
| REST base | `https://api-m.sandbox.paypal.com` |
| OAuth | `POST /v1/oauth2/token` (Basic auth) |
| Tạo order | `POST /v2/checkout/orders` |
| Capture | `POST /v2/checkout/orders/{id}/capture` |
| Refund | `POST /v2/payments/captures/{capture_id}/refund` |
| Verify webhook | `POST /v1/notifications/verify-webhook-signature` |
| Buyer sandbox | `https://www.sandbox.paypal.com/signin` |
| App credentials | Developer Dashboard → Apps & Credentials → Sandbox |

### 6.2. Lấy access token

```http
POST https://api-m.sandbox.paypal.com/v1/oauth2/token
Authorization: Basic base64(client_id:client_secret)
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
```

Response có `access_token`, `expires_in`. Cache token trong process (ví dụ `lru_cache` + timestamp) để không xin lại mỗi request. Khi hết hạn thì refresh.

### 6.3. Tạo order

```http
POST /v2/checkout/orders
Authorization: Bearer <token>
Content-Type: application/json
PayPal-Request-Id: <idempotency key>

{
  "intent": "CAPTURE",
  "purchase_units": [{
    "reference_id": "EH-XXXX",
    "invoice_id": "EH-XXXX",
    "description": "ElectroHub order EH-XXXX",
    "amount": {
      "currency_code": "USD",
      "value": "12.34"
    }
  }],
  "payment_source": {
    "paypal": {
      "experience_context": {
        "return_url": "https://.../payments/EH-XXXX/paypal/return",
        "cancel_url": "https://.../payments/EH-XXXX/paypal/cancel",
        "user_action": "PAY_NOW"
      }
    }
  }
}
```

Response có `id` và `links`. Tìm link có `rel` là `payer-action` (mới) hoặc `approve` (cũ), redirect người dùng tới đó.

**Quan trọng — VND không được hỗ trợ.** Danh sách currency chính thức của PayPal không có VND. Vì repo lưu tiền VND, phải chọn một trong hai:

1. **Quy đổi tại thời điểm checkout** (khuyến nghị cho demo): `value = round(total / PAYPAL_VND_PER_USD, 2)`. Lưu `amount_minor` USD cents + `currency=USD` vào payment, hiển thị rõ "số tiền quy đổi" trước khi redirect.
2. **Bảng giá USD riêng** cho sản phẩm: chính xác hơn nhưng phải sửa catalog.

Không dùng `float`; dùng `Decimal` + `ROUND_HALF_UP`. Phải đối chiếu đúng `value/currency` khi capture.

### 6.4. Capture

Sau khi buyer approve, PayPal redirect về `return_url?token=<paypal_order_id>&PayerID=...`.

Server gọi:

```http
POST /v2/checkout/orders/{id}/capture
Authorization: Bearer <token>
PayPal-Request-Id: <idempotency key>
```

Kết quả:

- `status == "COMPLETED"` → `paid`.
- `status == "PENDING"` → `pending` (chờ webhook/đối soát).
- `status == "DECLINED"/"FAILED"` → `failed`.

Lưu:

```text
provider_order_id = order.id
provider_txn_id   = purchase_units[0].payments.captures[0].id
provider_status   = capture.status
amount_minor      = capture.amount.value * 100
currency          = capture.amount.currency_code
```

Kiểm tra `capture.amount` khớp số tiền đã lưu **trước khi** đánh `paid`.

Vì capture là API call (không phải webhook), đây là hành động chính khi user quay về. Webhook `PAYMENT.CAPTURE.COMPLETED` là lớp xác nhận/backup.

### 6.5. Webhook

Đăng ký URL:

```text
POST https://.../api/v1/payments/paypal/webhook
```

Event cần subscribe:

- `CHECKOUT.ORDER.APPROVED` (không bắt buộc nếu capture ngay)
- `PAYMENT.CAPTURE.COMPLETED`
- `PAYMENT.CAPTURE.DENIED`
- `PAYMENT.CAPTURE.REFUNDED`
- `CHECKOUT.PAYMENT-APPROVAL.REVERSED`

Verify bằng API (không tự tính CRC32):

```http
POST /v1/notifications/verify-webhook-signature
Authorization: Bearer <token>

{
  "auth_algo": "<paypal-auth-algo header>",
  "cert_url": "<paypal-cert-url header>",
  "transmission_id": "<paypal-transmission-id header>",
  "transmission_sig": "<paypal-transmission-sig header>",
  "transmission_time": "<paypal-transmission-time header>",
  "webhook_id": "<PAYPAL_WEBHOOK_ID>",
  "webhook_event": <body>
}
```

Chỉ xử lý khi `verification_status == "SUCCESS"`. Sau đó:

1. Lấy `event_type`.
2. Lấy `resource.id` (capture id) và `resource.supplementary_data.related_ids.order_id` (PayPal order id).
3. Tìm payment theo `provider_order_id`/`provider_txn_id`.
4. Đối chiếu amount/currency.
5. Apply idempotent.
6. Trả `200` nhanh; PayPal retry tối đa **25 lần trong 3 ngày** nếu không 2xx.

**Không** dùng webhook làm nguồn duy nhất: nếu webhook không tới (local chưa tunnel), capture ở return URL vẫn phải hoạt động.

### 6.6. Refund

```http
POST /v2/payments/captures/{capture_id}/refund
Authorization: Bearer <token>
Content-Type: application/json
PayPal-Request-Id: <idempotency key>

{ "amount": { "currency_code": "USD", "value": "12.34" } }
```

- Toàn phần: bỏ `amount`.
- Kiểm tra capture id đã lưu, không refund quá số tiền.
- Khi hủy đơn đã paid: gọi refund trước, chỉ restock sau khi gateway trả thành công.

### 6.7. Mapping trạng thái

| PayPal | Local |
| --- | --- |
| `COMPLETED` | `paid` |
| `PENDING` | `pending` |
| `DECLINED`, `FAILED` | `failed` |
| `REFUNDED` | `refunded` |

### 6.8. Test sandbox

- Tạo **personal sandbox account** để đóng vai buyer; đăng nhập `sandbox.paypal.com`.
- Tạo **business sandbox account** để nhận tiền.
- Bật **Negative Testing** trên business sandbox account để giả lập `INSUFFICIENT_FUNDS`, `INSTRUMENT_DECLINED`, `TRANSACTION_REFUSED`, `INTERNAL_SERVER_ERROR`.
- Dùng **Webhook Simulator** trong dashboard để gửi event thử, hoặc tunnel để nhận event thật.
- Thẻ test: xem Credit Card Generator trong Developer Dashboard.

Lưu ý Việt Nam: PayPal có trang Vietnam, nhưng khả năng nhận/ rút tiền phụ thuộc loại tài khoản và country capability. **Sandbox nên dùng business account US** để tránh giới hạn; trước khi go-live phải xác minh tài khoản business VN có bật "Accept Payments" và rút được VND hay không.

---

## 7. Tích hợp vào codebase

### 7.1. Endpoint contract mới

| Method | Path | Auth/CSRF | Mục đích |
| --- | --- | --- | --- |
| `POST` | `/api/v1/payments/orders/{code}/session` | user + CSRF | Tạo URL gateway, trả `{provider,url,currency,amount_minor}` |
| `GET` | `/api/v1/payments/orders/{code}` | user | Chi tiết payment + refund |
| `POST` | `/api/v1/payments/orders/{code}/simulate` | user + CSRF | **Chỉ** khi `PAYMENT_MODE=mock` |
| `POST` | `/api/v1/orders/{code}/cancel` | chủ đơn + CSRF | Hủy đơn; nếu đã paid thì tạo refund `scheduled` |
| `GET` | `/payments/vnpay/return` | public | Return URL VNPAY (verify chữ ký) |
| `GET` | `/api/v1/payments/vnpay/ipn` | public, no CSRF | IPN VNPAY |
| `GET` | `/payments/paypal/return` | public | Return URL PayPal (`code` hoặc `token`), capture |
| `GET` | `/payments/{code}/paypal/cancel` | public | Buyer cancel |
| `POST` | `/api/v1/payments/paypal/webhook` | public, no CSRF | Webhook PayPal |
| `GET` | `/api/v1/admin/refunds` | staff/admin | Danh sách refund, lọc `status`, `due` |
| `POST` | `/api/v1/admin/refunds/{id}/confirm` | admin | Gọi gateway refund sau 72h |
| `POST` | `/api/v1/admin/refunds/{id}/reject` | admin | Từ chối + lý do, payment về `paid` |

Giữ `/payments/{code}` làm trang kết quả; JS đọc trạng thái từ API và hiển thị.

### 7.2. Thay đổi cụ thể

| File | Thay đổi |
| --- | --- |
| `app/core/config.py` | Toàn bộ config mục 3 + validator fail-fast + derive URL từ `SITE_URL` |
| `app/models/payment.py` | Cột provider/currency/amount_minor/attempt/txn_ref + filtered unique index |
| `app/models/refund.py` | Model `Refund`, quan hệ 1-1 với đơn |
| `alembic/versions/0010_payment_gateway.py` | Cột payment + backfill `provider='mock'` |
| `alembic/versions/0011_refund_hold.py` | Bảng `refunds` + `refund_pending` |
| `app/services/payments/*` | Adapter VNPAY/PayPal + orchestration |
| `app/routers/payments.py` | `session` gọi gateway; IPN/webhook |
| `app/routers/payment_returns.py` | Return/cancel URL public |
| `app/routers/admin_refunds.py` | List/confirm/reject |
| `app/services/order_service.py` | Checkout ghi provider/currency/amount; hủy tạo refund, restock ngay |
| `app/core/deps.py` | Exempt CSRF đúng path webhook; origin check nhận `SITE_URL` |
| `app/templates/cart/payment.html` | Bỏ nút "mô phỏng" khi sandbox; trạng thái + "Thanh toán lại" |
| `app/static/js/store.js` | `session` → `location.assign(url)`; hiển thị refund |
| `compose.yaml` | Inject toàn bộ biến payment vào container app |
| `scripts/smoke_payments.py` | Smoke test E2E trên Docker/SQL Server |
| `.env.example` | Tài liệu hóa biến môi trường (URL derive từ `SITE_URL`) |

### 7.3. CSRF cho webhook

`app/main.py:44` đang gắn `Depends(require_csrf)` toàn app. PayPal webhook là POST không có CSRF token → sẽ bị `403`.

Cách sửa sạch nhất:

1. Bỏ dependency global khỏi `FastAPI(...)`.
2. Gắn `dependencies=[Depends(require_csrf)]` cho từng router nội bộ (auth, cart, orders, admin, products, newsletter, payments nội bộ).
3. Router webhook công khai không gắn CSRF.

Nếu muốn sửa tối thiểu: trong `require_csrf`, bỏ qua chính xác 2 path:

```python
PUBLIC_WEBHOOK_PATHS = {"/api/v1/payments/paypal/webhook"}
if request.method in {"GET", "HEAD", "OPTIONS"} or request.url.path in PUBLIC_WEBHOOK_PATHS:
    return
```

Không dùng `startswith` rộng, tránh vô tình mở CSRF cho route khác. VNPAY IPN là GET nên đã được bỏ qua.

### 7.4. State machine & idempotency

Giữ nguyên:

```text
Order:   pending → confirmed → shipping → done
                ↘ cancelled
Payment: pending → paid → refunded
              ↘ failed → (retry) → paid
```

Quy tắc apply kết quả:

```python
def apply_result(db, payment, *, status, provider_txn_id, amount_minor, raw):
    with db.begin():
        locked = db.scalar(select(Payment).where(Payment.id == payment.id).with_for_update())
        if locked.status == status and locked.provider_txn_id == provider_txn_id:
            return "duplicate"
        if locked.status in {"paid", "refunded"} and status == "paid":
            return "duplicate"
        if locked.status == "refunded":
            raise Conflict
        if amount_minor != locked.amount_minor:
            raise AmountMismatch
        locked.status = status
        locked.provider_txn_id = provider_txn_id
        locked.provider_status = raw["status"]
        locked.raw_payload = raw
        locked.paid_at = now() if status == "paid" else locked.paid_at
```

- `with_for_update()` map sang `UPDLOCK/ROWLOCK` trên SQL Server.
- Không gọi HTTP gateway bên trong transaction DB.
- VNPAY IPN trùng → trả `RspCode=02`; PayPal webhook trùng → trả `200`.
- PayPal capture dùng `PayPal-Request-Id` để tránh capture đôi khi user refresh.

### 7.5. Retry

- `failed` được phép tạo session mới.
- Sinh `txn_ref` mới + `attempt += 1`; không tái sử dụng ref cũ.
- Nếu payment đang `pending` và user bấm lại: có thể tạo session mới (hủy order cũ phía provider nếu có API) hoặc trả lại URL cũ nếu còn hạn. Với VNPAY, URL cũ còn hạn 15 phút; với PayPal, order cũ có thể còn `CREATED`. Đơn giản nhất cho demo: mỗi lần bấm tạo mới, đánh dấu attempt cũ là bỏ.

---

## 8. Bảo mật — checklist bắt buộc

- [ ] Không tin `amount`, `currency`, `status` từ client.
- [ ] Verify chữ ký **trước** khi đọc DB/ghi DB.
- [ ] So khớp `vnp_TmnCode` với config.
- [ ] So khớp amount tuyệt đối (VND*100; USD cents).
- [ ] Kiểm tra `txn_ref` tồn tại, thuộc đúng order, order chưa hủy.
- [ ] Verify PayPal webhook qua API, không tự parse tin cậy.
- [ ] Chỉ bỏ CSRF cho đúng path webhook.
- [ ] Không log secret/hash/token; log `debug_id` của PayPal khi lỗi.
- [ ] `PAYMENT_MODE=live` yêu cầu HTTPS + `COOKIE_SECURE=true`.
- [ ] Rate limit `POST /session` (ví dụ 5/phút/user) để tránh spam tạo order.
- [ ] Không lưu số thẻ/CVV — redirect flow giữ PCI ở mức SAQ A.
- [ ] IPN/webhook chỉ trả JSON tối thiểu, không lộ stack trace.
- [ ] Refund phải kiểm tra capture id + số tiền; không refund hai lần.

---

## 9. Testing

### 9.1. Unit test

- Ký/verify VNPAY: golden vector với secret cố định, sinh độc lập bằng Node/PHP/openssl; test round-trip; test thứ tự sort; test ký tự tiếng Việt/space.
- `build_url` VNPAY: đúng `vnp_Amount = total*100`, `vnp_TxnRef` alphanumeric, `ExpireDate` GMT+7.
- Verify IPN: sai hash → `97`; amount sai → `04`; order không tồn tại → `01`; trùng → `02`.
- PayPal: mock `httpx` bằng `respx`; test token cache, create order (chọn `payer-action`/`approve`), capture `COMPLETED/PENDING/DECLINED`, webhook verify success/fail, refund.
- `apply_result`: idempotent, lock, không downgrade `paid → failed`, không apply cho order cancelled.
- CSRF: webhook path không cần token; các POST khác vẫn 403 khi thiếu token.

### 9.2. Integration/manual

1. Chạy stack bằng Docker (đúng cấu trúc deploy):
   ```bash
   docker compose up -d --build
   docker compose ps          # app healthy, migrate exited 0
   ```
2. Chạy smoke test end-to-end trên SQL Server thật:
   ```bash
   python3 scripts/smoke_payments.py
   ```
   Script tự: ký IPN VNPAY → payment `paid`; hủy đơn → refund `scheduled` + restock ngay; confirm trước hạn → 409; chuyển `due_at` rồi confirm → `succeeded/refunded`; reject → payment về `paid`; tạo PayPal order thật trên sandbox.
3. Khi có tunnel HTTPS, đặt `SITE_URL` = URL tunnel rồi khởi động lại app (không cần biến Return/IPN riêng).
4. VNPAY: đăng ký merchant sandbox, điền `TmnCode`/`HashSecret`, tạo đơn, thanh toán bằng thẻ test, kiểm tra:
   - Return URL hiển thị đúng.
   - IPN tới (xem log), payment `paid`.
   - Retry thẻ lỗi → `failed` → thanh toán lại → `paid`.
   - Gửi IPN giả/trùng → không double update.
5. PayPal: tạo đơn, đăng nhập personal sandbox, approve, quay về, capture, kiểm tra webhook.
6. Hủy đơn đã paid → shop confirm sau 72h → refund sandbox thành công → `refunded` + restock.

### 9.3. Giữ test cũ xanh

- `PAYMENT_MODE=mock` mặc định; fixture test ép mock nên toàn bộ suite cũ vẫn chạy.
- `test_orders.py` assert URL nội bộ và luồng simulate — chỉ đúng trong mock mode.
- Không xóa `simulate`; chỉ chặn khi mode khác `mock` (trả 409).

---

## 10. Hoàn tiền sau 72 giờ (shop xác nhận)

### 10.1. Luồng

```text
Khách/admin hủy đơn đã paid
        |
        v
Tạo refund(status=scheduled, due_at = now + 72h)
Order = cancelled, restock + hoàn voucher ngay
Payment = refund_pending
        |
        |  (trong 72h: chỉ hiển thị, không cho confirm)
        v
Shop mở admin, thấy "Đến hạn hoàn tiền"
        |
        |  now >= due_at
        v
Shop bấm xác nhận
        |
        v
Gọi gateway refund (VNPAY refund / PayPal refund)
        |
   +----+----+
   |         |
 thành công  thất bại
   |         |
Payment=     Refund=failed
refunded     Payment=refund_pending
             Admin thử lại
```

Quy tắc:

- **Không tự động refund** ở 72h; 72h chỉ là thời điểm **đủ điều kiện** để shop xác nhận. Điều này khớp yêu cầu "refund sau 72h để cần shop xác nhận".
- Trước `due_at`, endpoint confirm trả `409` kèm thời gian còn lại.
- Shop có thể **từ chối** (ví dụ khách chưa gửi lại hàng) → `refund.status = rejected`, payment quay về `paid` vì chưa có tiền nào rời cổng; xử lý tiếp là quy trình thủ công.
- Restock/voucher hoàn **ngay khi hủy** để kho không bị treo; refund là bước tài chính độc lập.
- Nếu gateway refund lỗi, **không** rollback restock; đánh dấu `failed` và cho admin bấm lại (retry dùng cùng refund id).
- Mock mode dùng cùng luồng; `confirm` giả lập thành công ngay, không gọi gateway.
- `PAYMENT_MODE=mock` hoặc payment có `provider='mock'` luôn đi nhánh giả lập, kể cả khi `PAYMENT_MODE=sandbox` (dùng cho smoke test).

### 10.2. Bảng `refunds`

```text
refunds
  id                BIGINT PK
  order_id          FK orders UNIQUE       -- một refund/đơn
  payment_id        FK payments
  amount            BIGINT                 -- VND hoặc minor unit
  currency          NVARCHAR(3)
  status            NVARCHAR(20)           -- scheduled | processing | succeeded | failed | rejected
  reason            NVARCHAR(255)
  requested_by      FK users NULL           -- khách hay admin hủy
  requested_at      DATETIME2
  due_at            DATETIME2               -- requested_at + REFUND_HOLD_HOURS
  confirmed_by      FK users NULL
  confirmed_at      DATETIME2 NULL
  provider_refund_id NVARCHAR(64) NULL
  raw_payload       NVARCHAR(MAX) NULL
  created_at        DATETIME2
  updated_at        DATETIME2
```

Thêm `refund_pending` vào check constraint `payments.status` (migration `0011_refund_hold`).

### 10.3. API & UI

| Method | Path | Quyền | Mô tả |
| --- | --- | --- | --- |
| `GET` | `/api/v1/admin/refunds?status=&due=1` | staff/admin | Danh sách, lọc đã đến hạn |
| `POST` | `/api/v1/admin/refunds/{id}/confirm` | admin | Kiểm tra `due_at`, gọi refund |
| `POST` | `/api/v1/admin/refunds/{id}/reject` | admin | Từ chối + lý do |
| `GET` | `/api/v1/orders/{code}` | chủ đơn | Trả thêm `refund` (status, due_at) |

UI:

- Trang đơn của khách: "Yêu cầu hoàn tiền đã tạo. Dự kiến đủ điều kiện sau 72h (HH:mm dd/mm)."
- Admin: badge `Đến hạn hoàn tiền` khi `now >= due_at`; nút **Xác nhận hoàn tiền** và **Từ chối**.
- Không hiển thị nút confirm trước hạn; có thể hiển thị countdown.

### 10.4. Cấu hình

```dotenv
REFUND_HOLD_HOURS=72
```

Cho phép test override `REFUND_HOLD_HOURS=0` để chạy E2E nhanh mà không phải chờ.

### 10.5. Thay đổi code liên quan

| File | Thay đổi |
| --- | --- |
| `app/models/refund.py` | Model mới |
| `app/models/payment.py` | Thêm `refund_pending` vào check constraint |
| `app/services/order_service.py` | `_restock` không set `refunded` ngay; tạo `Refund` |
| `app/services/payments/service.py` | `request_refund`, `confirm_refund`, `reject_refund` |
| `app/routers/admin_refunds.py` | Router list/confirm/reject (list staff, mutate admin) |
| `app/templates/admin/orders.html` | Panel yêu cầu hoàn tiền |
| `app/static/js/store.js` | Render trạng thái refund, nút xác nhận/từ chối |
| `tests/test_orders.py` | Test hủy đơn, 72h, reject trả payment về `paid` |
| `tests/test_payment_gateways.py` | Test chữ ký, quy đổi USD, session sandbox, reject/duplicate |

---

## 11. Kế hoạch triển khai

| Bước | Nội dung | Ước lượng |
| --- | --- | --- |
| 1 | Config + migration + model + `PaymentGateway` protocol | 0.5 ngày |
| 2 | VNPAY: build URL, verify, return, IPN, querydr | 1.5–2 ngày |
| 3 | PayPal: OAuth, create, capture, webhook, refund | 2 ngày |
| 4 | Nối router/UI, giữ mock mode, test CSRF/idempotency | 1 ngày |
| 5 | Refund khi hủy đơn + admin flow | 0.5–1 ngày |
| 6 | Test + tunnel + tài liệu vận hành | 1 ngày |
| **Tổng** | | **~6–7 ngày / 1 dev** |

Thứ tự an toàn: **VNPAY trước** để có một luồng E2E hoàn chỉnh; PayPal sau vì phụ thuộc currency + webhook.

---

## 12. Rủi ro & quyết định cần chốt

### Rủi ro

1. **VNPAY sandbox không có IPN do thiếu HTTPS public** — luôn test qua tunnel, đừng chỉ `localhost`.
2. **Sai encoding chữ ký** — chỉ dùng một hàm `_hash_data` cho cả ký và verify; test với tiếng Việt có dấu.
3. **`vnp_TxnRef` trùng trong ngày** — sinh ref mới mỗi attempt, unique index ở DB.
4. **PayPal không hỗ trợ VND** — phải quyết định tỷ giá/quy đổi trước khi code; sai lệch làm capture fail.
5. **Webhook bị CSRF chặn** — sửa `app/main.py:44` / `deps.py` đúng path.
6. **Capture/refund lặp** — dùng `PayPal-Request-Id`, lock DB, idempotent apply.
7. **Refund xong nhưng DB lỗi** — chấp nhận rủi ro nhỏ ở demo; production nên dùng outbox/reconciliation job.
8. **Tài khoản PayPal VN** — sandbox dùng account US; go-live phải xác minh capability.
9. **Sandbox VNPAY thay đổi thẻ test/domain** — kiểm tra lại trang demo trước buổi demo.

### Cần chốt với team

- [x] Demo cả hai provider.
- [x] VNPAY thu VND; PayPal thu USD.
- [x] Hủy đơn đã paid: tạo refund sau 72h, shop xác nhận.
- [ ] Tỷ giá `PAYPAL_VND_PER_USD` cố định bao nhiêu (đề xuất 25.000 cho demo)?
- [ ] Ai giữ credential sandbox (Dũng/Hưng), lưu ở đâu?
- [ ] Có domain/tunnel HTTPS cố định cho demo không?
- [ ] Chỉ `admin` hay cả `staff` được xác nhận refund?
- [ ] Có cần hóa đơn/đối soát doanh thu theo provider không?

---

## 13. Checklist lấy credential sandbox

### 13.0. Chuẩn bị chung: một URL HTTPS public

VNPAY IPN và PayPal webhook đều là **server-to-server**, nên `http://localhost:8000` không nhận được. Cần tunnel:

```bash
# Cách 1: Cloudflare quick tunnel (không cần tài khoản)
cloudflared tunnel --url http://localhost:8000

# Cách 2: ngrok
ngrok http 8000
```

Sau đó:

1. Copy URL `https://...` mà tunnel in ra.
2. Đặt `SITE_URL=https://...` trong `.env`.
3. Kiểm tra: `curl https://.../api/v1/health` phải trả `{"detail":"ok"}`.
4. Restart app sau khi đổi `.env`.

Lưu ý: quick tunnel đổi URL mỗi lần chạy. VNPAY có thể gắn Return/IPn với domain đã đăng ký, nên buổi demo nên dùng **Cloudflare named tunnel** hoặc domain dev cố định (`dev.electrohub.vn`). Nếu URL đổi, phải cập nhật lại credential/cấu hình bên VNPAY và PayPal.

### 13.1. VNPAY sandbox

**Bước 1 — Đăng ký merchant sandbox**

Mở <https://pay.vnpaytest.vn/dev-registration> và điền:

- Tên đơn vị/cá nhân, email, số điện thoại thật (credential gửi qua email).
- Website/app: dùng URL tunnel hoặc domain dev.
- Mô tả dịch vụ: "Demo bán linh kiện điện tử".

**Bước 2 — Nhận credential**

VNPAY gửi email (thường trong vài giờ làm việc) gồm:

```text
vnp_TmnCode      # 8 ký tự, ví dụ DEMOV210
vnp_HashSecret   # chuỗi bí mật dài
```

Nếu chưa nhận được, kiểm tra spam hoặc liên hệ VNPAY qua trang Liên hệ. Không dùng tài khoản production cho demo.

**Bước 3 — Điền `.env`**

```dotenv
PAYMENT_MODE=sandbox
SITE_URL=https://your-public-origin.example
VNPAY_TMN_CODE=<vnp_TmnCode>
VNPAY_HASH_SECRET=<vnp_HashSecret>
VNPAY_PAY_URL=https://sandbox.vnpayment.vn/paymentv2/vpcpay.html
VNPAY_API_URL=https://sandbox.vnpayment.vn/merchant_webapi/api/transaction
VNPAY_EXPIRE_MINUTES=15
```

**Bước 4 — Đăng ký Return URL / IPN URL**

Theo tài liệu VNPAY, sau khi tích hợp xong phải gửi lại IPN URL cho VNPAY. Tùy tài khoản sandbox:

- Nếu có merchant portal: nhập `{SITE_URL}/payments/vnpay/return` và `{SITE_URL}/api/v1/payments/vnpay/ipn`.
- Nếu không: gửi email hỗ trợ VNPAY kèm `vnp_TmnCode` và URL IPN.

URL phải **khớp chính xác** (https, không dấu `/` thừa). Nếu IPN không được đăng ký, giao dịch vẫn thanh toán được nhưng payment sẽ treo `pending` vì server không nhận được kết quả.

**Bước 5 — Test**

1. Tạo đơn, chọn VNPAY, bấm thanh toán.
2. Dùng thẻ test NCB `9704198526191432198`, tên `NGUYEN VAN A`, `07/15`, OTP `123456`.
3. Kiểm tra log có IPN, DB `payment.status = paid`.
4. Test thẻ lỗi (không đủ số dư, bị khóa) → `failed` → thanh toán lại.

**Lỗi thường gặp**

| Hiện tượng | Nguyên nhân |
| --- | --- |
| VNPAY báo `97` | Sai `HashSecret`, sai encoding, hoặc ký sai thứ tự |
| `01` khi IPN | `vnp_TxnRef` không khớp DB |
| `04` | Amount lệch (quên `*100`) |
| Thanh toán xong vẫn `pending` | IPN không tới: chưa public HTTPS, chưa đăng ký URL, firewall |
| `24` | Khách bấm hủy; map `failed` |
| Redirect sai domain | `vnp_ReturnUrl` không khớp cấu hình |

### 13.2. PayPal sandbox

**Bước 1 — Tạo tài khoản developer**

Mở <https://developer.paypal.com>, đăng nhập/đăng ký. Không cần tài khoản business Việt Nam cho sandbox.

**Bước 2 — Lấy Client ID / Secret**

1. Developer Dashboard → **Apps & Credentials**.
2. Chọn tab **Sandbox**.
3. Chọn **Default Application** hoặc **Create App** (tên `ElectroHub Demo`).
4. Copy **Client ID** và **Secret**.

**Bước 3 — Lấy tài khoản buyer/seller sandbox**

1. Dashboard → **Testing Tools** → **Sandbox Accounts**.
2. Mặc định có 2 account: `Personal` (buyer) và `Business` (seller).
3. Bấm `⋮` → **View/Edit Account** để lấy email + password.
4. Dùng Personal đăng nhập <https://www.sandbox.paypal.com/signin> khi thanh toán.

**Bước 4 — Tạo webhook**

1. Trong app vừa tạo → **Webhooks** → **Add Webhook**.
2. URL: `{SITE_URL}/api/v1/payments/paypal/webhook`.
3. Chọn event:
   - `PAYMENT.CAPTURE.COMPLETED`
   - `PAYMENT.CAPTURE.DENIED`
   - `PAYMENT.CAPTURE.REFUNDED`
   - `CHECKOUT.PAYMENT-APPROVAL.REVERSED`
4. Lưu và copy **Webhook ID**.

**Bước 5 — Điền `.env`**

```dotenv
PAYMENT_MODE=sandbox
SITE_URL=https://your-public-origin.example
PAYPAL_CLIENT_ID=<client_id>
PAYPAL_CLIENT_SECRET=<secret>
PAYPAL_API_BASE=https://api-m.sandbox.paypal.com
PAYPAL_WEBHOOK_ID=<webhook_id>
PAYPAL_CURRENCY=USD
PAYPAL_VND_PER_USD=25000
```

**Bước 6 — Test**

1. Tạo đơn, chọn PayPal → redirect sang PayPal.
2. Đăng nhập bằng Personal sandbox account.
3. Approve → quay về app → server capture → `paid`.
4. Kiểm tra webhook trong dashboard (**Webhooks** → **Event Logs**).
5. Bật **Negative Testing** trên Business sandbox account để test `INSUFFICIENT_FUNDS`, `INSTRUMENT_DECLINED`.

**Lưu ý Việt Nam**

- Sandbox dùng account US, không vướng hạn chế tài khoản VN.
- PayPal **không hỗ trợ VND**; app quy đổi VND → USD theo `PAYPAL_VND_PER_USD`.
- Trước khi go-live phải xác minh tài khoản PayPal Business VN có bật nhận thanh toán và rút được tiền hay không.

### 13.3. Nơi lưu credential

- `.env` ở máy dev (đã gitignore). Không commit.
- `.env.example` chỉ để placeholder, không có giá trị thật.
- Docker: `compose.yaml` chuyển tiếp từng biến payment vào container app; `.env` một mình **không** được inject. Thêm biến mới thì phải thêm cả vào `compose.yaml`.
- Chia sẻ trong team qua password manager (1Password/Bitwarden), **không gửi qua chat**.
- Nên tách bộ credential `dev` và `demo` nếu có nhiều môi trường.
- App **fail fast** khi `PAYMENT_MODE=sandbox` mà thiếu credential, thay vì fallback mock.

### 13.4. Trạng thái triển khai & việc còn lại

Đã xong trong repo:

- Config sandbox + derive URL từ `SITE_URL`, fail-fast khi thiếu credential.
- Adapter VNPAY (ký URL, verify callback, refund) và PayPal (OAuth, create/capture, webhook verify, refund, quy đổi USD).
- Payment session chuyển hướng gateway; IPN/return/webhook; retry khi `failed`.
- Refund giữ 72h, staff xem danh sách, admin confirm/reject; reject trả payment về `paid`.
- VAT 10% mặc định trên giá trị hàng sau giảm giá, lưu ở `orders.vat`; giỏ hàng chỉ xóa khi payment `paid`.
- Hiển thị tỷ giá PayPal và số tiền VNPAY ngay tại checkout khi chọn phương thức.
- Migration `0010`, `0011`, `0012` đã chạy trên SQL Server trong Docker.
- Test: `pytest` xanh; smoke E2E bằng `scripts/smoke_payments.py`.

Còn phụ thuộc môi trường ngoài:

1. `PAYPAL_WEBHOOK_ID` còn trống — chỉ tạo được khi có URL public HTTPS; thiếu nó webhook tự bỏ qua (`{"status":"ignored"}`), capture qua return URL vẫn hoạt động.
2. VNPAY sandbox hiện trả lỗi tra cứu khi mở trang thanh toán; cần VNPAY kích hoạt merchant/đăng ký Return + IPN hoặc hỗ trợ theo mã tra cứu.
3. Chưa có domain/tunnel HTTPS cố định; `SITE_URL` đang là `http://localhost:8000`.

---

## 14. Tài liệu tham khảo

- VNPAY — Thanh toán PAY: <https://sandbox.vnpayment.vn/apis/docs/thanh-toan-pay/pay.html>
- VNPAY — Querydr & Refund: <https://sandbox.vnpayment.vn/apis/docs/truy-van-hoan-tien/querydr&refund.html>
- VNPAY — Bảng mã lỗi: <https://sandbox.vnpayment.vn/apis/docs/bang-ma-loi/>
- VNPAY — Demo & thẻ test: <https://sandbox.vnpayment.vn/apis/vnpay-demo/>
- VNPAY — Đăng ký sandbox: <https://pay.vnpaytest.vn/dev-registration>
- PayPal — REST API getting started: <https://developer.paypal.com/api/rest/>
- PayPal — Orders v2: <https://developer.paypal.com/docs/api/orders/v2/>
- PayPal — Checkout integration: <https://developer.paypal.com/checkout/integrate>
- PayPal — Webhooks: <https://developer.paypal.com/api/webhooks/overview>
- PayPal — Webhook event names: <https://developer.paypal.com/api/rest/webhooks/event-names/>
- PayPal — Sandbox testing: <https://developer.paypal.com/sandbox-testing/overview>
- PayPal — Currency codes: <https://developer.paypal.com/reference/currency-codes>

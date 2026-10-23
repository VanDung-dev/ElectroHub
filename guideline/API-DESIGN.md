# API Design — FastAPI làm cổng giao tiếp

[← Trang bắt đầu / chọn thành viên](README.md) · [Tra cứu theo công việc](README.md#lookup)

[Dũng chốt contract](members/P1-DUNG.md#coordination); [Giàu làm catalog](members/P2-GIAU.md#tasks), [Hưng làm sales](members/P3-HUNG.md#tasks), [Gấm dùng contract để nối UI](members/P4-GAM.md#coordination).

<a id="principles"></a>

## 1. Nguyên tắc

* Versioned: `/api/v1/...`. HTML ở `/`, API ở `/api/v1`. Không lẫn.
* REST số nhiều: `/products, /categories, /brands, /cart, /orders, /auth`.
* Mọi response JSON snake_case. Tiền VND là int (đồng), không dùng float.
* Lỗi chuẩn duy nhất:
  ```json
  { "detail": "Sản phẩm không tồn tại" }
  ```
* Auth: JWT trong HttpOnly cookie do backend set. JS không đọc token. Admin check `role=admin` ở dependency, không check ở frontend.

<a id="contracts"></a>

## 2. Contract tối thiểu (Dũng P1 chốt, Giàu P2 / Hưng P3 implement, Gấm P4 dùng)

<a id="auth"></a>

### Auth (Dũng P1)

**Người thực hiện:** [Dũng P1 — nhiệm vụ và phối hợp](members/P1-DUNG.md#tasks). **UI sử dụng:** [Gấm P4](members/P4-GAM.md#coordination).

```text
POST /api/v1/auth/register  {email, password, name}
POST /api/v1/auth/login     {email, password} -> set cookie
POST /api/v1/auth/logout
GET  /api/v1/auth/me
GET  /api/v1/auth/csrf     -> {csrf_token}, set cookie CSRF
```

Đã implement ở nền tảng P1; Gấm cần xác nhận tích hợp UI trước khi nghiệm thu:

* Register trả `201`, user công khai `{id,email,name,role,created_at}`; không tự đăng nhập.
  Login trả user cùng format và set cookie `electrohub_access`; `/me` trả user hoặc `401`.
  Logout trả `200 {"detail":"Đã đăng xuất"}` và xóa cookie auth/CSRF.
* Email được chuẩn hóa chữ thường và unique; tên 1–100 đơn vị UTF-16 sau trim
  (khớp NVARCHAR(100), ký tự ngoài BMP như emoji chiếm hai đơn vị).
  Mật khẩu 8 ký tự trở lên, tối đa 72 byte UTF-8 để không bị bcrypt cắt ngắn.
  Register không nhận `role`; account mới luôn là `customer`. Admin được tạo bằng CLI trong README.
* Cookie host-only, HttpOnly, SameSite=Lax, path `/`; Secure theo `COOKIE_SECURE`.
  JWT hết hạn theo `ACCESS_TOKEN_MINUTES` (mặc định 60). Logout xóa cookie;
  thu hồi JWT bị sao chép trước hạn vẫn là việc cần làm trước production.
* **Mọi POST/PUT/PATCH/DELETE**, kể cả register/login/logout, cần CSRF:
  gọi `/api/v1/auth/csrf`, giữ cookie và gửi field `csrf_token` nhận được qua header `X-CSRF-Token`.
  Form HTML có thể gửi hidden field `csrf_token` do template context cấp.
  Token được ký HMAC và gắn với phiên, kiểm tra cả cookie lẫn header/form;
  lấy lại sau login/logout. Thiếu/sai token trả `403 {"detail":"CSRF token không hợp lệ"}`.
  Nếu trình duyệt gửi `Origin`, backend yêu cầu cùng origin với app.
* Validation trả `422 {"detail":"Dữ liệu không hợp lệ"}`; email trùng `409`;
  sai credentials/chưa đăng nhập `401`; thiếu quyền admin `403`.
  Response không chứa password, password_hash hoặc JWT; lỗi không phản chiếu request nhạy cảm.
* Auth nhận JSON; form HTML gửi qua fetch theo contract JSON. Cơ chế kiểm tra hidden CSRF
  đã sẵn sàng cho route form do nhóm bổ sung, không tự chuyển auth API sang form-urlencoded.

Ví dụ fetch và cách gắn router: [bàn giao P1](P1-HANDOFF.md#integration).

<a id="catalog"></a>

### Catalog (Giàu P2)

**Người thực hiện:** [Giàu P2 — nhiệm vụ và phối hợp](members/P2-GIAU.md#tasks). **UI sử dụng:** [Gấm P4](members/P4-GAM.md#coordination).

```text
GET /api/v1/categories            # cây đa cấp
GET /api/v1/brands
GET /api/v1/products?category=&brand=&q=&sort=price_asc|price_desc|newest&page=1&page_size=20
GET /api/v1/products/{slug}
POST /api/v1/products             # admin
PUT  /api/v1/products/{id}        # admin
GET /api/v1/wishlist  POST /api/v1/wishlist/{product_id}  DELETE ...
```

Response list chuẩn:

```json
{
  "items": [{ "id": 1, "slug": "esp32-devkit", "name": "ESP32 DevKit", "price": 185000, "sale_price": 165000, "stock": 42, "brand": "Espressif", "image": "/static/img/esp32.jpg" }],
  "total": 120, "page": 1, "page_size": 20
}
```

<a id="sales"></a>

### Sales (Hưng P3)

**Người thực hiện:** [Hưng P3 — nhiệm vụ và phối hợp](members/P3-HUNG.md#tasks). **UI sử dụng:** [Gấm P4](members/P4-GAM.md#coordination).

```text
GET  /api/v1/cart  POST /api/v1/cart/items {product_id, qty}  PUT /api/v1/cart/items/{id}  DELETE ...
POST /api/v1/cart/apply-voucher {code}
POST /api/v1/orders              # checkout từ cart -> trừ tồn kho trong transaction
GET  /api/v1/orders              # lịch sử user
GET  /api/v1/orders/{code}       # tra cứu
POST /api/v1/orders/{code}/pay   # COD xác nhận / mock VNPay
PATCH /api/v1/admin/orders/{code} # admin đổi trạng thái: pending->confirmed->shipping->done|cancelled
GET  /api/v1/admin/orders        # admin: danh sách/lọc trạng thái, mã đơn (bổ sung khi làm UI admin)
```

Đã chốt khi triển khai P3 (2026-10-23, Hưng — Dũng duyệt lại khi review PR):

* Cart và checkout **bắt buộc đăng nhập**; mọi API sales dùng cookie auth hiện có.
* Giá tính tiền = `sale_price` nếu có, ngược lại `price`; mọi số tiền là `int` VND.
* Phí ship cố định `30.000` đồng cho đơn có hàng; quy tắc này phải khớp nội dung
  chính sách vận chuyển Gấm hiển thị (còn chờ chốt ngưỡng miễn phí nếu có).
* Thanh toán MVP: `COD` và `CHUYEN_KHOAN_MOCK` (không gọi VNPay thật).
  `POST /orders/{code}/pay` với COD chỉ xác nhận, payment vẫn `pending`;
  với `CHUYEN_KHOAN_MOCK` payment chuyển `paid` kèm `reference` mock.
* Mã đơn `EH-XXXX` (4 ký tự), duy nhất; checkout trả `201`.
* `POST /cart/apply-voucher` chỉ xem trước giảm giá, **không** trừ lượt;
  checkout nhận `voucher_code` và trừ đúng 1 lượt trong transaction.
* Trạng thái đơn: `pending -> confirmed -> shipping -> done`, hủy được từ
  `pending|confirmed`; hủy đơn hoàn kho, hoàn lượt voucher và đánh `refunded`
  cho payment đã trả.
* Tra cứu công khai `GET /orders/{code}?phone=…`; owner đang đăng nhập hoặc admin
  không cần số điện thoại. Sai mã/sai số điện thoại đều trả `404`.
* `orders.voucher_code` được thêm ngoài ERD cũ để lưu vết và hoàn lượt voucher.

<a id="implementation"></a>

## 3. Quy định implement

* Router mỏng, service dày. Validate bằng Pydantic `Query/Path` (page >= 1, qty 1..99).
* `GET` không bao giờ thay đổi dữ liệu. Checkout/trừ kho phải là `POST` + transaction DB.
* Mọi API admin gắn `Depends(require_admin)`.
* Mọi API mới phải có ví dụ trên `/docs` + 1 test `httpx` + 1 dòng trong `test_main.http`.
* Đổi contract (thêm field required, đổi path): Giàu P2 / Hưng P3 báo trước cho Gấm P4, bump doc, không tự đổi lặng lẽ.

<a id="pending-decisions"></a>

## 4. Những điểm cần Dũng và chủ domain chốt

Các mục dưới đây là điểm chưa thống nhất hoặc chưa được mô tả đủ trong guideline hiện tại, chưa phải quyết định mới. Khi task đụng đến mục nào, trao đổi với đúng người ở cột cuối; cập nhật contract và tài liệu liên quan sau khi thống nhất, rồi báo cho Gấm trước khi nối UI.

| Điểm cần chốt | Đối chiếu ở đâu | Người phối hợp |
| --- | --- | --- |
| `price`/`sale_price`: giá bán, giá gạch, giá dùng để lọc và tính tiền | [Ví dụ catalog](#catalog) và [card PLP](HSHOP-ANALYSIS.md#plp) đang mô tả chưa khớp | [Dũng](members/P1-DUNG.md#coordination) + [Giàu](members/P2-GIAU.md#coordination) + [Hưng](members/P3-HUNG.md#coordination) + [Gấm](members/P4-GAM.md#coordination) — **đã chốt 2026-10-23:** tính tiền dùng `sale_price` nếu có, ngược lại `price`; lọc/sort theo giá còn chờ Giàu chốt |
| Tên và hành vi thanh toán giả lập: `VNPAY_MOCK` hay `CHUYEN_KHOAN_MOCK` | [API sales](#sales), [ERD payments](DB-MIGRATION.md#erd), [checkout](HSHOP-ANALYSIS.md#checkout) | [Dũng](members/P1-DUNG.md#coordination) + [Hưng](members/P3-HUNG.md#coordination) + [Gấm](members/P4-GAM.md#coordination) — **đã chốt 2026-10-23:** `CHUYEN_KHOAN_MOCK`, COD thu khi giao |
| Field/endpoint còn thiếu cho filter giá, sort tên, upload, wishlist/compare và PDP; nơi lưu dữ liệu tương ứng | [Catalog](#catalog), [ERD](DB-MIGRATION.md#erd), [PLP](HSHOP-ANALYSIS.md#plp), [PDP](HSHOP-ANALYSIS.md#pdp) | [Dũng](members/P1-DUNG.md#coordination) + [Giàu](members/P2-GIAU.md#coordination) + [Gấm](members/P4-GAM.md#coordination) |
| Mua hàng có cần đăng nhập; xác minh mã + số điện thoại khi tra cứu; xử lý gửi checkout lặp, hủy đơn/hoàn kho và trạng thái payment | [Sales](#sales), [checkout](HSHOP-ANALYSIS.md#checkout), [transaction](DB-MIGRATION.md#data-safety) | [Dũng](members/P1-DUNG.md#coordination) + [Hưng](members/P3-HUNG.md#coordination); [Giàu](members/P2-GIAU.md#coordination) khi liên quan kho, [Gấm](members/P4-GAM.md#coordination) khi liên quan UI — **đã chốt 2026-10-23:** bắt buộc đăng nhập; tra cứu bằng mã + số điện thoại; checkout lặp bị chặn khi giỏ trống; hủy đơn hoàn kho/voucher, payment đã trả chuyển `refunded` |
| CSRF và lỗi validation đã có [contract P1](#auth), chờ Gấm xác nhận; response rỗng/upload còn cần chốt | [Nguyên tắc API](#principles), [HTML](CODING-CONVENTION.md#html), [JS](CODING-CONVENTION.md#javascript) | [Dũng](members/P1-DUNG.md#coordination) + [Gấm](members/P4-GAM.md#coordination), chủ API liên quan |
| Số bài blog/review tối thiểu khi nghiệm thu | [Yêu cầu content](HSHOP-ANALYSIS.md#content) và [DoD MVP](DEFINITION-OF-DONE.md#mvp) đang ghi khác nhau | [Dũng](members/P1-DUNG.md#coordination) + [Gấm](members/P4-GAM.md#coordination) |

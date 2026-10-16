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
```

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
```

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
| `price`/`sale_price`: giá bán, giá gạch, giá dùng để lọc và tính tiền | [Ví dụ catalog](#catalog) và [card PLP](HSHOP-ANALYSIS.md#plp) đang mô tả chưa khớp | [Dũng](members/P1-DUNG.md#coordination) + [Giàu](members/P2-GIAU.md#coordination) + [Hưng](members/P3-HUNG.md#coordination) + [Gấm](members/P4-GAM.md#coordination) |
| Tên và hành vi thanh toán giả lập: `VNPAY_MOCK` hay `CHUYEN_KHOAN_MOCK` | [API sales](#sales), [ERD payments](DB-MIGRATION.md#erd), [checkout](HSHOP-ANALYSIS.md#checkout) | [Dũng](members/P1-DUNG.md#coordination) + [Hưng](members/P3-HUNG.md#coordination) + [Gấm](members/P4-GAM.md#coordination) |
| Field/endpoint còn thiếu cho filter giá, sort tên, upload, wishlist/compare và PDP; nơi lưu dữ liệu tương ứng | [Catalog](#catalog), [ERD](DB-MIGRATION.md#erd), [PLP](HSHOP-ANALYSIS.md#plp), [PDP](HSHOP-ANALYSIS.md#pdp) | [Dũng](members/P1-DUNG.md#coordination) + [Giàu](members/P2-GIAU.md#coordination) + [Gấm](members/P4-GAM.md#coordination) |
| Mua hàng có cần đăng nhập; xác minh mã + số điện thoại khi tra cứu; xử lý gửi checkout lặp, hủy đơn/hoàn kho và trạng thái payment | [Sales](#sales), [checkout](HSHOP-ANALYSIS.md#checkout), [transaction](DB-MIGRATION.md#data-safety) | [Dũng](members/P1-DUNG.md#coordination) + [Hưng](members/P3-HUNG.md#coordination); [Giàu](members/P2-GIAU.md#coordination) khi liên quan kho, [Gấm](members/P4-GAM.md#coordination) khi liên quan UI |
| CSRF cho fetch, lỗi validation, response rỗng/upload và cách dùng `api.js` | [Nguyên tắc API](#principles), [HTML](CODING-CONVENTION.md#html), [JS](CODING-CONVENTION.md#javascript) | [Dũng](members/P1-DUNG.md#coordination) + [Gấm](members/P4-GAM.md#coordination), chủ API liên quan |
| Số bài blog/review tối thiểu khi nghiệm thu | [Yêu cầu content](HSHOP-ANALYSIS.md#content) và [DoD MVP](DEFINITION-OF-DONE.md#mvp) đang ghi khác nhau | [Dũng](members/P1-DUNG.md#coordination) + [Gấm](members/P4-GAM.md#coordination) |

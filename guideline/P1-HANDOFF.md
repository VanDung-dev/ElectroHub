# Bàn giao nền tảng — Nguyễn Lê Văn Dũng (P1)

[← Phần việc P1](members/P1-DUNG.md) · [Kế hoạch nhóm](README.md) · [Chạy dự án](../README.md)

## Phạm vi và trạng thái

Đối chiếu checkout ngày 2026-10-23: `app/`, tests và Alembic ban đầu rỗng,
Docker chạy endpoint Hello World; lúc bắt đầu chưa có nhánh `develop`.
Nhánh triển khai hiện tại là `feature/core-platform-auth` theo Git workflow.
Đã tạo `develop` từ `main` tại commit gốc `7c98434`, cũng là điểm bắt đầu của nhánh feature.
Đây là bàn giao kỹ thuật để review; không phải xác nhận đã qua giai đoạn 1/2 hoặc nghiệm thu MVP.

| Ticket local | Owner / giai đoạn | Loại | Đầu ra / điều kiện chấp nhận | Trạng thái |
| --- | --- | --- | --- | --- |
| P1-01 Nền tảng | Dũng / GĐ1 | Tự làm | App chuẩn, config/logging, health DB, format lỗi, template/static routing | Review — test local và Docker pass; chờ review PR |
| P1-02 Auth | Dũng / GĐ2 | Phối hợp: Gấm | Register/login/logout/me, cookie/CSRF, admin guard; Gấm xác nhận fetch/form | Review — API pass trên SQL Server thật; chờ UI |
| P1-03 Users/migration/admin | Dũng / GĐ2 | Tự làm | Schema users Unicode/unique/role, migration hai chiều, CLI admin chạy lại an toàn | Review — SQLite và SQL Server Docker pass; chờ review PR |
| P1-04 Docker/kiểm tra | Dũng / GĐ1, GĐ4 | Tự làm | DB → init → migrate → app, lint/test local và SQL Server smoke | Review — Docker local pass; chờ review PR |
| P1-05 Duyệt ERD/API | Dũng / GĐ1 | Phối hợp: Giàu, Hưng, Gấm | Chủ domain đề xuất, Dũng review và ghi contract thống nhất | Todo — các điểm tại API-DESIGN còn mở |
| P1-06 Tích hợp/demo | Dũng / GĐ3–4 | Phối hợp: cả nhóm | Domain routers, transaction/stock, UI, quyền, test trên máy sạch | Todo — chờ P2/P3/P4 |

Đây là ticket nháp trong repo; chưa tạo issue/Kanban hay gửi tin cho thành viên.
Deadline và trạng thái nhóm thực tế cần cập nhật ở Kanban theo Git workflow.

<a id="verification"></a>

## Checklist kiểm chứng P1

`[x]` ghi phần kỹ thuật đã kiểm chứng ngày 2026-10-23. Ticket vẫn ở Review cho đến khi
đạt đủ điều kiện PR/phối hợp; checklist này chưa xác nhận qua giai đoạn hoặc hoàn thành MVP.

- [x] Khung app/config/logging, error chuẩn, health DB và template/static routing có code và test.
- [x] Python `.venv` 3.13; lint/format pass, `pytest -q` đạt **31 test pass** (exit code 0).
- [x] Auth/cookie/CSRF kể cả form, JWT lỗi/hết hạn, role từ DB, password bcrypt/UTF-8,
  lỗi không lộ input và migration hai chiều được test bằng DB SQLite tạm.
- [x] Docker build và chuỗi SQL Server → init DB → migration → app chạy thành công;
  SQL Server và app healthy, app chạy bằng user không phải root.
- [x] Kết nối ODBC và auth HTTP trên SQL Server thật **16.0.4305.5** pass:
  register/login/me/logout, CSRF và chặn Origin khác.
- [x] CLI tạo admin và chạy lại an toàn; không nâng quyền customer; kiểm tra admin/customer,
  email trùng và dữ liệu tiếng Việt trên SQL Server thật đều pass.
- [x] Migration SQL Server `downgrade base → upgrade head`, `alembic check` và smoke auth
  sau khi khởi động lại app đều pass (exit code 0).
- [x] Truy cập từ host: health và Swagger trả 200; template rỗng trả HTML 503 đúng thiết kế.
- [ ] Gấm xác nhận auth/CSRF và route/template trên UI thật.
- [ ] Review/approve PR theo Git workflow; kết quả kiểm tra thủ công ghi trong PR.
- [ ] Nghiệm thu trên máy thứ hai/Linux x86-64 và demo E2E với P2/P3/P4.

Docker được kiểm tra trên macOS ARM qua OrbStack, SQL Server chạy image amd64 bằng giả lập.
Project test riêng `electrohub-p1-check` dùng env/DB/cổng riêng; đã dừng container/network,
giữ volume. `.env` và dữ liệu phát triển hiện có không bị thay đổi.
Pytest có một cảnh báo deprecation của Starlette với `httpx`; không có test thất bại.

<a id="integration"></a>

## Đầu vào cho Giàu và Hưng

Model kế thừa `Base` từ `app.core.database`; dùng `DbSession` từ `app.core.deps`
trong router/service, `CurrentUser` cho API cần đăng nhập và `Depends(require_admin)` cho admin.
Quyền được lấy từ bản ghi user hiện tại; không tin role do frontend gửi.

Sau khi schema được duyệt, thêm model vào `app/models/__init__.py`, tạo migration và kiểm tra
upgrade/downgrade trên DB thử nghiệm. Không gọi `create_all()`, không sửa migration đã merge.
Router domain tự khai báo prefix `/api/v1/...`; đăng ký tại `create_app()` trong `app/main.py`
khi router đã có triển khai và test. Các router rỗng chưa được ghép để tránh giả API đã hoàn thành.
CSRF dependency toàn app bảo vệ cả router mới.

## Đầu vào cho Gấm

`app/core/pages.py` đăng ký các template hiện có:

| HTML route | Template trong `app/templates/` |
| --- | --- |
| `/` | `index.html` |
| `/collections/all` | `product/list.html` |
| `/products/{slug}` | `product/detail.html` |
| `/cart`, `/checkout`, `/cart/tracking` | `cart/cart.html`, `cart/checkout.html`, `cart/tracking.html` |
| `/account/login`, `/account/register` | `auth/login.html`, `auth/register.html` |
| `/blogs/all`, `/blogs/{slug}` | `blog/list.html`, `blog/detail.html` |
| `/admin/products`, `/admin/orders` | `admin/products.html`, `admin/orders.html` (backend kiểm tra admin) |

Đây là mapping khởi đầu theo scaffold, cần Gấm xác nhận. Template rỗng trả HTML 503;
không có layout/CSS/JS mới. `/static` đã mount; dùng `url_for('static', path='...')`.
`slug` và `csrf_token` có trong context của template được render; token đặt trong hidden input
với form POST. Blog/policy/wishlist/compare và biến thể route còn chờ hợp đồng, chưa tự sinh nội dung/API.

Fetch cùng origin giữ cookie tự động. JWT chỉ ở HttpOnly cookie, không lưu vào JS/localStorage.
Ví dụ để nối vào `api.js` của Gấm:

```js
const csrf = await fetch('/api/v1/auth/csrf').then((res) => res.json());
const res = await fetch('/api/v1/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf.csrf_token },
  body: JSON.stringify({ email, password }),
});
if (!res.ok) throw new Error((await res.json()).detail);
const user = await res.json();
// Lấy CSRF mới trước request ghi tiếp theo vì login đã đổi phiên.
```

API hiện trả JSON kể cả logout (`200 {detail}`), lỗi chỉ có `{detail: string}`.
Validation không echo email/password/body. Không tự retry request ghi khi CSRF lỗi;
lấy token mới và để người dùng gửi lại thao tác. Ví dụ HTTP tương tác ở `test_main.http`.

## Việc Dũng cần chốt tiếp với nhóm

1. Giàu + Hưng: giá áp dụng, sale_price, tồn kho/transaction, checkout lặp, hủy/hoàn kho,
   tên payment mock và vòng đời order/payment; nhận đề xuất schema trước khi duyệt migration business.
2. Gấm: xác nhận routes và auth/CSRF/error contract trên UI thật; thống nhất blog tĩnh/API
   và số bài theo tag/review. Nếu blog qua API, phân owner trước khi viết.
3. Nhóm: thống nhất nơi Kanban; mở PR về `develop` và review theo Git workflow.
4. Docker/auth/migration local đã pass trên OrbStack; tiếp tục chạy trên
   máy thứ hai/Linux x86-64 trước nghiệm thu môi trường. Không downgrade DB nhóm để thử.
5. Khi P2/P3/P4 sẵn sàng: ghép router, review quyền/transaction, demo E2E và test máy sạch.

## Giới hạn triển khai

Logout xóa cookie; JWT bị sao chép còn hiệu lực đến expiry. Chưa có refresh/revocation hoặc rate limit.
Trước production cần xử lý các mục này, bật HTTPS/Secure cookie, đổi từ tài khoản DB `sa`
sang tài khoản ứng dụng và dùng chứng chỉ DB tin cậy. Môi trường Compose hiện là development.

Nguồn kỹ thuật đối chiếu:
[SQLAlchemy SQL Server](https://docs.sqlalchemy.org/en/20/dialects/mssql.html),
[Microsoft ODBC Driver 18](https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server?view=sql-server-ver17),
[PyJWT](https://pyjwt.readthedocs.io/en/stable/usage.html),
[OWASP signed double-submit CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html#signed-double-submit-cookie-recommended).

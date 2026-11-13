# Bàn giao nền tảng & Hạ tầng — Nguyễn Lê Văn Dũng (P1)

[← Phần việc P1](members/P1-DUNG.md) · [Kế hoạch nhóm](README.md) · [Kiến trúc DB](DB-MIGRATION.md) · [Chạy dự án](../README.md)

---

## 1. Phạm vi và tổng kết bàn giao

Nguyễn Lê Văn Dũng (Lead & Nền tảng) chịu trách nhiệm chính về kiến trúc ứng dụng, phân quyền xác thực, cơ sở dữ liệu Microsoft SQL Server 2022, hạ tầng Docker Compose đa dịch vụ và bộ thành phần T-SQL môn học.

### Bảng trạng thái các hạng mục kỹ thuật:

| Hạng mục | Phạm vi | Mô tả chi tiết | Trạng thái |
| :--- | :--- | :--- | :--- |
| **P1-01 Nền tảng Core** | Tự làm | Cấu trúc FastAPI, quản lý cấu hình `.env`, logging chuẩn, định dạng lỗi `{ "detail": "..." }`, routing static và Jinja2 templates | **Hoàn thành 100%** (106 tests passed) |
| **P1-02 Auth & Security** | — | Đăng ký, đăng nhập JWT qua HttpOnly cookie, cơ chế chống CSRF kép, RBAC phân quyền (Customer, Staff, Manager) | **Hoàn thành 100%** (Đã tích hợp UI & API) |
| **P1-03 Schema & Alembic** | Tự làm | Schema chuẩn Unicode NVARCHAR, migration 2 chiều an toàn, CLI `app.create_admin` idempotent, 3 tài khoản demo mặc định | **Hoàn thành 100%** (Upgrade/Downgrade sạch) |
| **P1-04 Docker Dual-DB** | Tự làm | Triển khai song song DB Web App (1433) và DB Test môn học (1434), tự động hóa nạp dữ liệu qua `init-test.sh`, hỗ trợ kết nối từ SSMS Parallels | **Hoàn thành 100%** (Container healthy) |
| **P1-05 T-SQL Suite Môn học** | Tự làm | Trọn bộ 8 kịch bản T-SQL: Rules, Defaults, Triggers, Stored Procedures, Cursors, Views, Functions, Transactions và test tự động | **Hoàn thành 100%** (`test_all.sql` pass) |
| **P1-06 Tối ưu hóa hiệu năng** | Tự làm | Áp dụng triết lý Ponytail & Graphify: giảm thiểu N+1 queries, loại bỏ tính toán dư thừa trong DB, cache disk template | **Hoàn thành 100%** (Ruff pass, tests xanh) |

---

<a id="verification"></a>

## 2. Checklist kiểm chứng kỹ thuật (Technical Verification)

- [x] **Khung ứng dụng & Kiến trúc**: FastAPI 0.115+, Pydantic v2, cấu hình tập trung qua `app.core.config.get_settings`.
- [x] **Kiểm thử tự động**: Bộ test suite gồm **106/106 tests passed** (Auth, Catalog, Cart, Order, Payment Gateways, Platform, SEO).
- [x] **Định dạng & Tiêu chuẩn mã nguồn**: Đạt chuẩn 100% qua `ruff check .` và `ruff format --check .`.
- [x] **Bảo mật Auth**: Cookie `HttpOnly`, `SameSite=Lax`, kiểm tra CSRF token bắt buộc cho mọi request ghi, mã hóa mật khẩu bcrypt chống lộ input.
- [x] **Môi trường Docker Compose**:
  - `electrohub-app-1`: Chạy FastAPI non-root user, tích hợp health check.
  - `electrohub-sqlserver-1`: SQL Server 2022 cho Web App (Cổng 1433).
  - `electrohub-sqlserver-test`: SQL Server 2022 độc lập cho môn học (Cổng 1434).
  - `electrohub-mailpit`: Hộp thư ảo SMTP giả lập kiểm thử email marketing (Cổng 1025, 8025).
  - `electrohub-localtunnel-1`: Hỗ trợ public tunnel HTTPS cho webhook thanh toán.
- [x] **Hỗ trợ SSMS trên máy ảo Windows (Parallels)**: Cấu hình bind `0.0.0.0` và gateway `10.211.55.2`, mở kết nối thông suốt từ SSMS vào cả 2 database.
- [x] **T-SQL Suite môn học**: Đầy đủ 4 Triggers, 11 Stored Procedures & Functions, 3 Cursors, 5 Rules & Defaults, kịch bản giao dịch an toàn với `UPDLOCK, ROWLOCK`.

---

<a id="integration"></a>

## 3. Hướng dẫn tích hợp cho các thành viên

### Dành cho Giàu (P2 - Catalog) và Hưng (P3 - Sales):
1. **Model SQLAlchemy**: Kế thừa `Base` từ `app.core.database`. Khi khai báo quan hệ, sử dụng `lazy="selectin"` để tránh lỗi N+1 query.
2. **Session DB**: Inject qua `DbSession = Annotated[Session, Depends(get_db)]` từ `app.core.deps`.
3. **Giao dịch đặt hàng / Trừ kho**: Luôn gói trong `with db.begin():` và kiểm tra điều kiện tồn kho an toàn hoặc sử dụng `WITH (UPDLOCK)`.
4. **Phân quyền người dùng**:
   - Khách hàng đăng nhập: `CurrentUser = Annotated[User, Depends(get_current_user)]`.
   - Nhân viên: `Depends(require_staff)`.
   - Quản trị viên: `Depends(require_admin)`.


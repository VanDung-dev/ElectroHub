# ElectroHub

Hệ thống thương mại điện tử chuyên cung cấp linh kiện điện tử, vi điều khiển và thiết bị IoT. Dự án kết hợp giữa kiến trúc backend hiện đại (**Python 3.13**, **FastAPI**) và hệ quản trị cơ sở dữ liệu chuyên sâu (**Microsoft SQL Server 2022**) với đầy đủ Triggers, Cursors, Stored Procedures, Views, Functions và Rules phục vụ thực hành môn Hệ Quản Trị Cơ Sở Dữ Liệu.

---

## 🧭 Cẩm Nang Tra Cứu Dự Án

Tài liệu dự án được phân tách rõ ràng thành 3 phần chính phục vụ các nhu cầu khác nhau:

| Tài liệu | Mục đích sử dụng | Nội dung chính |
| :--- | :--- | :--- |
| 📖 **[DEV.md](DEV.md)** | **Dành cho Lập trình viên** | Hướng dẫn cài đặt local/Docker, kiến trúc Dual-DB (`1433` & `1434`), kết nối SSMS trên Parallels, migration Alembic, tài nguyên T-SQL môn học, lint & test. |
| 🎯 **[DEMO.md](DEMO.md)** | **Dành cho Demo & Nghiệm thu** | Tài khoản demo 3 vai trò (`Demo@2026!`), thông tin thẻ sandbox VNPAY & PayPal, 3 kịch bản demo mẫu (Khách hàng, Quản trị, Nghiệm thu T-SQL). |
| 📋 **[guideline/](guideline/README.md)** | **Kế hoạch & Tiến độ Đồ án** | Báo cáo chi tiết các phần đã hoàn thành, phân công thành viên, tiêu chuẩn nghiệm thu DoD, đặc tả API và quy chuẩn Git. |

---

## ⚡ Khởi Chạy Nhanh (Quick Start)

Dự án sử dụng **Docker Compose** đóng gói toàn bộ ứng dụng, 2 cụm SQL Server độc lập, Mailpit và LocalTunnel.

### 1. Chuẩn bị cấu hình:
```bash
# Sao chép cấu hình mẫu
cp .env.example .env

# Sinh SECRET_KEY và điền vào .env
docker run --rm python:3.13.9-slim-bookworm python -c "import secrets; print(secrets.token_urlsafe(48))"
```
*(Mật khẩu SA mặc định được đặt sẵn trong `.env` là `MSSQL_SA_PASSWORD=ElectroHub@123`).*

### 2. Khởi động hệ thống:
```bash
docker compose up -d --build
```

### 3. Nạp dữ liệu sản phẩm mẫu:
```bash
docker compose exec app python -m app.seeds.seed
```

Hệ thống sẵn sàng tại:
- **Trang chủ Cửa hàng**: [http://localhost:8000](http://localhost:8000)
- **Tài liệu API Swagger**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Hộp thư thử nghiệm Mailpit**: [http://localhost:8025](http://localhost:8025)

---

## 🌟 Tính Năng Nổi Bật

- **Storefront & Catalog**: Duyệt danh mục linh kiện, tìm kiếm, lọc sản phẩm theo khoảng giá và thương hiệu, tối ưu SEO Server-Side Rendering (SSR).
- **Giỏ hàng & Khuyến mãi**: Áp dụng mã giảm giá voucher (`WELCOME10`), tính thuế VAT, giao dịch checkout nguyên tử (Atomic Transaction) chống Race Condition.
- **Thanh toán Đa kênh**: Hỗ trợ chế độ mô phỏng (Mock) và kết nối cổng thanh toán thật Sandbox với **VNPAY** (ATM nội địa) và **PayPal** (VISA quốc tế).
- **Phân quyền người dùng (RBAC)**: Phân tách rõ ràng quyền hạn giữa Khách hàng (`/account/orders`), Nhân viên giao hàng (`/staff/orders`), và Quản trị viên (`/admin/products`, `/admin/refunds`, `/admin/newsletter`).
- **Email Marketing Tự Động**: Tự động gửi email chào mừng kèm voucher khi đăng ký nhận tin; gửi chiến dịch marketing hàng loạt qua background tasks.
- **Cơ sở dữ liệu T-SQL Chuyên sâu ([`sql/`](sql/))**: 
  - Rules & Defaults độc lập (`sp_bindrule`, `sp_bindefault`).
  - Triggers trừ tồn kho, tự động hoàn kho khi hủy đơn, chống sửa/xóa đơn đã đóng.
  - Stored Procedures giao dịch an toàn với `TRY...CATCH` và Savepoints.
  - Cursors phân hạng khách hàng VIP tặng voucher tri ân và quét đơn quá hạn.
  - Views và UDF báo cáo doanh thu kinh doanh.

---

## 🛠️ Công Nghệ Sử Dụng (Tech Stack)

- **Backend**: Python 3.13, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2.
- **Database**: Microsoft SQL Server 2022 Developer Edition.
- **Frontend**: Jinja2 Template SSR, HTML5, CSS Variables, Vanilla JS.
- **DevOps & Testing**: Docker Compose v2, Mailpit, LocalTunnel, Ruff Linter, Pytest (**106/106 tests passed**).

---

## 👥 Đội Ngũ Thực Hiện (Nhóm ElectroHub)

| Thành viên | Phụ trách chính | Phạm vi Domain |
| :--- | :--- | :--- |
| **P1 — Nguyễn Lê Văn Dũng** | **Lead & Nền tảng** | Kiến trúc core, Auth & RBAC, Docker Dual-DB, T-SQL Suite môn học, Review PR. |
| **P2 — Nguyễn Hữu Giàu** | **Catalog Domain** | Category, Brand, Product, Search & Filter, Quản lý ảnh, Seed Catalog. |
| **P3 — Lê Nhật Hưng** | **Sales & Payment** | Cart, Order, Voucher, Thanh toán Sandbox (PayPal / VNPAY) & Hoàn tiền. |
| **P4 — Phạm Thị Hồng Gấm** | **Frontend UI/UX** | Giao diện Storefront, Admin Panel, Quản lý Jinja2 template, Client API JS. |

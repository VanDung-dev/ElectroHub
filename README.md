# ElectroHub

Đồ án web bán hàng dùng Python 3.13, FastAPI, HTML/CSS/JS và SQL Server 2022.
Storefront đơn giản, API sản phẩm/giỏ hàng/đơn hàng, SEO cơ bản, newsletter và thanh toán tùy cấu hình.
Phân công và tiến độ: [guideline](guideline/README.md) · [bàn giao P1](guideline/P1-HANDOFF.md).

Chọn **một** cách chạy; thực hiện lệnh tại thư mục gốc repo:

| Máy của bạn | Cách chạy |
| --- | --- |
| Có Docker Desktop hoặc OrbStack | [Docker: chạy cả app và SQL Server](#docker) |
| Đã cài SQL Server trên Windows | [Windows: chạy Python trực tiếp](#windows) |

Trước lần chạy đầu, sao chép `.env.example` thành `.env`.
Nếu đã có `.env`, bổ sung biến còn thiếu và giữ nguyên mật khẩu DB. Không commit `.env`.

<a id="docker"></a>

## 1. Docker / OrbStack

Bật Docker Desktop hoặc OrbStack. Máy chỉ cần Docker và Compose v2; Python/ODBC được cài trong image.

**Cấu hình lần đầu:** tạo khóa bằng lệnh sau, rồi dán kết quả vào `SECRET_KEY=` trong `.env`:

```sh
docker run --rm python:3.13.9-slim-bookworm python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Điền thêm `MSSQL_SA_PASSWORD=` trong `.env`: ít nhất 8 ký tự, gồm 3 trong 4 nhóm
chữ hoa, chữ thường, số, ký tự đặc biệt. Giữ các biến khác theo `.env.example`.

**Khởi động:**

```sh
docker compose up --build --wait --wait-timeout 240
```

Sau khi app khởi động lần đầu, nạp một vài sản phẩm minh họa để xem luồng cửa hàng:

```sh
docker compose exec app python -m app.seeds.seed
```

DB, migration và ba tài khoản demo được khởi tạo tự động trước khi app chạy.
Database mới cũng có sẵn các tài khoản sau, mật khẩu chung là `Demo@2026!`:

| Vai trò | Email |
| --- | --- |
| Khách hàng | `customer.demo@example.com` |
| Nhân viên | `staff.demo@example.com` |
| Quản lý | `manager.demo@example.com` |

Đây là tài khoản demo với mật khẩu công khai. Chạy lại Compose chỉ thêm tài khoản còn thiếu,
không đặt lại mật khẩu hay thay đổi quyền/tên của tài khoản đã có.
Khi chạy Python trực tiếp, có thể nạp bằng `python -m app.seeds.accounts` sau migration.

Các lần sau dùng lại lệnh khởi động trên; thay đổi code cần build lại.
Có thể đổi `APP_PORT` hoặc `SQLSERVER_PORT` trong `.env` nếu cổng bị trùng.
Kết nối từ SSMS vào DB Docker: `localhost,1433`, SQL Server Authentication,
user `sa`, mật khẩu `MSSQL_SA_PASSWORD` (đổi 1433 theo `SQLSERVER_PORT` nếu đã chỉnh).

**Dừng và giữ dữ liệu:**

```sh
docker compose down
```

Không thêm `-v` vì sẽ xóa dữ liệu. Đổi mật khẩu trong `.env` không tự đổi mật khẩu DB đã tạo.
SQL Server cần ít nhất 2 GB RAM; dành thêm RAM cho app. Máy Mac ARM chạy SQL Server qua giả lập:
đã test được trên OrbStack; môi trường SQL Server được Microsoft hỗ trợ là Linux x86-64.

<a id="windows"></a>

## 2. SQL Server trên Windows + Python

**Chuẩn bị một lần:**

1. Cài Python **3.13**, SQL Server 2022 Developer và SSMS.
2. Cài [Microsoft ODBC Driver 18 for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server?view=sql-server-ver17).
3. Trong SQL Server Configuration Manager, bật TCP/IP cho instance đang dùng.
   Ở TCP/IP → IP Addresses → IPAll, xóa `TCP Dynamic Ports`, đặt `TCP Port = 1433`,
   rồi restart dịch vụ SQL Server. Nếu dùng cổng khác, đổi số cổng trong URL bên dưới.
   [Hướng dẫn Microsoft](https://learn.microsoft.com/en-us/sql/database-engine/configure-windows/configure-a-server-to-listen-on-a-specific-tcp-port?view=sql-server-ver17).
4. Mở SSMS bằng Windows Authentication, kết nối đúng instance, chạy file
   [docker/init.sql](docker/init.sql) để tạo DB `ElectroHub` nếu chưa có.
   File này cũng dùng được cho SQL Server cài trực tiếp trên Windows.

Mở **PowerShell** tại repo và chạy (bỏ lệnh tạo venv nếu đã có `.venv` dùng Python 3.13):

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Dán khóa vừa tạo vào `SECRET_KEY=` trong `.env`. Thêm dòng sau để dùng
**Windows Authentication** bằng tài khoản Windows đang chạy Python; tài khoản này cần quyền trên DB:

```dotenv
DATABASE_URL="mssql+pyodbc://localhost:1433/ElectroHub?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
```

`DATABASE_URL` ghi đè các biến kết nối `SQLSERVER_*` cho Python local.
Nếu dùng **SQL Server Authentication**, bỏ dòng `DATABASE_URL`, điền `SQLSERVER_USER`
và `MSSQL_SA_PASSWORD` theo SQL login của bạn; server cần bật Mixed Mode và login có quyền trên DB.
Thông tin host/port/database lấy từ các biến `SQLSERVER_*` trong `.env.example`.

**Khởi động:**

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Nạp catalog minh họa (tùy chọn):

```powershell
.\.venv\Scripts\python.exe -m app.seeds.seed
```

Chạy lại hai lệnh này sau khi pull code để cập nhật DB. Dừng app bằng `Ctrl+C`.
App mặc định dùng cổng 8000; muốn đổi cổng local, thêm `--port 8001` vào lệnh uvicorn
(`APP_PORT` chỉ dùng cho Compose).

## Mở ứng dụng và tạo admin

- [Trang web](http://localhost:8000), danh sách tại `/collections/all`, sản phẩm theo slug tại `/products/{slug}`.
- Sitemap: `/sitemap.xml`; robots: `/robots.txt`.
- [Swagger / thử API](http://localhost:8000/docs).
- [Kiểm tra kết nối DB](http://localhost:8000/api/v1/health).
- [Hộp thư thử nghiệm Mailpit (Docker)](http://localhost:8025): xem email chào mừng và chiến dịch marketing gửi nội bộ.

Đổi 8000 trong URL nếu đã cấu hình cổng khác. Tạo admin bằng lệnh ứng với cách chạy,
thay email/tên của bạn và nhập mật khẩu khi được hỏi:

```sh
# Docker: app phải đang chạy
docker compose exec app python -m app.create_admin --email dung@example.com --name "Nguyễn Lê Văn Dũng"
```

```powershell
# Windows: mở PowerShell thứ hai tại repo
.\.venv\Scripts\python.exe -m app.create_admin --email dung@example.com --name "Nguyễn Lê Văn Dũng"
```

Chạy lại lệnh không đổi mật khẩu tài khoản đã có. Đăng ký trên trang tạo tài khoản chỉ tạo customer.
Tạo nhân viên bằng cùng lệnh với `--role staff`:

```sh
docker compose exec app python -m app.create_admin --role staff --email nhanvien@example.com --name "Nhân viên cửa hàng"
```

Khách hàng dùng `/account/orders`, nhân viên dùng `/staff/orders`, quản lý vào `/manager`.
Quản lý có thể cập nhật sản phẩm, xử lý đơn và gửi email marketing; nhân viên chỉ xử lý đơn.
Để thử POST trong Swagger: gọi `GET /api/v1/auth/csrf`, dùng `csrf_token` làm
`X-CSRF-Token`; lấy token mới sau login/logout. Chi tiết: [contract auth](guideline/API-DESIGN.md#auth).

## Thanh toán sandbox (VNPAY + PayPal)

`PAYMENT_MODE=mock` (mặc định) giữ luồng mô phỏng cho test. Đặt `PAYMENT_MODE=sandbox`
trong `.env` cùng credential VNPAY/PayPal để thanh toán thật trên môi trường sandbox;
app dừng ngay nếu thiếu credential. Return/IPN/webhook được suy ra từ `SITE_URL`, nên
khi demo cần URL public HTTPS. Checkout hiển thị tỷ giá quy đổi PayPal/VNPAY kèm VAT
(`VAT_PERCENT`, mặc định 10%) và giỏ hàng chỉ được xóa sau khi thanh toán xác nhận.
Thiết kế, credential checklist và trạng thái còn lại:
[guideline/PAYMENT-SANDBOX.md](guideline/PAYMENT-SANDBOX.md).

Sau khi `docker compose up -d --build`, chạy smoke test E2E trên SQL Server thật:

```sh
python3 scripts/smoke_payments.py
```

## Kiểm tra code

Phần này dành cho người chạy Python local, sau khi cài `requirements-dev.txt`:

```sh
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
```

Trên Windows thay `python` bằng `.\.venv\Scripts\python.exe`; trên macOS/Linux dùng
Python của `.venv`. Test tự dùng DB SQLite tạm. Chi tiết Docker/SQL Server đã kiểm chứng
và phần còn chờ nhóm nằm ở [checklist P1](guideline/P1-HANDOFF.md#verification).

## Bật các tích hợp tùy chọn

- **Thanh toán mô phỏng:** chọn PayPal hoặc VNPAY khi đặt hàng. Trang `/payments/{code}` cho chủ đơn mô phỏng thành công hoặc thất bại; có thể thử lại trên cùng đơn. Không kết nối dịch vụ bên ngoài, không cần API key, không thu tiền thật. Đơn chỉ được chuyển sang xác nhận/giao hàng sau khi thanh toán thành công. Hủy đơn đã trả tiền sẽ ghi nhận hoàn tiền mô phỏng.
- **Email marketing & Mailpit:** hệ thống tự động gửi email chào mừng (kèm mã `WELCOME10`) khi khách đăng ký ở chân trang; admin quản lý danh sách người nhận, xem trước HTML và gửi chiến dịch qua background tasks tại `/admin/newsletter`. Khi chạy Docker, toàn bộ email được gom vào hộp thư ảo Mailpit tại [http://localhost:8025](http://localhost:8025) (cổng SMTP `1025`). Để gửi email thật ra ngoài Internet, cấu hình thông tin SMTP (như Gmail hoặc Brevo) và `MAIL_FROM` trong `.env`. Email gửi đi luôn kèm liên kết hủy đăng ký bảo mật HMAC.
- **Sản phẩm và ảnh chia sẻ:** admin quản lý tại `/admin/products`; nhập URL ảnh HTTPS
  hoặc đường dẫn dưới `/static/img/`. Trang sản phẩm dùng tên, mô tả và ảnh này cho Open Graph.
- **Chat:** đặt `FACEBOOK_PAGE_URL` và `ZALO_PAGE_URL` cho các nút liên hệ. Để nhúng
  live chat Subiz, dán nguyên embed snippet do tài khoản Subiz cấp vào `SUBIZ_EMBED_CODE`.
  Để nhúng live chat Tawk.to, cấu hình `PROPERTY_ID` và `WIDGET_ID` (lấy từ Dashboard Tawk.to > Administration > Chat Widget) vào `.env`.
- **SEO/chia sẻ:** đặt `SITE_URL` thành địa chỉ HTTPS công khai của website trước khi
  phát hành để canonical, Open Graph, sitemap và URL callback dùng đúng domain.

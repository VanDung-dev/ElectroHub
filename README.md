# ElectroHub

Đồ án web bán hàng dùng Python 3.13, FastAPI, HTML/CSS/JS và SQL Server 2022.
Hiện có nền tảng/auth; catalog, giỏ hàng và giao diện đang được bổ sung.
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

DB và migration được khởi tạo tự động. Các lần sau dùng lại lệnh trên; thay đổi code cần build lại.
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

Chạy lại hai lệnh này sau khi pull code để cập nhật DB. Dừng app bằng `Ctrl+C`.
App mặc định dùng cổng 8000; muốn đổi cổng local, thêm `--port 8001` vào lệnh uvicorn
(`APP_PORT` chỉ dùng cho Compose).

## Mở ứng dụng và tạo admin

- [Trang web](http://localhost:8000) — template còn rỗng hiện trả thông báo HTML 503.
- [Swagger / thử API](http://localhost:8000/docs).
- [Kiểm tra kết nối DB](http://localhost:8000/api/v1/health).

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

Chạy lại lệnh không đổi mật khẩu admin đã có. Đăng ký qua API tạo tài khoản customer.
Để thử POST trong Swagger: gọi `GET /api/v1/auth/csrf`, dùng `csrf_token` làm
`X-CSRF-Token`; lấy token mới sau login/logout. Chi tiết: [contract auth](guideline/API-DESIGN.md#auth).

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

# ElectroHub — Hướng Dẫn Phát Triển (Developer Guide)

[← Về README chính](README.md) · [Kịch bản Demo](DEMO.md) · [Tiến độ & Guideline](guideline/README.md)

Tài liệu kỹ thuật chi tiết dành cho lập trình viên phát triển, cấu hình môi trường, quản trị Database và kiểm thử mã nguồn dự án ElectroHub.

---

## 🛠️ 1. Thiết lập Môi trường Phát triển

### Lựa chọn A: Docker Compose (Khuyến nghị cho tất cả OS)
Toàn bộ môi trường gồm Python 3.13, ODBC Driver 18, SQL Server 2022 (2 cụm), Mailpit và LocalTunnel đều được cấu hình sẵn trong [`compose.yaml`](compose.yaml).

1. Sao chép cấu hình:
   ```bash
   cp .env.example .env
   ```
2. Sinh mã `SECRET_KEY`:
   ```bash
   docker run --rm python:3.13.9-slim-bookworm python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
   Dán giá trị vào `SECRET_KEY=` trong `.env`.
   Mật khẩu SA mặc định: `MSSQL_SA_PASSWORD=ElectroHub@123`.
3. Khởi động toàn bộ dịch vụ:
   ```bash
   docker compose up -d --build
   ```
4. Nạp dữ liệu sản phẩm mẫu (tùy chọn):
   ```bash
   docker compose exec app python -m app.seeds.seed
   ```

### Lựa chọn B: Chạy trực tiếp trên Windows (Python native)
Dành cho máy Windows đã cài sẵn SQL Server 2022 Developer và SSMS:
1. Cài đặt Python 3.13 và [ODBC Driver 18 for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server).
2. Bật TCP/IP trong SQL Server Configuration Manager (Port: `1433`).
3. Chạy file [`docker/init.sql`](docker/init.sql) trong SSMS để tạo database `ElectroHub`.
4. Mở PowerShell tại repo:
   ```powershell
   py -3.13 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
   .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
   Dán key vào `SECRET_KEY=` trong `.env`.
5. Chạy migration và khởi động server:
   ```powershell
   .\.venv\Scripts\python.exe -m alembic upgrade head
   .\.venv\Scripts\python.exe -m app.seeds.accounts
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
   ```

---

## 🗄️ 2. Kiến trúc Hai Cụm Database (Dual Database)

Hệ thống Docker khởi chạy song song **2 cụm Database độc lập** để dev thoải mái thực hành môn học mà không ảnh hưởng tới dữ liệu Web App:

| Thông số | 1. Database Chính (Web App) | 2. Database Test (Dev / Môn học) |
| :--- | :--- | :--- |
| **Service Compose** | `sqlserver` | `sqlserver-test` |
| **Container Name** | `electrohub-sqlserver-1` | `electrohub-sqlserver-test` |
| **Cổng trên macOS / Linux** | `localhost:1433` | `localhost:1434` |
| **Cổng trên Windows Parallels** | `10.211.55.2,1433` | `<IP của máy tính>,1434` |
| **User Name / Password** | `sa` / `ElectroHub@123` | `sa` / `ElectroHub@123` |
| **Database** | `ElectroHub` | `ElectroHub` |
| **Volume dữ liệu** | `sqlserver_data` | `sqlserver_test_data` |
| **Cơ chế nạp dữ liệu** | Alembic migrations + demo accounts | Tự động chạy toàn bộ 8 file SQL qua `init-test.sh` |
| **Nội dung** | Bảng nghiệp vụ phục vụ Web App | 13 bảng & view, 4 Triggers, 11 SP/Functions |

---

## 🔌 3. Hướng dẫn kết nối Database từ các công cụ

### Kết nối từ macOS (PyCharm / DataGrip / DBeaver / TablePlus):
- **Host / Port**: `localhost:1434` (DB Test môn học) hoặc `localhost:1433` (DB Web App).
- **User / Password**: `sa` / `ElectroHub@123`.
- **Database**: `ElectroHub`.
- **Driver**: Microsoft SQL Server (JDBC).
- **SSL / Certificate**: Tích chọn `Trust Server Certificate = True`.

### Kết nối từ SSMS trên Windows (chạy qua Parallels):
- **Server Name**: `<IP của máy tính>,1434` (DB Test) hoặc `<IP của máy tính>,1433` (DB Web App).
  *(Lưu ý: Bắt buộc dùng **dấu phẩy `,`**, không dùng dấu hai chấm `:`).*
- **Authentication**: `SQL Server Authentication`.
- **User Name / Password**: `sa` / `ElectroHub@123`.
- **Database**: `ElectroHub`.
- **Trust Server Certificate**: **BẮT BUỘC TÍCH CHỌN ☑** (nếu bỏ trống SSMS sẽ từ chối kết nối vì chứng chỉ tự ký).

---

## 🔄 4. Quy trình Quản trị Migration với Alembic

Alembic chỉ áp dụng cho Database Web App (`sqlserver` cổng 1433):

```bash
# Tạo migration tự động khi thay đổi model SQLAlchemy
alembic revision --autogenerate -m "ten_thay_doi"

# Áp dụng migration lên database
alembic upgrade head

# Rollback 1 bước để kiểm tra tính 2 chiều
alembic downgrade -1
alembic upgrade head
```

---

## 📚 5. Bộ tài nguyên T-SQL Môn học ([`sql/`](sql/))

Toàn bộ kịch bản phục vụ môn Hệ Quản Trị CSDL SQL Server 2022:

- [`01_ddl_tables.sql`](sql/01_ddl_tables.sql): Cấu trúc 10 bảng nghiệp vụ, PK, FK, Constraints, Filtered Index.
- [`02_rules_defaults.sql`](sql/02_rules_defaults.sql): Các Rule (`rule_GiaKhongAm`, `rule_SoLuongHopLe`...) và Default độc lập gán qua `sp_bindrule`, `sp_bindefault`.
- [`03_triggers.sql`](sql/03_triggers.sql): Triggers tự động trừ tồn kho, hoàn kho khi hủy đơn, chống sửa xóa đơn đã đóng.
- [`04_stored_procedures.sql`](sql/04_stored_procedures.sql): SPs tạo đơn hàng nguyên tử (Atomic Transaction), hủy đơn, báo cáo doanh thu với `TRY...CATCH`.
- [`05_cursors.sql`](sql/05_cursors.sql): Cursors quét đơn hàng quá hạn, phân hạng VIP tặng voucher, kiểm tra duyệt hoàn tiền.
- [`06_views_and_functions.sql`](sql/06_views_and_functions.sql): Scalar UDF, Table-Valued UDF và 3 Views báo cáo tổng hợp.
- [`07_transactions_concurrency.sql`](sql/07_transactions_concurrency.sql): Demo Savepoint, lock hints (`UPDLOCK`, `ROWLOCK`) và Isolation Levels.
- [`08_seed_data.sql`](sql/08_seed_data.sql): Dữ liệu mẫu linh kiện điện tử, đơn hàng và voucher.

### Chạy kiểm thử tự động toàn bộ 100% kịch bản T-SQL:
```bash
docker compose exec -T sqlserver-test /opt/mssql-tools18/bin/sqlcmd \
    -S localhost -U sa -P "ElectroHub@123" -C -i /sql/test_all.sql
```

---

## 🧪 6. Kiểm tra Chất lượng Mã nguồn (Linting & Testing)

Dự án duy trì bộ kiểm thử tự động với **106/106 tests passed**:

```bash
# Kiểm tra convention và import
python -m ruff check .

# Kiểm tra định dạng code
python -m ruff format --check .

# Tự động format toàn bộ code
python -m ruff format .

# Chạy toàn bộ 106 unit & integration tests
python -m pytest -v
```

---

## ⚙️ 7. Các lệnh CLI Tiện ích

```bash
# Tạo tài khoản quản trị mới
docker compose exec app python -m app.create_admin --email admin@example.com --name "Quản trị viên"

# Tạo tài khoản nhân viên
docker compose exec app python -m app.create_admin --role staff --email staff@example.com --name "Nhân viên"

# Nạp lại tài khoản demo
docker compose exec app python -m app.seeds.accounts

# Chạy smoke test kiểm tra cổng thanh toán
python3 scripts/smoke_payments.py
```

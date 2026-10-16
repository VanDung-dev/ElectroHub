# ElectroHub

Môi trường phát triển ban đầu: Python 3.13.9/FastAPI và SQL Server 2022 Developer.
Database `ElectroHub` được tạo tự động; chạy lại bước khởi tạo không xóa database có sẵn.
Ứng dụng hiện phục vụ các endpoint mẫu, chưa kết nối SQL Server.

## Chạy bằng Docker Compose

Cần Docker Engine và Docker Compose v2 trở lên. SQL Server cần ít nhất 2 GB RAM;
để thêm tài nguyên cho Python và Docker.

1. Sao chép `.env.example` thành `.env`.
2. Điền `MSSQL_SA_PASSWORD`: ít nhất 8 ký tự, gồm ít nhất 3 nhóm chữ hoa,
   chữ thường, chữ số, ký tự đặc biệt. Không commit `.env`.
3. Chạy tại thư mục repository:

```sh
docker compose up --build --wait --wait-timeout 240
```

Compose chờ SQL Server sẵn sàng, tạo database rồi khởi động FastAPI.

- FastAPI: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- SQL Server từ máy cá nhân: `localhost,1433`, database `ElectroHub`,
  tài khoản `sa`, mật khẩu trong `.env`.
- SQL Server từ container cùng mạng Compose: `sqlserver:1433`.

Có thể đổi `SQLSERVER_PORT` và `APP_PORT` trong `.env` nếu cổng đang được sử dụng.
Các cổng chỉ mở trên `127.0.0.1` của máy chạy Docker.

Kiểm tra database:

```sh
docker compose exec sqlserver sh -c 'SQLCMDPASSWORD="$MSSQL_SA_PASSWORD" /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -C -b -d ElectroHub -Q "SELECT DB_NAME()"'
```

Dừng dịch vụ và giữ dữ liệu:

```sh
docker compose down
```

Dữ liệu SQL Server nằm trong named volume `electrohub_sqlserver_data`.
`docker compose down -v` sẽ xóa volume và toàn bộ dữ liệu database.
Sau khi volume đã được tạo, thay mật khẩu trong `.env` không tự đổi mật khẩu
`sa` trong database; cần đổi mật khẩu qua SQL Server rồi cập nhật `.env`.

## Python chạy trực tiếp, SQL Server chạy trong Docker

```sh
docker compose up --wait --wait-timeout 240 sqlserver
docker compose run --rm sqlserver-init
python -m venv .venv
```

Kích hoạt `.venv` theo hệ điều hành, sau đó:

```sh
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Nếu máy hoàn toàn không dùng Docker, cài SQL Server trên Windows/Linux tương thích
hoặc dùng SQL Server từ máy chủ khác; chạy `docker/init.sql` bằng công cụ SQL
để tạo database, rồi chạy Python theo hướng dẫn trên.
Không chia sẻ `.venv` giữa các máy. Thư viện/driver kết nối database sẽ được bổ sung
khi triển khai tầng dữ liệu.

## Giới hạn môi trường phát triển

SQL Server image chỉ được Microsoft hỗ trợ trên Linux x86-64.
Compose đặt `platform: linux/amd64` để Docker ARM có thể thử chạy bằng giả lập;
đây không phải nền tảng được Microsoft hỗ trợ. Nếu không chạy được, dùng SQL Server
trên máy Windows/Linux x86-64 bên ngoài.

Cấu hình này dùng SQL Server Developer cho phát triển/kiểm thử và `sa` để khởi tạo.
Chưa phải cấu hình production. `sqlcmd -C` tin cậy chứng chỉ của SQL Server local;
triển khai thật cần cấu hình chứng chỉ và tài khoản ứng dụng riêng.

Tham khảo:
- https://learn.microsoft.com/en-us/sql/linux/quickstart-install-connect-docker?view=sql-server-ver16
- https://docs.docker.com/compose/how-tos/startup-order/

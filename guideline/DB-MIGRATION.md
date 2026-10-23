# DB & Migration — SQL Server 2022 + Alembic

[← Trang bắt đầu / chọn thành viên](README.md) · [Tra cứu theo công việc](README.md#lookup)

[Dũng chủ trì ERD/migration](members/P1-DUNG.md#tasks). [Giàu](members/P2-GIAU.md#coordination) và [Hưng](members/P3-HUNG.md#coordination) đề xuất schema theo domain; thay đổi DB cần Dũng duyệt.

<a id="roles"></a>

## 1. Vai trò

* `docker/init.sql`: chỉ tạo DB `ElectroHub` nếu chưa có. Không chứa bảng business.
* Mọi bảng/column/index đi qua Alembic migration versioned. Không `ALTER` tay trên SSMS rồi quên ghi lại.
* Dũng P1 sở hữu ERD + migration. Giàu P2 / Hưng P3 đề xuất schema qua issue, Dũng P1 duyệt rồi mới code migration.

Đã có `Base`/`get_db` tại `app/core/database.py` và migration `0001_users` chỉ tạo bảng users.
Các bảng business trong ERD dưới đây vẫn là bản tối thiểu cần chủ domain đề xuất/duyệt,
chưa được migration tạo. Import model mới vào `app/models/__init__.py` để Alembic thấy metadata.
Users lưu Unicode, email unique, constraint role admin/customer; `created_at` UTC không timezone
(SQL Server dùng `DATETIME2`). CLI tạo admin xem [README](../README.md).

<a id="erd"></a>

## 2. ERD tối thiểu (Dũng P1 chốt W1, Giàu P2 bổ sung product, Hưng P3 bổ sung order)

```text
users(id, email UQ, password_hash, name, role, created_at)
categories(id, parent_id FK, name, slug UQ)
brands(id, name, slug UQ)
products(id, slug UQ, sku UQ, name, category_id FK, brand_id FK, price INT, sale_price INT NULL, stock INT, specs JSON, created_at)
product_images(id, product_id FK, url, sort)
cart_items(id, user_id FK, product_id FK, qty, UQ(user_id, product_id))
orders(id, code UQ, user_id FK, status, subtotal, discount, shipping_fee, total, address JSON, created_at)
order_items(id, order_id FK, product_id FK, price, qty)
payments(id, order_id FK UQ, method[COD,VNPAY_MOCK], status, payload JSON)
vouchers(id, code UQ, percent, max_discount, qty_left, expired_at)
posts(id, slug UQ, title, tag[ARDUINO,ESP32,RASPBERRY,MICROBIT,REVIEW], content, created_at)
```

Quy ước: PK `id INT IDENTITY`, tiền `INT`, thời gian `DATETIME2`, `slug/code` unique, FK có index.

<a id="migrations"></a>

## 3. Workflow migration

```sh
alembic revision --autogenerate -m "add products stock"
alembic upgrade head
alembic downgrade -1   # bắt buộc chạy thử trước khi PR
```

* 1 migration 1 mục đích, có cả `upgrade()` + `downgrade()`. Không sửa migration đã merge vào `develop`.
* Seed tách riêng `app/seeds/*.py` (brands, categories, 50-100 products kiểu hshop), chạy lại được, không nhét seed vào migration.

<a id="data-safety"></a>

## 4. An toàn dữ liệu

* Checkout/trừ kho/voucher gói trong 1 transaction, dùng `WITH (UPDLOCK)` hoặc check `stock >= qty` trong UPDATE. Không đọc stock rồi trừ ở 2 query rời.
* Mật khẩu `bcrypt`, không lưu plain. Connection string chỉ từ `.env`, không commit.
* `docker compose down` giữ data. `down -v` xóa hết — chỉ Dũng P1 được chạy khi cả team đồng ý.

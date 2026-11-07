# Tài Liệu Cơ Sở Dữ Liệu T-SQL — ElectroHub (SQL Server 2022)

Hệ thống cơ sở dữ liệu T-SQL này được thiết kế và xây dựng đầy đủ theo chuẩn chương trình môn học **Hệ Quản Trị Cơ Sở Dữ Liệu (DBMS)**, bám sát các tài liệu bài giảng:
- `CaiDat Rules_SP_Trigger.pdf` (Rules, Defaults, Triggers, Stored Procedures)
- `DBMS_03_ProgrammingCursors.pdf` (Lập trình với Con trỏ - Cursors)
- `DBMS_05_ContTransactionProc.pdf` (Transaction, Concurrency Control, Lock Hints, Savepoints)

---

## 📁 Cấu Trúc Thư Mục SQL

```
sql/
├── 01_ddl_tables.sql                # Tạo Database ElectroHub và 10 bảng nghiệp vụ
├── 02_rules_defaults.sql           # Cài đặt Rules (sp_bindrule) & Defaults (sp_bindefault)
├── 03_triggers.sql                 # Cài đặt các Triggers nghiệp vụ và bảo toàn dữ liệu
├── 04_stored_procedures.sql       # Cài đặt Stored Procedures (Tạo đơn, Hủy đơn, Báo cáo)
├── 05_cursors.sql                  # Cài đặt các Stored Procedures dùng CURSOR duyệt dòng
├── 06_views_and_functions.sql      # Cài đặt Views và User-Defined Functions (Scalar & Table)
├── 07_transactions_concurrency.sql # Kịch bản demo Transaction, Concurrency Control & Lock Hints
├── 08_seed_data.sql                # Bộ dữ liệu mẫu linh kiện điện tử để test
├── master_setup.sql                # File tổng quan thứ tự thực thi
└── README.md                       # Hướng dẫn chi tiết và kịch bản test
```

---

## 🚀 Hướng Dẫn Thực Thi

### Cách 1: Chạy trên SQL Server Management Studio (SSMS) / Azure Data Studio
Mở kết nối tới SQL Server và mở từng file chạy theo thứ tự:
`01` ➔ `02` ➔ `03` ➔ `04` ➔ `05` ➔ `06` ➔ `07` ➔ `08`.

### Cách 2: Chạy trực tiếp qua Docker Container `sqlcmd` trong repo
Nếu bạn đang dùng macOS/Linux và chạy SQL Server qua Docker Compose (`compose.yaml`):

```bash
# 1. Chạy container SQL Server
docker compose up -d sqlserver

# 2. Thực thi lần lượt các file SQL vào container
for file in sql/*.sql; do
    echo "Đang chạy $file..."
    docker compose exec -T sqlserver /opt/mssql-tools18/bin/sqlcmd \
        -S localhost -U sa -P 'YourStrongPassword!' -C -b -i "/work/$file"
done
```

---

## 🧪 Kịch Bản Kiểm Thử & Nghiệm Thu Môn Học

### 1. Kiểm thử Rules & Defaults (`02_rules_defaults.sql`)

```sql
USE [ElectroHub];
GO

-- Test Rule 1: Thử chèn sản phẩm với giá âm (Sẽ bị chặn bởi rule_GiaKhongAm)
INSERT INTO dbo.products (slug, sku, name, price, stock)
VALUES ('test-sp-am', 'EH-AM', N'Sản phẩm giá âm', -50000, 10);
-- Kết quả mong đợi: Lỗi "A column insert or update conflicts with a rule imposed by a previous CREATE RULE statement."

-- Test Rule 2: Thử chèn số lượng giỏ hàng vượt quá 99 (Bị chặn bởi rule_SoLuongHopLe)
INSERT INTO dbo.cart_items (user_id, product_id, qty)
VALUES (3, 1, 150);
-- Kết quả mong đợi: Lỗi vi phạm Rule.
```

---

### 2. Kiểm thử Triggers (`03_triggers.sql`)

#### Test Trigger 1: `trg_KiemTraVaTruTonKho` (Kiểm tra và trừ tồn kho)
```sql
USE [ElectroHub];
GO

-- Xem tồn kho ban đầu của sản phẩm ID = 1 (ESP32)
SELECT id, sku, name, stock FROM dbo.products WHERE id = 1;

-- Thử đặt mua số lượng vượt quá tồn kho (Ví dụ kho còn 50, đặt 999 cái)
-- Trigger sẽ RAISERROR và ROLLBACK
INSERT INTO dbo.order_items (order_id, product_id, price, qty)
VALUES (3, 1, 75000, 999);
-- Kết quả mong đợi: Bị Trigger chặn và in lỗi: "Lỗi tồn kho: Sản phẩm ... không đủ đáp ứng..."

-- Đặt mua số lượng hợp lệ (Ví dụ mua 5 cái)
INSERT INTO dbo.order_items (order_id, product_id, price, qty)
VALUES (3, 1, 75000, 5);

-- Kiểm tra lại: Tồn kho đã tự động bị trừ đi 5 cái
SELECT id, sku, name, stock FROM dbo.products WHERE id = 1;
```

#### Test Trigger 2: `trg_HoanKhoKhiHuyDonHang` (Tự động hoàn kho khi hủy đơn)
```sql
-- Xem tồn kho sản phẩm ID = 1 trước khi hủy đơn 3
SELECT id, stock FROM dbo.products WHERE id = 1;

-- Cập nhật đơn hàng 3 sang 'cancelled'
UPDATE dbo.orders SET status = 'cancelled' WHERE id = 3;

-- Kiểm tra lại: Tồn kho của sản phẩm 1 đã tự động được Trigger hoàn trả lại!
SELECT id, stock FROM dbo.products WHERE id = 1;
```

---

### 3. Kiểm thử Stored Procedures (`04_stored_procedures.sql`)

#### Test Procedure 1: Thêm sản phẩm mới kèm kiểm tra
```sql
DECLARE @NewId INT;
EXEC dbo.sp_ThemSanPham
    @Slug = 'cam-bien-khi-mq2',
    @Sku = 'EH-MQ2',
    @Name = N'Cảm biến rò rỉ khí gas và khói MQ-2',
    @Price = 45000,
    @SalePrice = 39000,
    @Stock = 60,
    @Description = N'Cảm biến phát hiện LPG, i-butan, propan, mêtan, cồn, hydro, khói.',
    @NewProductId = @NewId OUTPUT;

SELECT * FROM dbo.products WHERE id = @NewId;
```

#### Test Procedure 2: Tạo đơn hàng từ giỏ hàng (Transaction)
```sql
-- 1. Thêm hàng vào giỏ của User 3 (Nguyễn Văn Dũng)
INSERT INTO dbo.cart_items (user_id, product_id, qty) VALUES (3, 3, 2);

-- 2. Gọi thủ tục tạo đơn hàng
DECLARE @OrderIdOut INT, @OrderCodeOut VARCHAR(12);
EXEC dbo.sp_TaoDonHangTuGioHang
    @UserId = 3,
    @Name = N'Nguyễn Văn Dũng',
    @Phone = '0987654321',
    @AddressText = N'Đại học Bách Khoa TP.HCM',
    @PaymentMethod = 'COD',
    @VoucherCode = 'WELCOME10',
    @OrderId = @OrderIdOut OUTPUT,
    @OrderCode = @OrderCodeOut OUTPUT;

-- 3. Kiểm tra kết quả
SELECT * FROM dbo.orders WHERE id = @OrderIdOut;
SELECT * FROM dbo.order_items WHERE order_id = @OrderIdOut;
SELECT * FROM dbo.payments WHERE order_id = @OrderIdOut;
-- Giỏ hàng của User 3 đã được tự động dọn sạch
SELECT * FROM dbo.cart_items WHERE user_id = 3;
```

#### Test Procedure 3: Báo cáo thống kê doanh thu
```sql
EXEC dbo.sp_BaoCaoDoanhThu @TuNgay = '2024-01-01', @DenNgay = '2026-12-31';
```

---

### 4. Kiểm thử Cursors (`05_cursors.sql`)

#### Test Cursor 1: Quét hủy đơn hàng Pending quá hạn
```sql
-- Quét các đơn pending quá 1 giờ
EXEC dbo.sp_Cursor_XuLyDonHangPendingQuaHan @SoGioCho = 1;
```

#### Test Cursor 2: Phân hạng khách hàng VIP và tặng Voucher tri ân
```sql
EXEC dbo.sp_Cursor_PhanHangVaTangVoucherKhachHang;

-- Kiểm tra các mã voucher VIP mới được tạo tự động cho khách:
SELECT * FROM dbo.vouchers WHERE code LIKE 'VIP-%' OR code LIKE 'LOYAL-%';
```

#### Test Cursor 3: Quét yêu cầu hoàn tiền sau 72 giờ
```sql
EXEC dbo.sp_Cursor_QuetKiemTraYeuCauHoanTien;
```

---

### 5. Kiểm thử Views & User-Defined Functions (`06_views_and_functions.sql`)

```sql
-- 1. Thử hàm vô hướng tính tổng tiền
SELECT dbo.fn_TinhTongTienDonHang(500000, 50000, 10, 30000) AS TongTienSauThueVaPhi;

-- 2. Thử hàm kiểm tra mã voucher
SELECT dbo.fn_KiemTraVoucherHopLe('WELCOME10') AS VoucherConHan,
       dbo.fn_KiemTraVoucherHopLe('EXPIRED') AS VoucherHetHan;

-- 3. Thử hàm bảng xem lịch sử mua hàng của User ID = 3
SELECT * FROM dbo.fn_LichSuDonHangUser(3);

-- 4. Truy vấn Views báo cáo
SELECT * FROM dbo.v_ChiTietDonHangTongHop;
SELECT * FROM dbo.v_ThongKeSanPhamVaDoanhSo;
SELECT * FROM dbo.v_BaoCaoDoanhThuTheoThang;
```

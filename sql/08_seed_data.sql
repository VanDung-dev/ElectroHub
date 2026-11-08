-- ============================================================================
-- ELECTROHUB - HỆ QUẢN TRỊ CƠ SỞ DỮ LIỆU (SQL SERVER 2022)
-- File: 08_seed_data.sql
-- Mục đích: Nạp dữ liệu mẫu thực tế để kiểm thử SP, Trigger, Cursor, Views
-- ============================================================================

USE [ElectroHub];
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

PRINT N'=== BẮT ĐẦU NẠP DỮ LIỆU MẪU (SEED DATA) ===';
GO

-- 1. NẠP USERS
SET IDENTITY_INSERT dbo.users ON;
IF NOT EXISTS (SELECT 1 FROM dbo.users WHERE id = 1)
    INSERT INTO dbo.users (id, email, password_hash, name, role, created_at)
    VALUES (1, 'admin@electrohub.vn', '$2b$12$e80yq9l.v.uW7/JvEwTTe.aC4oH.lqN7U6C8B5G5A5X7y5z3m3Z1e', N'Quản trị viên ElectroHub', 'admin', SYSUTCDATETIME());

IF NOT EXISTS (SELECT 1 FROM dbo.users WHERE id = 2)
    INSERT INTO dbo.users (id, email, password_hash, name, role, created_at)
    VALUES (2, 'staff@electrohub.vn', '$2b$12$e80yq9l.v.uW7/JvEwTTe.aC4oH.lqN7U6C8B5G5A5X7y5z3m3Z1e', N'Nhân viên bán hàng', 'staff', SYSUTCDATETIME());

IF NOT EXISTS (SELECT 1 FROM dbo.users WHERE id = 3)
    INSERT INTO dbo.users (id, email, password_hash, name, role, created_at)
    VALUES (3, 'dung.nguyen@example.com', '$2b$12$e80yq9l.v.uW7/JvEwTTe.aC4oH.lqN7U6C8B5G5A5X7y5z3m3Z1e', N'Nguyễn Văn Dũng', 'customer', SYSUTCDATETIME());

IF NOT EXISTS (SELECT 1 FROM dbo.users WHERE id = 4)
    INSERT INTO dbo.users (id, email, password_hash, name, role, created_at)
    VALUES (4, 'giau.nguyen@example.com', '$2b$12$e80yq9l.v.uW7/JvEwTTe.aC4oH.lqN7U6C8B5G5A5X7y5z3m3Z1e', N'Nguyễn Hữu Giàu', 'customer', SYSUTCDATETIME());

IF NOT EXISTS (SELECT 1 FROM dbo.users WHERE id = 5)
    INSERT INTO dbo.users (id, email, password_hash, name, role, created_at)
    VALUES (5, 'hung.le@example.com', '$2b$12$e80yq9l.v.uW7/JvEwTTe.aC4oH.lqN7U6C8B5G5A5X7y5z3m3Z1e', N'Lê Nhật Hưng', 'customer', SYSUTCDATETIME());
SET IDENTITY_INSERT dbo.users OFF;
PRINT N'Đã nạp bảng users.';
GO

-- 2. NẠP PRODUCTS
SET IDENTITY_INSERT dbo.products ON;
INSERT INTO dbo.products (id, slug, sku, name, description, image_url, price, sale_price, stock)
SELECT source.id, source.slug, source.sku, source.name, source.description, source.image_url, source.price, source.sale_price, source.stock
FROM (VALUES
    (1, 'esp32-wroom-32d', 'EH-ESP32', N'Module Wi-Fi BLE ESP32-WROOM-32D', N'Vi điều khiển lõi kép 240MHz, tích hợp Wi-Fi 802.11 b/g/n và Bluetooth 4.2 BLE.', '/static/img/products/esp32-devkit.png', 85000, 75000, 50),
    (2, 'arduino-uno-r3', 'EH-UNO-R3', N'Bo mạch Arduino Uno R3 ATmega328P', N'Bo mạch vi điều khiển tiêu chuẩn học tập, tương thích hoàn toàn Arduino IDE.', '/static/img/products/arduino-uno.png', 120000, 110000, 35),
    (3, 'stm32-blue-pill', 'EH-STM32', N'Bo mạch STM32F103C8T6 Blue Pill', N'ARM Cortex-M3 72MHz, 64KB Flash, phù hợp các ứng dụng điều khiển thời gian thực.', '/static/img/product-placeholder.svg', 65000, NULL, 20),
    (4, 'cam-bien-dht22', 'EH-DHT22', N'Cảm biến nhiệt độ độ ẩm DHT22/AM2302', N'Cảm biến độ chính xác cao: nhiệt độ -40~80°C (±0.5°C), độ ẩm 0~100% RH (±2%).', '/static/img/products/dht22.png', 95000, 85000, 40),
    (5, 'cam-bien-hc-sr04', 'EH-SR04', N'Cảm biến khoảng cách siêu âm HC-SR04', N'Khoảng cách đo 2cm - 400cm, độ phân giải 3mm, ứng dụng xe tránh vật cản.', '/static/img/products/sr04.jpg', 25000, NULL, 100),
    (6, 'module-relay-5v-4-kenh', 'EH-RELAY-4CH', N'Module Relay 5V 4 kênh cách ly quang', N'Kích đóng ngắt tải AC 250V/10A hoặc DC 30V/10A, có opto cách ly an toàn.', '/static/img/products/relay.jpg', 55000, 49000, 15),
    (7, 'mach-ha-ap-buck-lm2596', 'EH-LM2596', N'Mạch giảm áp DC-DC LM2596 3A', N'Điện áp vào 4V-35V, điện áp ra điều chỉnh 1.23V-30V, dòng tải max 3A.', '/static/img/products/lm2596.jpg', 22000, NULL, 80),
    (8, 'raspberry-pi-4-model-b-4gb', 'EH-RPI4-4GB', N'Máy tính mini Raspberry Pi 4 Model B (4GB RAM)', N'Quad-core Cortex-A72 1.5GHz, 2 cổng micro-HDMI 4K, 2x USB 3.0, Gigabit Ethernet.', '/static/img/products/rpi4.jpg', 1850000, 1750000, 5)
) AS source (id, slug, sku, name, description, image_url, price, sale_price, stock)
WHERE NOT EXISTS (SELECT 1 FROM dbo.products WHERE id = source.id);
SET IDENTITY_INSERT dbo.products OFF;
PRINT N'Đã nạp bảng products.';
GO

-- 2.1. NẠP PRODUCT_IMAGES (Gallery nhiều ảnh cho ESP32 DevKit, Arduino Uno, DHT22)
IF NOT EXISTS (SELECT 1 FROM dbo.product_images WHERE product_id = 1)
BEGIN
    INSERT INTO dbo.product_images (product_id, url, alt, sort) VALUES
    (1, '/static/img/products/esp32-devkit.png', N'Mặt trước', 0),
    (1, '/static/img/products/esp32-devkit-1.png', N'Góc nghiêng', 1),
    (1, '/static/img/products/esp32-devkit-2.png', N'Khác / Chi tiết', 2);
END

IF NOT EXISTS (SELECT 1 FROM dbo.product_images WHERE product_id = 2)
BEGIN
    INSERT INTO dbo.product_images (product_id, url, alt, sort) VALUES
    (2, '/static/img/products/arduino-uno.png', N'Mặt trước', 0),
    (2, '/static/img/products/arduino-uno-1.png', N'Góc nghiêng', 1),
    (2, '/static/img/products/arduino-uno-2.png', N'Mặt sau', 2),
    (2, '/static/img/products/arduino-uno-3.png', N'Khác / Sơ đồ chi tiết', 3);
END

IF NOT EXISTS (SELECT 1 FROM dbo.product_images WHERE product_id = 4)
BEGIN
    INSERT INTO dbo.product_images (product_id, url, alt, sort) VALUES
    (4, '/static/img/products/dht22.png', N'Mặt trước', 0),
    (4, '/static/img/products/dht22-1.png', N'Mặt sau', 1),
    (4, '/static/img/products/dht22-2.png', N'Chân cắm', 2),
    (4, '/static/img/products/dht22-3.png', N'Khác / Thông số', 3);
END
PRINT N'Đã nạp bảng product_images.';
GO

-- 3. NẠP VOUCHERS
INSERT INTO dbo.vouchers (code, [percent], max_discount, qty_left, expired_at)
SELECT source.code, source.[percent], source.max_discount, source.qty_left, source.expired_at
FROM (VALUES
    ('WELCOME10', 10, 50000, 100, DATEADD(YEAR, 1, SYSUTCDATETIME())),
    ('TRIAN2026', 15, 100000, 50, DATEADD(MONTH, 6, SYSUTCDATETIME())),
    ('FLASH30', 30, 150000, 20, DATEADD(MONTH, 1, SYSUTCDATETIME())),
    ('EXPIRED', 50, 200000, 0, '2023-01-01')
) AS source (code, [percent], max_discount, qty_left, expired_at)
WHERE NOT EXISTS (SELECT 1 FROM dbo.vouchers WHERE code = source.code);
PRINT N'Đã nạp bảng vouchers.';
GO

-- 4. NẠP ĐƠN HÀNG MẪU VÀ CHI TIẾT
-- Tạm vô hiệu hóa Trigger trừ kho khi nạp seed lịch sử để không bị âm tồn kho
DISABLE TRIGGER dbo.trg_KiemTraVaTruTonKho ON dbo.order_items;
GO

SET IDENTITY_INSERT dbo.orders ON;
IF NOT EXISTS (SELECT 1 FROM dbo.orders WHERE id = 1)
    INSERT INTO dbo.orders (id, code, user_id, status, subtotal, discount, vat, shipping_fee, total, voucher_code, address, created_at)
    VALUES (1, 'EH-DEMO01', 3, 'done', 260000, 26000, 23400, 30000, 287400, 'WELCOME10', N'{"name":"Nguyễn Văn Dũng","phone":"0987654321","address":"Số 123 Đường Điện Biên Phủ, TP.HCM"}', DATEADD(DAY, -10, SYSUTCDATETIME()));

IF NOT EXISTS (SELECT 1 FROM dbo.orders WHERE id = 2)
    INSERT INTO dbo.orders (id, code, user_id, status, subtotal, discount, vat, shipping_fee, total, voucher_code, address, created_at)
    VALUES (2, 'EH-DEMO02', 4, 'shipping', 1750000, 100000, 165000, 30000, 1845000, 'TRIAN2026', N'{"name":"Nguyễn Hữu Giàu","phone":"0912345678","address":"Số 45 Lê Duẩn, Hà Nội"}', DATEADD(DAY, -2, SYSUTCDATETIME()));

IF NOT EXISTS (SELECT 1 FROM dbo.orders WHERE id = 3)
    INSERT INTO dbo.orders (id, code, user_id, status, subtotal, discount, vat, shipping_fee, total, voucher_code, address, created_at)
    VALUES (3, 'EH-DEMO03', 5, 'pending', 110000, 0, 11000, 30000, 151000, NULL, N'{"name":"Lê Nhật Hưng","phone":"0909090909","address":"Số 88 Trần Hưng Đạo, Cần Thơ"}', SYSUTCDATETIME());

IF NOT EXISTS (SELECT 1 FROM dbo.orders WHERE id = 4)
    INSERT INTO dbo.orders (id, code, user_id, status, subtotal, discount, vat, shipping_fee, total, voucher_code, address, created_at)
    VALUES (4, 'EH-DEMO04', 3, 'cancelled', 85000, 0, 8500, 30000, 123500, NULL, N'{"name":"Nguyễn Văn Dũng","phone":"0987654321","address":"TP.HCM"}', DATEADD(DAY, -5, SYSUTCDATETIME()));

SET IDENTITY_INSERT dbo.orders OFF;
GO

-- Nạp order_items
IF NOT EXISTS (SELECT 1 FROM dbo.order_items WHERE order_id = 1)
BEGIN
    INSERT INTO dbo.order_items (order_id, product_id, price, qty) VALUES
    (1, 1, 75000, 2), -- 2x ESP32 = 150k
    (1, 2, 110000, 1); -- 1x Arduino = 110k
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.order_items WHERE order_id = 2)
BEGIN
    INSERT INTO dbo.order_items (order_id, product_id, price, qty) VALUES
    (2, 8, 1750000, 1); -- 1x RPi 4 = 1750k
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.order_items WHERE order_id = 3)
BEGIN
    INSERT INTO dbo.order_items (order_id, product_id, price, qty) VALUES
    (3, 2, 110000, 1);
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.order_items WHERE order_id = 4)
BEGIN
    INSERT INTO dbo.order_items (order_id, product_id, price, qty) VALUES
    (4, 4, 85000, 1);
END
GO

-- Bật lại Trigger
ENABLE TRIGGER dbo.trg_KiemTraVaTruTonKho ON dbo.order_items;
PRINT N'Đã nạp bảng orders và order_items.';
GO

-- 5. NẠP PAYMENTS
SET IDENTITY_INSERT dbo.payments ON;
IF NOT EXISTS (SELECT 1 FROM dbo.payments WHERE order_id = 1)
    INSERT INTO dbo.payments (id, order_id, method, status, provider, currency, amount_minor, attempt, txn_ref, paid_at)
    VALUES (1, 1, 'VNPAY', 'paid', 'vnpay', 'VND', 28740000, 1, 'EHDEMO0101', DATEADD(DAY, -10, SYSUTCDATETIME()));

IF NOT EXISTS (SELECT 1 FROM dbo.payments WHERE order_id = 2)
    INSERT INTO dbo.payments (id, order_id, method, status, provider, currency, amount_minor, attempt, txn_ref, paid_at)
    VALUES (2, 2, 'PAYPAL', 'paid', 'paypal', 'USD', 7380, 1, 'EHDEMO0201', DATEADD(DAY, -2, SYSUTCDATETIME()));

IF NOT EXISTS (SELECT 1 FROM dbo.payments WHERE order_id = 3)
    INSERT INTO dbo.payments (id, order_id, method, status, provider, currency, amount_minor, attempt, txn_ref)
    VALUES (3, 3, 'COD', 'pending', 'mock', 'VND', 15100000, 1, 'EHDEMO0301');

IF NOT EXISTS (SELECT 1 FROM dbo.payments WHERE order_id = 4)
    INSERT INTO dbo.payments (id, order_id, method, status, provider, currency, amount_minor, attempt, txn_ref, paid_at)
    VALUES (4, 4, 'VNPAY', 'refund_pending', 'vnpay', 'VND', 12350000, 1, 'EHDEMO0401', DATEADD(DAY, -5, SYSUTCDATETIME()));
SET IDENTITY_INSERT dbo.payments OFF;
PRINT N'Đã nạp bảng payments.';
GO

-- 6. NẠP YÊU CẦU HOÀN TIỀN (REFUNDS)
SET IDENTITY_INSERT dbo.refunds ON;
IF NOT EXISTS (SELECT 1 FROM dbo.refunds WHERE order_id = 4)
    INSERT INTO dbo.refunds (id, order_id, payment_id, status, amount, currency, reason, requested_by, requested_at, due_at)
    VALUES (
        1, 4, 4, 'scheduled', 12350000, 'VND', 
        N'Khách hàng đổi ý mua linh kiện khác', 3, 
        DATEADD(HOUR, -80, SYSUTCDATETIME()), -- Đã qua 80 giờ (> 72h) -> Đủ điều kiện hoàn!
        DATEADD(HOUR, -8, SYSUTCDATETIME())
    );
SET IDENTITY_INSERT dbo.refunds OFF;
PRINT N'Đã nạp bảng refunds.';
GO

PRINT N'=== HOÀN TẤT NẠP DỮ LIỆU MẪU THÀNH CÔNG ===';
GO

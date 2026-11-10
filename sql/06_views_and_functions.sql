-- ============================================================================
-- ELECTROHUB - HỆ QUẢN TRỊ CƠ SỞ DỮ LIỆU (SQL SERVER 2022)
-- File: 06_views_and_functions.sql
-- Mục đích: Cài đặt Khung nhìn (Views) và Hàm do người dùng định nghĩa (UDF)
-- ============================================================================

USE [ElectroHub];
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

PRINT N'=== BẮT ĐẦU CÀI ĐẶT VIEWS VÀ FUNCTIONS ===';
GO

-- ----------------------------------------------------------------------------
-- PHẦN 1: USER-DEFINED FUNCTIONS (HÀM TỰ ĐỊNH NGHĨA)
-- ----------------------------------------------------------------------------

-- 1.1. SCALAR FUNCTION: Tính toán tổng tiền đơn hàng sau thuế và chiết khấu
CREATE OR ALTER FUNCTION dbo.fn_TinhTongTienDonHang
(
    @Subtotal INT,
    @Discount INT,
    @VatPercent INT = 10,
    @ShippingFee INT = 30000
)
RETURNS INT
AS
BEGIN
    DECLARE @NetGoods INT = @Subtotal - @Discount;
    IF @NetGoods < 0 SET @NetGoods = 0;

    DECLARE @VAT INT = (@NetGoods * @VatPercent + 50) / 100;
    DECLARE @Total INT = @NetGoods + @VAT + @ShippingFee;

    RETURN @Total;
END;
GO

-- 1.2. SCALAR FUNCTION: Kiểm tra tính hợp lệ của mã Voucher (Còn hạn & còn lượt dùng)
CREATE OR ALTER FUNCTION dbo.fn_KiemTraVoucherHopLe
(
    @VoucherCode VARCHAR(32)
)
RETURNS BIT
AS
BEGIN
    DECLARE @HopLe BIT = 0;

    IF EXISTS (
        SELECT 1 
        FROM dbo.vouchers
        WHERE code = @VoucherCode
          AND expired_at > SYSUTCDATETIME()
          AND qty_left > 0
    )
    BEGIN
        SET @HopLe = 1;
    END

    RETURN @HopLe;
END;
GO

-- 1.3. INLINE TABLE-VALUED FUNCTION: Lấy danh sách lịch sử đơn hàng của một người dùng
CREATE OR ALTER FUNCTION dbo.fn_LichSuDonHangUser
(
    @UserId INT
)
RETURNS TABLE
AS
RETURN
(
    SELECT 
        o.id AS OrderId,
        o.code AS OrderCode,
        o.status AS OrderStatus,
        o.total AS OrderTotal,
        o.created_at AS CreatedAt,
        COUNT(oi.id) AS ItemCount,
        COALESCE(p.method, N'Chưa chọn') AS PaymentMethod,
        COALESCE(p.status, N'none') AS PaymentStatus
    FROM dbo.orders o
    LEFT JOIN dbo.order_items oi ON o.id = oi.order_id
    LEFT JOIN dbo.payments p ON o.id = p.order_id
    WHERE o.user_id = @UserId
    GROUP BY o.id, o.code, o.status, o.total, o.created_at, p.method, p.status
);
GO


-- ----------------------------------------------------------------------------
-- PHẦN 2: VIEWS (KHUNG NHÌN)
-- ----------------------------------------------------------------------------

-- 2.1. VIEW: Chi tiết đơn hàng tổng hợp (Orders + Users + Payments + Refunds)
CREATE OR ALTER VIEW dbo.v_ChiTietDonHangTongHop
AS
SELECT 
    o.id AS OrderId,
    o.code AS OrderCode,
    o.created_at AS OrderDate,
    o.status AS OrderStatus,
    u.id AS CustomerId,
    u.name AS CustomerName,
    u.email AS CustomerEmail,
    o.subtotal AS Subtotal,
    o.discount AS Discount,
    o.vat AS VAT,
    o.shipping_fee AS ShippingFee,
    o.total AS TotalAmount,
    o.voucher_code AS VoucherCode,
    p.method AS PaymentMethod,
    p.status AS PaymentStatus,
    p.provider AS PaymentProvider,
    p.paid_at AS PaidAt,
    r.status AS RefundStatus,
    r.amount AS RefundAmountMinor
FROM dbo.orders o
JOIN dbo.users u ON o.user_id = u.id
LEFT JOIN dbo.payments p ON o.id = p.order_id
LEFT JOIN dbo.refunds r ON o.id = r.order_id;
GO

-- 2.2. VIEW: Thống kê hiệu suất và doanh số từng sản phẩm
CREATE OR ALTER VIEW dbo.v_ThongKeSanPhamVaDoanhSo
AS
SELECT 
    p.id AS ProductId,
    p.sku AS Sku,
    p.name AS ProductName,
    p.price AS Price,
    p.sale_price AS SalePrice,
    p.stock AS CurrentStock,
    CASE 
        WHEN p.stock = 0 THEN N'Hết hàng'
        WHEN p.stock < 10 THEN N'Sắp hết hàng'
        ELSE N'Còn hàng'
    END AS StockStatus,
    COALESCE(SUM(oi.qty), 0) AS TotalQuantitySold,
    COALESCE(SUM(oi.price * oi.qty), 0) AS TotalRevenueGenerated
FROM dbo.products p
LEFT JOIN dbo.order_items oi ON p.id = oi.product_id
LEFT JOIN dbo.orders o ON oi.order_id = o.id AND o.status = 'done'
GROUP BY p.id, p.sku, p.name, p.price, p.sale_price, p.stock;
GO

-- 2.3. VIEW: Báo cáo doanh thu theo tháng
CREATE OR ALTER VIEW dbo.v_BaoCaoDoanhThuTheoThang
AS
SELECT 
    YEAR(created_at) AS Nam,
    MONTH(created_at) AS Thang,
    COUNT(id) AS TongSoDon,
    SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS SoDonThanhCong,
    SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS SoDonHuy,
    SUM(CASE WHEN status = 'done' THEN total ELSE 0 END) AS DoanhThuThangVND
FROM dbo.orders
GROUP BY YEAR(created_at), MONTH(created_at);
GO

PRINT N'=== HOÀN TẤT CÀI ĐẶT VIEWS VÀ FUNCTIONS ===';
GO

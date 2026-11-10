-- ============================================================================
-- ELECTROHUB - HỆ QUẢN TRỊ CƠ SỞ DỮ LIỆU (SQL SERVER 2022)
-- File: 02_rules_defaults.sql
-- Mục đích: Cài đặt Rules (Quy tắc) và Defaults (Giá trị mặc định)
-- Theo tài liệu môn học: "CaiDat Rules_SP_Trigger.pdf"
-- ============================================================================

USE [ElectroHub];
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

PRINT N'=== BẮT ĐẦU CÀI ĐẶT RULES & DEFAULTS ===';
GO

-- ----------------------------------------------------------------------------
-- PHẦN 1: CÀI ĐẶT RULES (QUY TẮC TOÀN VẸN DỮ LIỆU)
-- ----------------------------------------------------------------------------

-- 1.1. Rule: Giá tiền không được âm (>= 0)
IF OBJECT_ID(N'dbo.rule_GiaKhongAm', N'R') IS NOT NULL
BEGIN
    EXEC sp_unbindrule 'dbo.products.price';
    EXEC sp_unbindrule 'dbo.products.sale_price';
    EXEC sp_unbindrule 'dbo.order_items.price';
    DROP RULE dbo.rule_GiaKhongAm;
END
GO
CREATE RULE dbo.rule_GiaKhongAm AS @gia >= 0;
GO
EXEC sp_bindrule 'dbo.rule_GiaKhongAm', 'dbo.products.price';
EXEC sp_bindrule 'dbo.rule_GiaKhongAm', 'dbo.products.sale_price';
EXEC sp_bindrule 'dbo.rule_GiaKhongAm', 'dbo.order_items.price';
PRINT N'Đã tạo và gán rule_GiaKhongAm.';
GO

-- 1.2. Rule: Số lượng mua mỗi món phải từ 1 đến 99
IF OBJECT_ID(N'dbo.rule_SoLuongHopLe', N'R') IS NOT NULL
BEGIN
    EXEC sp_unbindrule 'dbo.cart_items.qty';
    EXEC sp_unbindrule 'dbo.order_items.qty';
    DROP RULE dbo.rule_SoLuongHopLe;
END
GO
CREATE RULE dbo.rule_SoLuongHopLe AS @qty BETWEEN 1 AND 99;
GO
EXEC sp_bindrule 'dbo.rule_SoLuongHopLe', 'dbo.cart_items.qty';
EXEC sp_bindrule 'dbo.rule_SoLuongHopLe', 'dbo.order_items.qty';
PRINT N'Đã tạo và gán rule_SoLuongHopLe.';
GO

-- 1.3. Rule: Phần trăm giảm giá của Voucher từ 1% đến 100%
IF OBJECT_ID(N'dbo.rule_PhanTramVoucher', N'R') IS NOT NULL
BEGIN
    EXEC sp_unbindrule 'dbo.vouchers.percent';
    DROP RULE dbo.rule_PhanTramVoucher;
END
GO
CREATE RULE dbo.rule_PhanTramVoucher AS @percent BETWEEN 1 AND 100;
GO
EXEC sp_bindrule 'dbo.rule_PhanTramVoucher', 'dbo.vouchers.percent';
PRINT N'Đã tạo và gán rule_PhanTramVoucher.';
GO

-- 1.4. Rule: Trạng thái đơn hàng hợp lệ
IF OBJECT_ID(N'dbo.rule_TrangThaiDonHang', N'R') IS NOT NULL
BEGIN
    EXEC sp_unbindrule 'dbo.orders.status';
    DROP RULE dbo.rule_TrangThaiDonHang;
END
GO
CREATE RULE dbo.rule_TrangThaiDonHang AS @status IN ('pending', 'confirmed', 'shipping', 'done', 'cancelled');
GO
EXEC sp_bindrule 'dbo.rule_TrangThaiDonHang', 'dbo.orders.status';
PRINT N'Đã tạo và gán rule_TrangThaiDonHang.';
GO

-- 1.5. Rule: Phân quyền vai trò người dùng hợp lệ
IF OBJECT_ID(N'dbo.rule_VaiTroNguoiDung', N'R') IS NOT NULL
BEGIN
    EXEC sp_unbindrule 'dbo.users.role';
    DROP RULE dbo.rule_VaiTroNguoiDung;
END
GO
CREATE RULE dbo.rule_VaiTroNguoiDung AS @role IN ('admin', 'staff', 'customer');
GO
EXEC sp_bindrule 'dbo.rule_VaiTroNguoiDung', 'dbo.users.role';
PRINT N'Đã tạo và gán rule_VaiTroNguoiDung.';
GO


-- ----------------------------------------------------------------------------
-- PHẦN 2: CÀI ĐẶT DEFAULTS (GIÁ TRỊ MẶC ĐỊNH DÙNG CHUNG)
-- ----------------------------------------------------------------------------

-- 2.1. Default: Ngày giờ hiện tại (UTC)
IF OBJECT_ID(N'dbo.def_NgayHienTaiUTC', N'D') IS NOT NULL
BEGIN
    BEGIN TRY EXEC sp_unbindefault 'dbo.users.created_at'; END TRY BEGIN CATCH END CATCH;
    BEGIN TRY EXEC sp_unbindefault 'dbo.products.created_at'; END TRY BEGIN CATCH END CATCH;
    BEGIN TRY EXEC sp_unbindefault 'dbo.orders.created_at'; END TRY BEGIN CATCH END CATCH;
    DROP DEFAULT dbo.def_NgayHienTaiUTC;
END
GO
-- Xóa ràng buộc default tĩnh trên bảng để có thể bind standalone default
IF OBJECT_ID('dbo.df_users_created_at', 'D') IS NOT NULL
    ALTER TABLE dbo.users DROP CONSTRAINT df_users_created_at;
IF OBJECT_ID('dbo.df_products_created_at', 'D') IS NOT NULL
    ALTER TABLE dbo.products DROP CONSTRAINT df_products_created_at;
IF OBJECT_ID('dbo.df_orders_created_at', 'D') IS NOT NULL
    ALTER TABLE dbo.orders DROP CONSTRAINT df_orders_created_at;
GO
CREATE DEFAULT dbo.def_NgayHienTaiUTC AS SYSUTCDATETIME();
GO
EXEC sp_bindefault 'dbo.def_NgayHienTaiUTC', 'dbo.users.created_at';
EXEC sp_bindefault 'dbo.def_NgayHienTaiUTC', 'dbo.products.created_at';
EXEC sp_bindefault 'dbo.def_NgayHienTaiUTC', 'dbo.orders.created_at';
PRINT N'Đã tạo và gán def_NgayHienTaiUTC.';
GO

-- 2.2. Default: Phí vận chuyển tiêu chuẩn cửa hàng (30.000 VNĐ)
IF OBJECT_ID(N'dbo.def_PhiVanChuyenTieuChuan', N'D') IS NOT NULL
BEGIN
    BEGIN TRY EXEC sp_unbindefault 'dbo.orders.shipping_fee'; END TRY BEGIN CATCH END CATCH;
    DROP DEFAULT dbo.def_PhiVanChuyenTieuChuan;
END
GO
IF OBJECT_ID('dbo.df_orders_shipping', 'D') IS NOT NULL
    ALTER TABLE dbo.orders DROP CONSTRAINT df_orders_shipping;
GO
CREATE DEFAULT dbo.def_PhiVanChuyenTieuChuan AS 30000;
GO
EXEC sp_bindefault 'dbo.def_PhiVanChuyenTieuChuan', 'dbo.orders.shipping_fee';
PRINT N'Đã tạo và gán def_PhiVanChuyenTieuChuan.';
GO

-- 2.3. Default: Số lượng mặc định là 0
IF OBJECT_ID(N'dbo.def_SoLuongMacDinhKhong', N'D') IS NOT NULL
BEGIN
    BEGIN TRY EXEC sp_unbindefault 'dbo.products.stock'; END TRY BEGIN CATCH END CATCH;
    BEGIN TRY EXEC sp_unbindefault 'dbo.orders.discount'; END TRY BEGIN CATCH END CATCH;
    BEGIN TRY EXEC sp_unbindefault 'dbo.orders.vat'; END TRY BEGIN CATCH END CATCH;
    DROP DEFAULT dbo.def_SoLuongMacDinhKhong;
END
GO
IF OBJECT_ID('dbo.df_products_stock', 'D') IS NOT NULL
    ALTER TABLE dbo.products DROP CONSTRAINT df_products_stock;
IF OBJECT_ID('dbo.df_orders_discount', 'D') IS NOT NULL
    ALTER TABLE dbo.orders DROP CONSTRAINT df_orders_discount;
IF OBJECT_ID('dbo.df_orders_vat', 'D') IS NOT NULL
    ALTER TABLE dbo.orders DROP CONSTRAINT df_orders_vat;
GO
CREATE DEFAULT dbo.def_SoLuongMacDinhKhong AS 0;
GO
EXEC sp_bindefault 'dbo.def_SoLuongMacDinhKhong', 'dbo.products.stock';
EXEC sp_bindefault 'dbo.def_SoLuongMacDinhKhong', 'dbo.orders.discount';
EXEC sp_bindefault 'dbo.def_SoLuongMacDinhKhong', 'dbo.orders.vat';
PRINT N'Đã tạo và gán def_SoLuongMacDinhKhong.';
GO

PRINT N'=== HOÀN TẤT CÀI ĐẶT RULES & DEFAULTS ===';
GO

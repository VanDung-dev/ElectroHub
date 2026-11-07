USE [ElectroHub];
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

PRINT N'====================================================================';
PRINT N'BẮT ĐẦU KIỂM THỬ TOÀN DIỆN HỆ THỐNG TRÊN TEST CONTAINER';
PRINT N'====================================================================';
GO

-- 1. TEST RULES & DEFAULTS
PRINT N'--- TEST 1: KIỂM THỬ RULES & CONSTRAINTS ---';
BEGIN TRY
    INSERT INTO dbo.products (slug, sku, name, price, stock)
    VALUES ('test-sp-am', 'EH-AM-01', N'Sản phẩm giá âm', -99000, 10);
    PRINT N'[FAIL] Không chặn được giá âm!';
END TRY
BEGIN CATCH
    PRINT N'[PASS] Đã chặn thành công giá âm: ' + ERROR_MESSAGE();
END CATCH;
GO

BEGIN TRY
    INSERT INTO dbo.cart_items (user_id, product_id, qty)
    VALUES (3, 1, 150);
    PRINT N'[FAIL] Không chặn được số lượng > 99!';
END TRY
BEGIN CATCH
    PRINT N'[PASS] Đã chặn thành công số lượng > 99: ' + ERROR_MESSAGE();
END CATCH;
GO

-- 2. TEST TRIGGER: KIỂM TRA TỒN KHO & TRỪ KHO
PRINT N'--- TEST 2: KIỂM THỬ TRIGGER trg_KiemTraVaTruTonKho ---';
DECLARE @TonKhoTruoc INT;
SELECT @TonKhoTruoc = stock FROM dbo.products WHERE id = 1;
PRINT FORMATMESSAGE(N'Tồn kho sản phẩm 1 trước khi đặt: %d', @TonKhoTruoc);

-- Thử đặt vượt tồn kho
BEGIN TRY
    INSERT INTO dbo.order_items (order_id, product_id, price, qty)
    VALUES (3, 1, 75000, 9999);
    PRINT N'[FAIL] Trigger không chặn được đặt quá tồn kho!';
END TRY
BEGIN CATCH
    PRINT N'[PASS] Trigger đã chặn thành công đặt quá tồn kho: ' + ERROR_MESSAGE();
END CATCH;
GO

-- Đặt số lượng hợp lệ (2 cái)
INSERT INTO dbo.order_items (order_id, product_id, price, qty)
VALUES (3, 1, 75000, 2);

DECLARE @TonKhoSau INT;
SELECT @TonKhoSau = stock FROM dbo.products WHERE id = 1;
PRINT FORMATMESSAGE(N'[PASS] Tồn kho sau khi đặt 2 cái đã tự trừ: %d', @TonKhoSau);
GO

-- 3. TEST TRIGGER: HOÀN KHO KHI HỦY ĐƠN HÀNG
PRINT N'--- TEST 3: KIỂM THỬ TRIGGER trg_HoanKhoKhiHuyDonHang ---';
DECLARE @KhoTruocHuy INT;
SELECT @KhoTruocHuy = stock FROM dbo.products WHERE id = 1;

UPDATE dbo.orders SET status = 'cancelled' WHERE id = 3;

DECLARE @KhoSauHuy INT;
SELECT @KhoSauHuy = stock FROM dbo.products WHERE id = 1;
PRINT FORMATMESSAGE(N'[PASS] Tồn kho trước hủy: %d -> Tồn kho sau hủy đã tự hoàn: %d', @KhoTruocHuy, @KhoSauHuy);
GO

-- 4. TEST TRIGGER: CHỐNG SỬA/XÓA ĐƠN ĐÃ ĐÓNG (DONE)
PRINT N'--- TEST 4: KIỂM THỬ TRIGGER trg_ChongSuaXoaDonHangDaDong ---';
BEGIN TRY
    UPDATE dbo.orders SET status = 'pending' WHERE id = 1; -- Đơn 1 đang là 'done'
    PRINT N'[FAIL] Không chặn được sửa đơn đã done!';
END TRY
BEGIN CATCH
    PRINT N'[PASS] Đã chặn thành công sửa đơn đã hoàn tất: ' + ERROR_MESSAGE();
END CATCH;
GO

BEGIN TRY
    DELETE FROM dbo.orders WHERE id = 1; -- Đơn 1 đang là 'done'
    PRINT N'[FAIL] Không chặn được xóa đơn đã done!';
END TRY
BEGIN CATCH
    PRINT N'[PASS] Đã chặn thành công xóa đơn đã hoàn tất: ' + ERROR_MESSAGE();
END CATCH;
GO

-- 5. TEST STORED PROCEDURE: sp_ThemSanPham
PRINT N'--- TEST 5: KIỂM THỬ STORED PROCEDURE sp_ThemSanPham ---';
DECLARE @NewId INT;
EXEC dbo.sp_ThemSanPham
    @Slug = 'cam-bien-khi-mq2-test',
    @Sku = 'EH-MQ2-TEST',
    @Name = N'Cảm biến rò rỉ khí gas MQ-2 Test',
    @Price = 45000,
    @SalePrice = 39000,
    @Stock = 60,
    @Description = N'Cảm biến phát hiện gas khói.',
    @NewProductId = @NewId OUTPUT;

IF EXISTS (SELECT 1 FROM dbo.products WHERE id = @NewId)
    PRINT FORMATMESSAGE(N'[PASS] sp_ThemSanPham đã tạo sản phẩm thành công với ID = %d', @NewId);
ELSE
    PRINT N'[FAIL] sp_ThemSanPham không tạo được sản phẩm!';
GO

-- 6. TEST STORED PROCEDURE: sp_TaoDonHangTuGioHang
PRINT N'--- TEST 6: KIỂM THỬ STORED PROCEDURE sp_TaoDonHangTuGioHang ---';
-- Thêm sản phẩm vào giỏ User 3
INSERT INTO dbo.cart_items (user_id, product_id, qty) VALUES (3, 2, 2);

DECLARE @OrderIdOut INT, @OrderCodeOut VARCHAR(12);
EXEC dbo.sp_TaoDonHangTuGioHang
    @UserId = 3,
    @Name = N'Nguyễn Văn Dũng',
    @Phone = '0987654321',
    @AddressText = N'Khu Đô Thị ĐHQG TP.HCM',
    @PaymentMethod = 'VNPAY',
    @VoucherCode = 'WELCOME10',
    @OrderId = @OrderIdOut OUTPUT,
    @OrderCode = @OrderCodeOut OUTPUT;

PRINT FORMATMESSAGE(N'[PASS] sp_TaoDonHangTuGioHang: Tạo đơn thành công với mã = %s, ID = %d', @OrderCodeOut, @OrderIdOut);

-- Kiểm tra giỏ hàng đã dọn sạch
IF NOT EXISTS (SELECT 1 FROM dbo.cart_items WHERE user_id = 3)
    PRINT N'[PASS] Giỏ hàng của User 3 đã được tự động dọn sạch sau khi tạo đơn.';
ELSE
    PRINT N'[FAIL] Giỏ hàng chưa được dọn!';
GO

-- 7. TEST STORED PROCEDURE: sp_BaoCaoDoanhThu
PRINT N'--- TEST 7: KIỂM THỬ STORED PROCEDURE sp_BaoCaoDoanhThu ---';
EXEC dbo.sp_BaoCaoDoanhThu;
GO

-- 8. TEST CURSORS
PRINT N'--- TEST 8: KIỂM THỬ CÁC THỦ TỤC CURSORS ---';
-- 8.1 Cursor quét đơn pending
EXEC dbo.sp_Cursor_XuLyDonHangPendingQuaHan @SoGioCho = 0; -- Quét ngay

-- 8.2 Cursor phân hạng khách hàng VIP & tặng voucher
EXEC dbo.sp_Cursor_PhanHangVaTangVoucherKhachHang;

-- 8.3 Cursor kiểm tra yêu cầu hoàn tiền quá 72h
EXEC dbo.sp_Cursor_QuetKiemTraYeuCauHoanTien;
GO

-- 9. TEST VIEWS VÀ FUNCTIONS
PRINT N'--- TEST 9: KIỂM THỬ VIEWS VÀ FUNCTIONS ---';
-- Test scalar function
DECLARE @TongTienTinh INT = dbo.fn_TinhTongTienDonHang(200000, 20000, 10, 30000);
PRINT FORMATMESSAGE(N'[PASS] fn_TinhTongTienDonHang kết quả: %d VNĐ', @TongTienTinh);

-- Test table-valued function
SELECT * FROM dbo.fn_LichSuDonHangUser(3);

-- Test views
SELECT TOP 2 OrderCode, CustomerName, TotalAmount, PaymentMethod FROM dbo.v_ChiTietDonHangTongHop;
SELECT TOP 2 ProductName, CurrentStock, TotalQuantitySold, TotalRevenueGenerated FROM dbo.v_ThongKeSanPhamVaDoanhSo;
SELECT * FROM dbo.v_BaoCaoDoanhThuTheoThang;
GO

PRINT N'====================================================================';
PRINT N'TẤT CẢ CÁC BÀI TEST ĐÃ HOÀN TẤT THÀNH CÔNG TRÊN TEST CONTAINER!';
PRINT N'====================================================================';
GO

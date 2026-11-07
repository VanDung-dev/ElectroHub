-- ============================================================================
-- ELECTROHUB - HỆ QUẢN TRỊ CƠ SỞ DỮ LIỆU (SQL SERVER 2022)
-- File: 07_transactions_concurrency.sql
-- Mục đích: Minh họa Transaction, Concurrency Control, Lock Hints và Savepoints
-- Theo tài liệu môn học: "DBMS_05_ContTransactionProc.pdf"
-- ============================================================================

USE [ElectroHub];
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

PRINT N'=== KỊCH BẢN DEMO TRANSACTIONS VÀ CONCURRENCY CONTROL ===';
GO

-- ----------------------------------------------------------------------------
-- KỊCH BẢN 1: Sử dụng Transaction kèm Savepoint (Điểm lưu)
-- Minh họa: Đặt hàng thành công nhưng bước gửi email thất bại, chỉ rollback
-- bước gửi email mà không làm mất đơn hàng đã tạo.
-- ----------------------------------------------------------------------------
PRINT N'--- DEMO 1: SAVEPOINT TRONG TRANSACTION ---';

BEGIN TRANSACTION;
BEGIN TRY
    -- 1. Trừ tồn kho một sản phẩm
    UPDATE dbo.products
    SET stock = stock - 1
    WHERE sku = 'EH-ESP32';

    -- Đặt điểm lưu
    SAVE TRANSACTION SavePoint_SauKhiTruKho;
    PRINT N'[1] Đã trừ tồn kho và đặt SavePoint_SauKhiTruKho.';

    -- 2. Giả lập một lỗi nghiệp vụ ở bước phụ (ví dụ trừ voucher sai)
    -- Gặp lỗi thì quay lại điểm lưu
    IF (1 = 0) -- Đổi thành 1 = 1 để test lỗi
    BEGIN
        RAISERROR(N'Lỗi giả lập ở bước phụ.', 16, 1);
    END

    COMMIT TRANSACTION;
    PRINT N'[2] Transaction thành công trọn vẹn.';
END TRY
BEGIN CATCH
    PRINT N'[Lỗi xảy ra]: ' + ERROR_MESSAGE();
    IF @@TRANCOUNT > 0
    BEGIN
        -- Quay về điểm lưu thay vì hủy toàn bộ
        ROLLBACK TRANSACTION SavePoint_SauKhiTruKho;
        COMMIT TRANSACTION;
        PRINT N'Đã rollback về SavePoint_SauKhiTruKho và bảo toàn bước trừ kho.';
    END
END CATCH;
GO


-- ----------------------------------------------------------------------------
-- KỊCH BẢN 2: Demo Lock Hints chống Race Condition (Tranh chấp tồn kho)
-- Minh họa: Sử dụng WITH (UPDLOCK, ROWLOCK) để khóa dòng sản phẩm đang đọc
-- ngăn chặn 2 người mua cùng lúc khi chỉ còn 1 sản phẩm cuối cùng trong kho.
-- ----------------------------------------------------------------------------
PRINT N'--- DEMO 2: LOCK HINTS CHỐNG RACE CONDITION KHI ĐẶT HÀNG ---';

DECLARE @MaSP VARCHAR(32) = 'EH-ESP32';
DECLARE @SoLuongMua INT = 1;

BEGIN TRANSACTION;
BEGIN TRY
    DECLARE @TonKhoHienTai INT;

    -- Sử dụng UPDLOCK + ROWLOCK để giữ khóa cập nhật trên dòng này cho đến khi kết thúc Tran
    SELECT @TonKhoHienTai = stock
    FROM dbo.products WITH (UPDLOCK, ROWLOCK)
    WHERE sku = @MaSP;

    PRINT FORMATMESSAGE(N'Tồn kho đọc được (đang được giữ khóa): %d', @TonKhoHienTai);

    IF @TonKhoHienTai < @SoLuongMua
    BEGIN
        RAISERROR(N'Hết hàng! Không thể đặt.', 16, 1);
    END

    -- Cập nhật trừ kho an toàn
    UPDATE dbo.products
    SET stock = stock - @SoLuongMua
    WHERE sku = @MaSP;

    COMMIT TRANSACTION;
    PRINT N'Đặt hàng và giữ khóa an toàn thành công!';
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;
    PRINT N'[Lỗi Race Condition]: ' + ERROR_MESSAGE();
END CATCH;
GO


-- ----------------------------------------------------------------------------
-- KỊCH BẢN 3: Các mức cô lập giao dịch (Transaction Isolation Levels)
-- ----------------------------------------------------------------------------
PRINT N'--- DEMO 3: THIẾT LẬP ISOLATION LEVELS ---';

-- Mức 1: READ COMMITTED (Mặc định của SQL Server - Chống Dirty Read)
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
BEGIN TRANSACTION;
    SELECT COUNT(*) AS TongDonHangTuongTrinh FROM dbo.orders;
COMMIT TRANSACTION;

-- Mức 2: REPEATABLE READ (Chống Non-Repeatable Read)
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
BEGIN TRANSACTION;
    SELECT id, price, stock FROM dbo.products WHERE sku = 'EH-ESP32';
    -- Trong suốt thời gian Tran chạy, không ai có thể sửa giá hay tồn kho dòng này
COMMIT TRANSACTION;

-- Mức 3: SERIALIZABLE (Mức cao nhất - Chống Phantom Read bằng Range Lock)
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
BEGIN TRANSACTION;
    SELECT * FROM dbo.products WHERE price > 500000;
    -- Ngăn chặn người khác chèn sản phẩm mới có giá > 500.000 trong khi Tran đang mở
COMMIT TRANSACTION;

-- Đưa về mức mặc định
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
PRINT N'Đã hoàn tất kịch bản demo Isolation Levels.';
GO

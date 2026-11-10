-- ============================================================================
-- ELECTROHUB - HỆ QUẢN TRỊ CƠ SỞ DỮ LIỆU (SQL SERVER 2022)
-- File: 03_triggers.sql
-- Mục đích: Cài đặt Triggers đảm bảo toàn vẹn dữ liệu và tự động hóa nghiệp vụ
-- Theo tài liệu môn học: "CaiDat Rules_SP_Trigger.pdf"
-- ============================================================================

USE [ElectroHub];
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

PRINT N'=== BẮT ĐẦU CÀI ĐẶT TRIGGERS ===';
GO

-- ----------------------------------------------------------------------------
-- TRIGGER 1: trg_KiemTraVaTruTonKho
-- Loại: AFTER INSERT trên order_items
-- Nhiệm vụ:
--   1. Kiểm tra tồn kho của sản phẩm trong bảng products.
--   2. Nếu không đủ hàng (stock < qty đặt) -> ROLLBACK và báo lỗi.
--   3. Nếu đủ hàng -> Tự động trừ tồn kho tương ứng.
-- ----------------------------------------------------------------------------
CREATE OR ALTER TRIGGER dbo.trg_KiemTraVaTruTonKho
ON dbo.order_items
AFTER INSERT
AS
BEGIN
    SET NOCOUNT ON;

    -- Kiểm tra nếu có sản phẩm nào không đủ tồn kho
    IF EXISTS (
        SELECT 1
        FROM inserted i
        JOIN dbo.products p ON i.product_id = p.id
        WHERE p.stock < i.qty
    )
    BEGIN
        DECLARE @TenSP NVARCHAR(200);
        DECLARE @TonKho INT;
        DECLARE @SoLuongDat INT;

        SELECT TOP 1
            @TenSP = p.name,
            @TonKho = p.stock,
            @SoLuongDat = i.qty
        FROM inserted i
        JOIN dbo.products p ON i.product_id = p.id
        WHERE p.stock < i.qty;

        DECLARE @Msg NVARCHAR(500) = FORMATMESSAGE(
            N'Lỗi tồn kho: Sản phẩm "%s" chỉ còn %d trong kho, không đủ đáp ứng số lượng đặt %d.',
            @TenSP, @TonKho, @SoLuongDat
        );

        RAISERROR(@Msg, 16, 1);
        ROLLBACK TRANSACTION;
        RETURN;
    END

    -- Trừ tồn kho sản phẩm tương ứng với số lượng trong inserted
    UPDATE p
    SET p.stock = p.stock - i.qty
    FROM dbo.products p
    JOIN inserted i ON p.id = i.product_id;

    PRINT N'Trigger trg_KiemTraVaTruTonKho: Đã cập nhật trừ tồn kho thành công.';
END;
GO


-- ----------------------------------------------------------------------------
-- TRIGGER 2: trg_HoanKhoKhiHuyDonHang
-- Loại: AFTER UPDATE trên orders
-- Nhiệm vụ:
--   Khi đơn hàng chuyển sang trạng thái "cancelled":
--   1. Tự động hoàn trả tồn kho cho tất cả sản phẩm thuộc đơn đó.
--   2. Hoàn lại 1 lượt dùng cho mã voucher (nếu có sử dụng voucher).
-- ----------------------------------------------------------------------------
CREATE OR ALTER TRIGGER dbo.trg_HoanKhoKhiHuyDonHang
ON dbo.orders
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    -- Chỉ xử lý khi có đơn hàng vừa chuyển trạng thái thành 'cancelled'
    IF UPDATE(status) AND EXISTS (
        SELECT 1
        FROM inserted i
        JOIN deleted d ON i.id = d.id
        WHERE i.status = 'cancelled' AND d.status <> 'cancelled'
    )
    BEGIN
        -- 1. Hoàn lại tồn kho cho từng sản phẩm trong order_items
        UPDATE p
        SET p.stock = p.stock + oi.qty
        FROM dbo.products p
        JOIN dbo.order_items oi ON p.id = oi.product_id
        JOIN inserted i ON oi.order_id = i.id
        JOIN deleted d ON i.id = d.id
        WHERE i.status = 'cancelled' AND d.status <> 'cancelled';

        -- 2. Hoàn lại lượt sử dụng voucher nếu đơn hàng có áp dụng mã
        UPDATE v
        SET v.qty_left = v.qty_left + 1
        FROM dbo.vouchers v
        JOIN inserted i ON v.code = i.voucher_code
        JOIN deleted d ON i.id = d.id
        WHERE i.status = 'cancelled' 
          AND d.status <> 'cancelled' 
          AND i.voucher_code IS NOT NULL;

        PRINT N'Trigger trg_HoanKhoKhiHuyDonHang: Đã hoàn trả tồn kho và voucher cho đơn hàng bị hủy.';
    END
END;
GO


-- ----------------------------------------------------------------------------
-- TRIGGER 3: trg_ChongSuaXoaDonHangDaDong
-- Loại: INSTEAD OF DELETE, UPDATE trên orders
-- Nhiệm vụ:
--   Bảo vệ dữ liệu kế toán & bán hàng:
--   Không cho phép XÓA đơn hàng hoặc SỬA ĐỔI trạng thái của đơn đã "done" hoặc "cancelled".
-- ----------------------------------------------------------------------------
CREATE OR ALTER TRIGGER dbo.trg_ChongSuaXoaDonHangDaDong
ON dbo.orders
INSTEAD OF DELETE, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    -- Kiểm tra trường hợp DELETE
    IF NOT EXISTS (SELECT 1 FROM inserted) AND EXISTS (SELECT 1 FROM deleted)
    BEGIN
        IF EXISTS (SELECT 1 FROM deleted WHERE status IN ('done', 'shipping'))
        BEGIN
            RAISERROR(N'Lỗi nghiệp vụ: Không thể xóa đơn hàng đang giao hoặc đã hoàn tất thành công.', 16, 1);
            ROLLBACK TRANSACTION;
            RETURN;
        END

        -- Cho phép xóa nếu thỏa điều kiện
        DELETE FROM dbo.orders
        WHERE id IN (SELECT id FROM deleted);
        RETURN;
    END

    -- Kiểm tra trường hợp UPDATE
    IF EXISTS (SELECT 1 FROM inserted) AND EXISTS (SELECT 1 FROM deleted)
    BEGIN
        -- Đơn đã 'done' hoặc 'cancelled' thì không cho đổi trạng thái khác
        IF EXISTS (
            SELECT 1
            FROM inserted i
            JOIN deleted d ON i.id = d.id
            WHERE d.status IN ('done', 'cancelled') AND i.status <> d.status
        )
        BEGIN
            RAISERROR(N'Lỗi nghiệp vụ: Đơn hàng đã ở trạng thái kết thúc (done/cancelled), không thể thay đổi trạng thái nữa.', 16, 1);
            ROLLBACK TRANSACTION;
            RETURN;
        END

        -- Thực hiện UPDATE bình thường
        UPDATE o
        SET 
            o.status = i.status,
            o.subtotal = i.subtotal,
            o.discount = i.discount,
            o.vat = i.vat,
            o.shipping_fee = i.shipping_fee,
            o.total = i.total,
            o.address = i.address
        FROM dbo.orders o
        JOIN inserted i ON o.id = i.id;
    END
END;
GO


-- ----------------------------------------------------------------------------
-- TRIGGER 4: trg_DongBoThanhToanKhiHoanTien
-- Loại: AFTER UPDATE trên refunds
-- Nhiệm vụ:
--   Khi yêu cầu hoàn tiền được duyệt thành công (status = 'succeeded'):
--   Tự động cập nhật bảng payments tương ứng thành 'refunded'.
-- ----------------------------------------------------------------------------
CREATE OR ALTER TRIGGER dbo.trg_DongBoThanhToanKhiHoanTien
ON dbo.refunds
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    IF UPDATE(status)
    BEGIN
        UPDATE p
        SET 
            p.status = 'refunded',
            p.provider_status = 'REFUNDED'
        FROM dbo.payments p
        JOIN inserted i ON p.id = i.payment_id
        JOIN deleted d ON i.id = d.id
        WHERE i.status = 'succeeded' AND d.status <> 'succeeded';

        PRINT N'Trigger trg_DongBoThanhToanKhiHoanTien: Đã đồng bộ trạng thái payment sang refunded.';
    END
END;
GO

PRINT N'=== HOÀN TẤT CÀI ĐẶT TRIGGERS ===';
GO

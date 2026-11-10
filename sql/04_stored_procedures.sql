-- ============================================================================
-- ELECTROHUB - HỆ QUẢN TRỊ CƠ SỞ DỮ LIỆU (SQL SERVER 2022)
-- File: 04_stored_procedures.sql
-- Mục đích: Cài đặt Stored Procedures (Thủ tục lưu trữ) cho luồng nghiệp vụ
-- Theo tài liệu môn học: "CaiDat Rules_SP_Trigger.pdf" & "DBMS_05_ContTransactionProc.pdf"
-- ============================================================================

USE [ElectroHub];
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

PRINT N'=== BẮT ĐẦU CÀI ĐẶT STORED PROCEDURES ===';
GO

-- ----------------------------------------------------------------------------
-- THỦ TỤC 1: sp_ThemSanPham
-- Nhiệm vụ: Thêm mới sản phẩm, kiểm tra tính duy nhất của SKU/Slug
-- ----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE dbo.sp_ThemSanPham
    @Slug VARCHAR(200),
    @Sku VARCHAR(32),
    @Name NVARCHAR(200),
    @Price INT,
    @SalePrice INT = NULL,
    @Stock INT = 0,
    @Description NVARCHAR(MAX) = NULL,
    @ImageUrl VARCHAR(500) = '/static/img/product-placeholder.svg',
    @NewProductId INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRY
        -- Kiểm tra giá trị đầu vào
        IF @Price < 0
        BEGIN
            RAISERROR(N'Giá sản phẩm không được âm.', 16, 1);
            RETURN -1;
        END

        IF @SalePrice IS NOT NULL AND (@SalePrice < 0 OR @SalePrice > @Price)
        BEGIN
            RAISERROR(N'Giá khuyến mãi phải lớn hơn hoặc bằng 0 và không vượt quá giá gốc.', 16, 1);
            RETURN -2;
        END

        IF EXISTS (SELECT 1 FROM dbo.products WHERE slug = @Slug)
        BEGIN
            RAISERROR(N'Slug "%s" đã tồn tại.', 16, 1, @Slug);
            RETURN -3;
        END

        IF EXISTS (SELECT 1 FROM dbo.products WHERE sku = @Sku)
        BEGIN
            RAISERROR(N'Mã SKU "%s" đã tồn tại.', 16, 1, @Sku);
            RETURN -4;
        END

        INSERT INTO dbo.products (slug, sku, name, description, image_url, price, sale_price, stock)
        VALUES (@Slug, @Sku, @Name, @Description, @ImageUrl, @Price, @SalePrice, @Stock);

        SET @NewProductId = SCOPE_IDENTITY();
        PRINT FORMATMESSAGE(N'Đã thêm sản phẩm thành công với ID = %d', @NewProductId);
        RETURN 0;
    END TRY
    BEGIN CATCH
        DECLARE @ErrorMessage NVARCHAR(4000) = ERROR_MESSAGE();
        RAISERROR(@ErrorMessage, 16, 1);
        RETURN -99;
    END CATCH
END;
GO


-- ----------------------------------------------------------------------------
-- THỦ TỤC 2: sp_TaoDonHangTuGioHang
-- Nhiệm vụ: Chuyển toàn bộ giỏ hàng của User thành đơn đặt hàng (Atomic Transaction)
-- Tham số:
--   @UserId: ID người mua
--   @Name, @Phone, @AddressText: Thông tin giao hàng
--   @PaymentMethod: 'VNPAY', 'PAYPAL' hoặc 'COD'
--   @VoucherCode: Mã voucher (nếu có)
--   @OrderId OUTPUT, @OrderCode OUTPUT: Kết quả trả về
-- ----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE dbo.sp_TaoDonHangTuGioHang
    @UserId INT,
    @Name NVARCHAR(100),
    @Phone VARCHAR(20),
    @AddressText NVARCHAR(500),
    @PaymentMethod VARCHAR(32) = 'COD',
    @VoucherCode VARCHAR(32) = NULL,
    @OrderId INT OUTPUT,
    @OrderCode VARCHAR(12) OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRY
        BEGIN TRANSACTION;

        -- 1. Kiểm tra giỏ hàng có sản phẩm không
        IF NOT EXISTS (SELECT 1 FROM dbo.cart_items WHERE user_id = @UserId)
        BEGIN
            RAISERROR(N'Giỏ hàng của người dùng đang trống, không thể tạo đơn.', 16, 1);
        END

        -- 2. Kiểm tra tồn kho từng mặt hàng trong giỏ
        IF EXISTS (
            SELECT 1 
            FROM dbo.cart_items ci
            JOIN dbo.products p ON ci.product_id = p.id
            WHERE ci.user_id = @UserId AND ci.qty > p.stock
        )
        BEGIN
            RAISERROR(N'Một số sản phẩm trong giỏ không đủ tồn kho để thanh toán.', 16, 1);
        END

        -- 3. Tính tạm tính (Subtotal)
        DECLARE @Subtotal INT = 0;
        SELECT @Subtotal = SUM(COALESCE(p.sale_price, p.price) * ci.qty)
        FROM dbo.cart_items ci
        JOIN dbo.products p ON ci.product_id = p.id
        WHERE ci.user_id = @UserId;

        -- 4. Xử lý Voucher (nếu có)
        DECLARE @Discount INT = 0;
        IF @VoucherCode IS NOT NULL AND LEN(TRIM(@VoucherCode)) > 0
        BEGIN
            DECLARE @Percent INT, @MaxDiscount INT, @QtyLeft INT, @ExpiredAt DATETIME2;
            SELECT 
                @Percent = [percent], 
                @MaxDiscount = max_discount, 
                @QtyLeft = qty_left, 
                @ExpiredAt = expired_at
            FROM dbo.vouchers WITH (UPDLOCK, ROWLOCK)
            WHERE code = @VoucherCode;

            IF @Percent IS NULL
                RAISERROR(N'Mã voucher không tồn tại.', 16, 1);

            IF @ExpiredAt <= SYSUTCDATETIME()
                RAISERROR(N'Mã voucher đã hết hạn.', 16, 1);

            IF @QtyLeft <= 0
                RAISERROR(N'Mã voucher đã hết lượt sử dụng.', 16, 1);

            -- Tính số tiền giảm giá
            SET @Discount = (@Subtotal * @Percent) / 100;
            IF @Discount > @MaxDiscount
                SET @Discount = @MaxDiscount;
            IF @Discount > @Subtotal
                SET @Discount = @Subtotal;

            -- Trừ 1 lượt voucher
            UPDATE dbo.vouchers
            SET qty_left = qty_left - 1
            WHERE code = @VoucherCode;
        END

        -- 5. Tính VAT (10%), Phí vận chuyển (30.000 VNĐ) và Tổng tiền
        DECLARE @NetGoods INT = @Subtotal - @Discount;
        IF @NetGoods < 0 SET @NetGoods = 0;
        DECLARE @VAT INT = (@NetGoods * 10 + 50) / 100;
        DECLARE @ShippingFee INT = 30000;
        DECLARE @Total INT = @NetGoods + @VAT + @ShippingFee;

        -- 6. Sinh mã đơn hàng duy nhất (VD: EH-A1B2)
        SET @OrderCode = 'EH-' + UPPER(SUBSTRING(REPLACE(CONVERT(VARCHAR(36), NEWID()), '-', ''), 1, 4));

        -- 7. Chuẩn bị JSON địa chỉ giao hàng
        DECLARE @AddressJSON NVARCHAR(MAX) = JSON_OBJECT(
            'name': @Name,
            'phone': @Phone,
            'address': @AddressText
        );

        -- 8. Tạo đơn hàng vào bảng orders
        INSERT INTO dbo.orders (code, user_id, status, subtotal, discount, vat, shipping_fee, total, voucher_code, address)
        VALUES (@OrderCode, @UserId, 'pending', @Subtotal, @Discount, @VAT, @ShippingFee, @Total, @VoucherCode, @AddressJSON);

        SET @OrderId = SCOPE_IDENTITY();

        -- 9. Sao chép chi tiết từ cart_items sang order_items
        -- (Lưu ý: Trigger trg_KiemTraVaTruTonKho sẽ tự động chạy để trừ tồn kho)
        INSERT INTO dbo.order_items (order_id, product_id, price, qty)
        SELECT 
            @OrderId, 
            ci.product_id, 
            COALESCE(p.sale_price, p.price), 
            ci.qty
        FROM dbo.cart_items ci
        JOIN dbo.products p ON ci.product_id = p.id
        WHERE ci.user_id = @UserId;

        -- 10. Tạo bản ghi thanh toán tương ứng
        INSERT INTO dbo.payments (order_id, method, status, provider, currency, amount_minor)
        VALUES (
            @OrderId, 
            @PaymentMethod, 
            'pending', 
            LOWER(@PaymentMethod), 
            'VND', 
            CAST(@Total AS BIGINT) * 100
        );

        -- 11. Xóa sạch giỏ hàng của user sau khi đặt hàng thành công
        DELETE FROM dbo.cart_items WHERE user_id = @UserId;

        COMMIT TRANSACTION;
        PRINT FORMATMESSAGE(N'Đã tạo đơn hàng %s (ID = %d) thành công.', @OrderCode, @OrderId);
        RETURN 0;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        DECLARE @Err NVARCHAR(4000) = ERROR_MESSAGE();
        RAISERROR(@Err, 16, 1);
        RETURN -1;
    END CATCH
END;
GO


-- ----------------------------------------------------------------------------
-- THỦ TỤC 3: sp_CapNhatTrangThaiDonHang
-- Nhiệm vụ: Cập nhật trạng thái đơn hàng theo state machine chuẩn
-- ----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE dbo.sp_CapNhatTrangThaiDonHang
    @OrderCode VARCHAR(12),
    @NewStatus VARCHAR(16)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRY
        BEGIN TRANSACTION;

        DECLARE @OrderId INT, @CurrentStatus VARCHAR(16), @PaymentStatus VARCHAR(20);

        SELECT 
            @OrderId = o.id, 
            @CurrentStatus = o.status,
            @PaymentStatus = p.status
        FROM dbo.orders o WITH (UPDLOCK, ROWLOCK)
        LEFT JOIN dbo.payments p ON o.id = p.order_id
        WHERE o.code = @OrderCode;

        IF @OrderId IS NULL
        BEGIN
            RAISERROR(N'Không tìm thấy đơn hàng mã "%s".', 16, 1, @OrderCode);
        END

        IF @CurrentStatus = @NewStatus
        BEGIN
            RAISERROR(N'Đơn hàng hiện đã ở trạng thái "%s".', 16, 1, @NewStatus);
        END

        -- Kiểm tra chuyển đổi trạng thái hợp lệ
        -- pending -> confirmed, cancelled
        -- confirmed -> shipping, cancelled
        -- shipping -> done
        DECLARE @HopLe BIT = 0;
        IF @CurrentStatus = 'pending' AND @NewStatus IN ('confirmed', 'cancelled') SET @HopLe = 1;
        IF @CurrentStatus = 'confirmed' AND @NewStatus IN ('shipping', 'cancelled') SET @HopLe = 1;
        IF @CurrentStatus = 'shipping' AND @NewStatus = 'done' SET @HopLe = 1;

        IF @HopLe = 0
        BEGIN
            DECLARE @ErrTransition NVARCHAR(300) = FORMATMESSAGE(
                N'Không thể chuyển trạng thái từ "%s" sang "%s".', @CurrentStatus, @NewStatus
            );
            RAISERROR(@ErrTransition, 16, 1);
        END

        -- Nếu duyệt đơn ('confirmed', 'shipping', 'done'), phải thanh toán thành công trước
        IF @NewStatus IN ('confirmed', 'shipping', 'done') AND (@PaymentStatus IS NULL OR @PaymentStatus <> 'paid')
        BEGIN
            RAISERROR(N'Đơn hàng chưa thanh toán thành công (status <> paid), không thể xử lý tiếp.', 16, 1);
        END

        -- Cập nhật trạng thái đơn (Trigger trg_HoanKhoKhiHuyDonHang sẽ tự chạy nếu cancelled)
        UPDATE dbo.orders
        SET status = @NewStatus
        WHERE id = @OrderId;

        COMMIT TRANSACTION;
        PRINT FORMATMESSAGE(N'Đã chuyển trạng thái đơn hàng %s sang "%s".', @OrderCode, @NewStatus);
        RETURN 0;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        DECLARE @ErrMsg NVARCHAR(4000) = ERROR_MESSAGE();
        RAISERROR(@ErrMsg, 16, 1);
        RETURN -1;
    END CATCH
END;
GO


-- ----------------------------------------------------------------------------
-- THỦ TỤC 4: sp_HuyDonHangVaYeuCauHoanTien
-- Nhiệm vụ: Hủy đơn hàng và tự động tạo bản ghi giữ tiền 72 giờ nếu đã trả
-- ----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE dbo.sp_HuyDonHangVaYeuCauHoanTien
    @OrderCode VARCHAR(12),
    @UserId INT,
    @Reason NVARCHAR(255) = N'Khách hàng yêu cầu hủy đơn'
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRY
        BEGIN TRANSACTION;

        DECLARE @OrderId INT, @CurrentStatus VARCHAR(16), @Total INT;
        DECLARE @PaymentId INT, @PaymentStatus VARCHAR(20), @AmountMinor BIGINT, @Currency VARCHAR(8);

        SELECT 
            @OrderId = o.id,
            @CurrentStatus = o.status,
            @Total = o.total,
            @PaymentId = p.id,
            @PaymentStatus = p.status,
            @AmountMinor = p.amount_minor,
            @Currency = p.currency
        FROM dbo.orders o WITH (UPDLOCK, ROWLOCK)
        LEFT JOIN dbo.payments p ON o.id = p.order_id
        WHERE o.code = @OrderCode AND o.user_id = @UserId;

        IF @OrderId IS NULL
        BEGIN
            RAISERROR(N'Không tìm thấy đơn hàng của bạn để hủy.', 16, 1);
        END

        IF @CurrentStatus NOT IN ('pending', 'confirmed')
        BEGIN
            RAISERROR(N'Đơn hàng đang giao hoặc đã hoàn tất, không thể tự hủy.', 16, 1);
        END

        -- 1. Cập nhật trạng thái đơn sang 'cancelled' (Trigger sẽ tự hoàn tồn kho và voucher)
        UPDATE dbo.orders
        SET status = 'cancelled'
        WHERE id = @OrderId;

        -- 2. Nếu đơn đã thanh toán trước (status = 'paid'), mở yêu cầu hoàn tiền giữ trong 72h
        IF @PaymentStatus = 'paid'
        BEGIN
            DECLARE @Now DATETIME2 = SYSUTCDATETIME();
            DECLARE @DueAt DATETIME2 = DATEADD(HOUR, 72, @Now);

            INSERT INTO dbo.refunds (
                order_id, payment_id, status, amount, currency, reason, 
                requested_by, requested_at, due_at, created_at, updated_at
            )
            VALUES (
                @OrderId, @PaymentId, 'scheduled', 
                COALESCE(@AmountMinor, CAST(@Total AS BIGINT) * 100), 
                COALESCE(@Currency, 'VND'), 
                @Reason, @UserId, @Now, @DueAt, @Now, @Now
            );

            UPDATE dbo.payments
            SET status = 'refund_pending'
            WHERE id = @PaymentId;

            PRINT N'Đã mở yêu cầu hoàn tiền (giữ trong 72 giờ để shop xác nhận).';
        END

        COMMIT TRANSACTION;
        PRINT FORMATMESSAGE(N'Đã hủy đơn hàng %s thành công.', @OrderCode);
        RETURN 0;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;

        DECLARE @Err NVARCHAR(4000) = ERROR_MESSAGE();
        RAISERROR(@Err, 16, 1);
        RETURN -1;
    END CATCH
END;
GO


-- ----------------------------------------------------------------------------
-- THỦ TỤC 5: sp_BaoCaoDoanhThu
-- Nhiệm vụ: Thống kê tổng số đơn, doanh thu, đơn hủy theo khoảng thời gian
-- ----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE dbo.sp_BaoCaoDoanhThu
    @TuNgay DATETIME2 = NULL,
    @DenNgay DATETIME2 = NULL
AS
BEGIN
    SET NOCOUNT ON;

    SET @TuNgay = COALESCE(@TuNgay, '2000-01-01');
    SET @DenNgay = COALESCE(@DenNgay, SYSUTCDATETIME());

    SELECT
        COUNT(id) AS TongSoDon,
        SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS SoDonThanhCong,
        SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS SoDonHuy,
        SUM(CASE WHEN status = 'done' THEN total ELSE 0 END) AS TongDoanhThuVND,
        AVG(CASE WHEN status = 'done' THEN total ELSE NULL END) AS GiaTriDonTrungBinhVND,
        SUM(discount) AS TongTienVoucherDaGiamVND
    FROM dbo.orders
    WHERE created_at BETWEEN @TuNgay AND @DenNgay;
END;
GO

PRINT N'=== HOÀN TẤT CÀI ĐẶT STORED PROCEDURES ===';
GO

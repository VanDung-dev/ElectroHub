-- ============================================================================
-- ELECTROHUB - HỆ QUẢN TRỊ CƠ SỞ DỮ LIỆU (SQL SERVER 2022)
-- File: 05_cursors.sql
-- Mục đích: Cài đặt và ứng dụng CURSOR (Con trỏ duyệt bản ghi từng dòng)
-- Theo tài liệu môn học: "DBMS_03_ProgrammingCursors.pdf"
-- ============================================================================

USE [ElectroHub];
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

PRINT N'=== BẮT ĐẦU CÀI ĐẶT CÁC THỦ TỤC DÙNG CURSOR ===';
GO

-- ----------------------------------------------------------------------------
-- CURSOR 1: sp_Cursor_XuLyDonHangPendingQuaHan
-- Nhiệm vụ:
--   Duyệt qua danh sách các đơn hàng còn ở trạng thái "pending" đã quá @SoGioCho (mặc định 24h).
--   Với mỗi đơn hàng:
--     1. Đọc mã đơn, người mua và tổng tiền.
--     2. Chuyển trạng thái đơn sang "cancelled" (Trigger sẽ tự động hoàn tồn kho).
--     3. In thông báo xử lý từng dòng.
-- ----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE dbo.sp_Cursor_XuLyDonHangPendingQuaHan
    @SoGioCho INT = 24
AS
BEGIN
    SET NOCOUNT ON;

    PRINT FORMATMESSAGE(N'--- BẮT ĐẦU QUÉT ĐƠN HÀNG PENDING QUÁ %d GIỜ ---', @SoGioCho);

    -- Khai báo các biến nhận dữ liệu từ Cursor
    DECLARE @OrderId INT;
    DECLARE @OrderCode VARCHAR(12);
    DECLARE @Total INT;
    DECLARE @CreatedAt DATETIME2;
    DECLARE @SoLuongDaHuy INT = 0;

    -- Thời điểm mốc quá hạn
    DECLARE @MocThoiGian DATETIME2 = DATEADD(HOUR, -@SoGioCho, SYSUTCDATETIME());

    -- 1. Khai báo Cursor
    DECLARE cur_DonHangQuaHan CURSOR FOR
        SELECT id, code, total, created_at
        FROM dbo.orders
        WHERE status = 'pending' AND created_at <= @MocThoiGian
        ORDER BY created_at ASC;

    -- 2. Mở Cursor
    OPEN cur_DonHangQuaHan;

    -- 3. Đọc bản ghi đầu tiên
    FETCH NEXT FROM cur_DonHangQuaHan INTO @OrderId, @OrderCode, @Total, @CreatedAt;

    -- 4. Vòng lặp duyệt từng dòng cho đến hết dữ liệu (@@FETCH_STATUS = 0)
    WHILE @@FETCH_STATUS = 0
    BEGIN
        PRINT FORMATMESSAGE(N'-> Đang hủy đơn hàng quá hạn: %s (ID: %d, Giá trị: %d VNĐ, Tạo lúc: %s)',
            @OrderCode, @OrderId, @Total, CONVERT(VARCHAR(30), @CreatedAt, 120));

        -- Cập nhật hủy đơn (Trigger trg_HoanKhoKhiHuyDonHang sẽ tự động hoàn trả tồn kho)
        UPDATE dbo.orders
        SET status = 'cancelled'
        WHERE id = @OrderId;

        SET @SoLuongDaHuy = @SoLuongDaHuy + 1;

        -- Đọc bản ghi tiếp theo
        FETCH NEXT FROM cur_DonHangQuaHan INTO @OrderId, @OrderCode, @Total, @CreatedAt;
    END

    -- 5. Đóng Cursor
    CLOSE cur_DonHangQuaHan;

    -- 6. Hủy vùng nhớ Cursor
    DEALLOCATE cur_DonHangQuaHan;

    PRINT FORMATMESSAGE(N'--- HOÀN TẤT: Đã tự động hủy %d đơn hàng pending quá hạn ---', @SoLuongDaHuy);
END;
GO


-- ----------------------------------------------------------------------------
-- CURSOR 2: sp_Cursor_PhanHangVaTangVoucherKhachHang
-- Nhiệm vụ:
--   Duyệt qua danh sách toàn bộ khách hàng:
--     1. Tính tổng chi tiêu từ các đơn hàng thành công (status = 'done').
--     2. Phân loại thứ hạng:
--        - Chi tiêu >= 10.000.000đ: Hạng VIP -> Tự động cấp mã voucher "VIP-<id>" giảm 15%.
--        - Chi tiêu >= 2.000.000đ : Hạng Thân thiết -> Tự động cấp mã "LOYAL-<id>" giảm 5%.
--        - Còn lại: Hạng Thường.
-- ----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE dbo.sp_Cursor_PhanHangVaTangVoucherKhachHang
AS
BEGIN
    SET NOCOUNT ON;

    PRINT N'--- BẮT ĐẦU PHÂN HẠNG VÀ TẶNG VOUCHER KHÁCH HÀNG (DÙNG CURSOR) ---';

    -- Khai báo biến Cursor
    DECLARE @UserId INT;
    DECLARE @Email VARCHAR(255);
    DECLARE @Name NVARCHAR(100);
    DECLARE @TongChiTieu INT;
    DECLARE @Hang NVARCHAR(50);
    DECLARE @MaVoucher VARCHAR(32);

    -- Khai báo Cursor duyệt qua các khách hàng (role = 'customer')
    DECLARE cur_KhachHang CURSOR FOR
        SELECT 
            u.id, 
            u.email, 
            u.name,
            COALESCE(SUM(o.total), 0) AS TongChiTieu
        FROM dbo.users u
        LEFT JOIN dbo.orders o ON u.id = o.user_id AND o.status = 'done'
        WHERE u.role = 'customer'
        GROUP BY u.id, u.email, u.name
        ORDER BY TongChiTieu DESC;

    OPEN cur_KhachHang;

    FETCH NEXT FROM cur_KhachHang INTO @UserId, @Email, @Name, @TongChiTieu;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        IF @TongChiTieu >= 10000000
        BEGIN
            SET @Hang = N'VIP (Giảm 15%)';
            SET @MaVoucher = 'VIP-' + CAST(@UserId AS VARCHAR(10));

            -- Tự động tạo voucher VIP độc quyền cho khách nếu chưa tồn tại
            IF NOT EXISTS (SELECT 1 FROM dbo.vouchers WHERE code = @MaVoucher)
            BEGIN
                INSERT INTO dbo.vouchers (code, [percent], max_discount, qty_left, expired_at)
                VALUES (@MaVoucher, 15, 200000, 3, DATEADD(MONTH, 3, SYSUTCDATETIME()));
                PRINT FORMATMESSAGE(N'[*] Khách hàng %s (ID %d) đạt VIP! Đã tạo mã voucher: %s', @Name, @UserId, @MaVoucher);
            END
        END
        ELSE IF @TongChiTieu >= 2000000
        BEGIN
            SET @Hang = N'Thân thiết (Giảm 5%)';
            SET @MaVoucher = 'LOYAL-' + CAST(@UserId AS VARCHAR(10));

            IF NOT EXISTS (SELECT 1 FROM dbo.vouchers WHERE code = @MaVoucher)
            BEGIN
                INSERT INTO dbo.vouchers (code, [percent], max_discount, qty_left, expired_at)
                VALUES (@MaVoucher, 5, 50000, 2, DATEADD(MONTH, 1, SYSUTCDATETIME()));
                PRINT FORMATMESSAGE(N'[*] Khách hàng %s (ID %d) đạt Thân thiết! Đã tạo mã voucher: %s', @Name, @UserId, @MaVoucher);
            END
        END
        ELSE
        BEGIN
            SET @Hang = N'Tiềm năng';
        END

        PRINT FORMATMESSAGE(N'Khách hàng: %s | Email: %s | Chi tiêu: %d VNĐ | Hạng: %s',
            @Name, @Email, @TongChiTieu, @Hang);

        FETCH NEXT FROM cur_KhachHang INTO @UserId, @Email, @Name, @TongChiTieu;
    END

    CLOSE cur_KhachHang;
    DEALLOCATE cur_KhachHang;

    PRINT N'--- HOÀN TẤT PHÂN HẠNG KHÁCH HÀNG ---';
END;
GO


-- ----------------------------------------------------------------------------
-- CURSOR 3: sp_Cursor_QuetKiemTraYeuCauHoanTien
-- Nhiệm vụ:
--   Duyệt qua danh sách các yêu cầu hoàn tiền (bảng refunds) đã hết 72 giờ giữ tiền (due_at <= NOW).
--   In báo cáo và danh sách các khoản cần được shop giải ngân.
-- ----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE dbo.sp_Cursor_QuetKiemTraYeuCauHoanTien
AS
BEGIN
    SET NOCOUNT ON;

    PRINT N'--- BẮT ĐẦU DUYỆT CÁC YÊU CẦU HOÀN TIỀN ĐÃ ĐỦ ĐIỀU KIỆN 72H (CURSOR) ---';

    DECLARE @RefundId INT;
    DECLARE @OrderCode VARCHAR(12);
    DECLARE @Amount BIGINT;
    DECLARE @Reason NVARCHAR(255);
    DECLARE @DueAt DATETIME2;
    DECLARE @Count INT = 0;

    DECLARE cur_HoanTien CURSOR FOR
        SELECT 
            r.id, 
            o.code, 
            r.amount, 
            r.reason, 
            r.due_at
        FROM dbo.refunds r
        JOIN dbo.orders o ON r.order_id = o.id
        WHERE r.status = 'scheduled' AND r.due_at <= SYSUTCDATETIME()
        ORDER BY r.due_at ASC;

    OPEN cur_HoanTien;

    FETCH NEXT FROM cur_HoanTien INTO @RefundId, @OrderCode, @Amount, @Reason, @DueAt;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @Count = @Count + 1;
        PRINT FORMATMESSAGE(N'Yêu cầu #%d | Đơn hàng: %s | Số tiền: %s VNĐ | Lý do: %s | Hạn giữ tiền: %s (ĐÃ ĐỦ ĐIỀU KIỆN HOÀN)',
            @RefundId, @OrderCode, CAST(@Amount / 100 AS VARCHAR(20)), COALESCE(@Reason, N'Không ghi'), CONVERT(VARCHAR(30), @DueAt, 120));

        FETCH NEXT FROM cur_HoanTien INTO @RefundId, @OrderCode, @Amount, @Reason, @DueAt;
    END

    CLOSE cur_HoanTien;
    DEALLOCATE cur_HoanTien;

    PRINT FORMATMESSAGE(N'--- TỔNG CỘNG: Có %d yêu cầu hoàn tiền cần xác nhận giải ngân ---', @Count);
END;
GO

PRINT N'=== HOÀN TẤT CÀI ĐẶT CÁC THỦ TỤC DÙNG CURSOR ===';
GO

-- ============================================================================
-- ELECTROHUB - HỆ QUẢN TRỊ CƠ SỞ DỮ LIỆU (SQL SERVER 2022)
-- File: master_setup.sql
-- Mục đích: Hướng dẫn và thứ tự chạy toàn bộ hệ thống cơ sở dữ liệu
-- ============================================================================

/*
HƯỚNG DẪN THỰC THI TRÊN SQL SERVER MANAGEMENT STUDIO (SSMS) HOẶC AZURE DATA STUDIO:
--------------------------------------------------------------------------------
Bạn có thể mở từng file trong thư mục `sql/` theo đúng thứ tự đánh số sau:

  1. sql/01_ddl_tables.sql
     -> Tạo cơ sở dữ liệu ElectroHub và 10 bảng nghiệp vụ.

  2. sql/02_rules_defaults.sql
     -> Tạo các Rule toàn vẹn (Giá không âm, Số lượng 1..99, Trạng thái đơn)
        và Default dùng sp_bindrule, sp_bindefault theo slide bài học.

  3. sql/03_triggers.sql
     -> Cài đặt các Trigger nghiệp vụ:
        - trg_KiemTraVaTruTonKho (Kiểm tra và trừ tồn kho khi tạo đơn)
        - trg_HoanKhoKhiHuyDonHang (Hoàn trả tồn kho và voucher khi hủy đơn)
        - trg_ChongSuaXoaDonHangDaDong (Chống sửa xóa đơn hàng đã đóng)
        - trg_DongBoThanhToanKhiHoanTien (Tự cập nhật trạng thái payment khi hoàn tiền)

  4. sql/04_stored_procedures.sql
     -> Cài đặt các Stored Procedures nghiệp vụ:
        - sp_ThemSanPham (Thêm sản phẩm mới kèm kiểm tra tính duy nhất)
        - sp_TaoDonHangTuGioHang (Quy trình tạo đơn từ giỏ hàng dùng Transaction)
        - sp_CapNhatTrangThaiDonHang (Chuyển trạng thái đơn hàng theo luồng)
        - sp_HuyDonHangVaYeuCauHoanTien (Hủy đơn và giữ tiền 72h)
        - sp_BaoCaoDoanhThu (Thống kê đơn hàng và doanh thu)

  5. sql/05_cursors.sql
     -> Cài đặt các thủ tục sử dụng Con trỏ (CURSOR) duyệt dòng:
        - sp_Cursor_XuLyDonHangPendingQuaHan (Quét hủy đơn hàng quá hạn)
        - sp_Cursor_PhanHangVaTangVoucherKhachHang (Duyệt tính điểm và tặng voucher VIP)
        - sp_Cursor_QuetKiemTraYeuCauHoanTien (Duyệt các khoản hoàn tiền đủ hạn 72h)

  6. sql/06_views_and_functions.sql
     -> Cài đặt Views và Functions (UDF):
        - fn_TinhTongTienDonHang (Hàm vô hướng tính tổng tiền VAT)
        - fn_KiemTraVoucherHopLe (Hàm kiểm tra voucher)
        - fn_LichSuDonHangUser (Hàm trả về bảng lịch sử đơn)
        - v_ChiTietDonHangTongHop, v_ThongKeSanPhamVaDoanhSo, v_BaoCaoDoanhThuTheoThang

  7. sql/07_transactions_concurrency.sql
     -> Kịch bản thực hành Concurrency Control, Lock Hints, Savepoints và Isolation Levels.

  8. sql/08_seed_data.sql
     -> Nạp bộ dữ liệu mẫu linh kiện điện tử để test ngay các đối tượng trên.
*/

PRINT N'Vui lòng mở và thực thi từng file theo thứ tự từ 01 đến 08 trong thư mục sql/ hoặc xem file sql/README.md để kiểm thử chi tiết.';
GO

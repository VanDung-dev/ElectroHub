# Definition of Done & Nghiệm Thu — ElectroHub

[← Trang bắt đầu / Kế hoạch nhóm](README.md) · [Tra cứu theo công việc](README.md#lookup) · [README chính](../README.md)

Tài liệu quy định tiêu chuẩn hoàn thành (Definition of Done - DoD) của từng Task, API, Page và bảng nghiệm thu MVP thực tế của toàn dự án ElectroHub.

---

<a id="task"></a>

## 1. Tiêu chuẩn Done của 1 Task Kỹ thuật

* [x] **Vùng sở hữu**: Code đúng phạm vi domain được phân công (Dũng P1: Nền tảng/DB/Auth; Giàu P2: Catalog; Hưng P3: Sales; Gấm P4: UI).
* [x] **Kiểm thử**: Backend có unit/integration test (`pytest`) tương ứng; hiển thị chuẩn trên tài liệu `/docs`.
* [x] **Kiểm tra linter**: Đạt chuẩn `ruff check .` và `ruff format --check .`.
* [x] **Bảo mật**: Không hardcode secret, mật khẩu hay cổng trong code; cấu hình qua `.env`.
* [x] **Đóng gói**: Chạy ổn định trên Docker Compose (`docker compose up -d --build`).

---

<a id="api"></a>

## 2. Tiêu chuẩn Done của 1 API Endpoint

* [x] Đường dẫn chuẩn RESTful: `/api/v1/...`, danh sách trả về định dạng `{ items, total, page, page_size }`.
* [x] Định dạng lỗi chuẩn hóa duy nhất: `{ "detail": "Thông báo lỗi tiếng Việt" }`.
* [x] Đầy đủ các test case: Happy path (thành công) và Error path (hết hàng, sai quyền, voucher hết hạn/không hợp lệ).
* [x] Bảo vệ an toàn: Yêu cầu CSRF token đối với mọi thao tác ghi (POST/PUT/PATCH/DELETE).

---

<a id="page"></a>

## 3. Tiêu chuẩn Done của 1 Giao diện (Page)

* [x] Kế thừa layout chuẩn `base.html`, gọi static files qua `url_for('static', path='...')`.
* [x] Kết nối dữ liệu thật từ backend (Server-Side Rendering với Jinja2 hoặc Client-Side fetch qua `api.js`).
* [x] Có đầy đủ trạng thái: Loading, Dữ liệu trống (Empty), và Báo lỗi trực quan (Error).
* [x] Responsive mượt mà trên các kích thước màn hình: Mobile (360px), Tablet (768px), Desktop (1024px+).

---

<a id="mvp"></a>

## 4. Bảng Nghiệm Thu MVP Thực Tế của Dự Án (Hiện trạng: 100% Hoàn Thành)

Dưới đây là bảng đối chiếu nghiệm thu thực tế của toàn bộ hệ thống ElectroHub:

| Hạng mục nghiệm thu MVP | Người phụ trách | Trạng thái | Bằng chứng kiểm chứng thực tế |
| :--- | :--- | :--- | :--- |
| **1. Auth & Phân quyền RBAC** | Dũng P1 & Gấm P4 | **ĐÃ HOÀN THÀNH** | Đăng ký, đăng nhập JWT qua HttpOnly cookie, phân quyền 3 cấp (Customer, Staff, Manager), tự tạo admin qua CLI, 3 tài khoản demo sẵn có. |
| **2. Quản trị Sản phẩm & Catalog** | Giàu P2 & Gấm P4 | **ĐÃ HOÀN THÀNH** | CRUD sản phẩm, danh mục, upload/quản lý ảnh, tìm kiếm theo từ khóa, lọc theo khoảng giá và thương hiệu, seed dữ liệu mẫu >50 sản phẩm. |
| **3. Giỏ hàng & Luồng Đặt hàng** | Hưng P3 & Gấm P4 | **ĐÃ HOÀN THÀNH** | Thêm/sửa/xóa giỏ hàng, áp mã giảm giá `WELCOME10`, trừ tồn kho an toàn trong giao dịch nguyên tử (Atomic Transaction), tra cứu đơn hàng cá nhân. |
| **4. Thanh toán Đa kênh (Mock & Sandbox)** | Hưng P3 & Dũng P1 | **ĐÃ HOÀN THÀNH** | Chế độ Mock mô phỏng thành công/thất bại tại `/payments/{code}`; kết nối Sandbox thật với **VNPAY** (ATM NCB) và **PayPal** (VISA quốc tế), chính sách hoàn tiền an toàn giữ chỗ 72h. |
| **5. Email Marketing & Mailpit** | Dũng P1 & Gấm P4 | **ĐÃ HOÀN THÀNH** | Tự động gửi email chào mừng kèm voucher khi đăng ký nhận tin; admin gửi chiến dịch marketing hàng loạt qua background tasks; kiểm tra trực quan qua hộp thư Mailpit (`localhost:8025`). |
| **6. Cơ sở dữ liệu T-SQL Chuyên sâu** | Dũng P1 | **ĐÃ HOÀN THÀNH** | Đầy đủ 8 file SQL: 4 Triggers, 11 Stored Procedures & Functions, 3 Cursors, 5 Rules & Defaults, demo Transactions & Lock Hints; test tự động qua `sql/test_all.sql` pass 100%. |
| **7. Kiến trúc Docker Dual-DB** | Dũng P1 | **ĐÃ HOÀN THÀNH** | Khởi chạy song song DB Web App (1433) và DB Test môn học (1434); kết nối trực tiếp từ SSMS trên máy ảo Windows Parallels. |
| **8. Bộ kiểm thử tự động (Test Suite)** | Cả nhóm | **ĐÃ HOÀN THÀNH** | **106/106 unit & integration tests passed 100%**; linter đạt chuẩn tuyệt đối qua `ruff check` và `ruff format`. |

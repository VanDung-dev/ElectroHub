# P3 — Lê Nhật Hưng

[← Chọn thành viên / tra cứu hướng dẫn](../README.md)

**Vai trò:** Sales — giỏ hàng, đơn hàng, thanh toán, vận chuyển và voucher.

<a id="scope"></a>

## Phần Hưng phụ trách

Cart, orders/order_items, payments, shipments, vouchers, tra cứu và lịch sử đơn; nghiệp vụ quản trị trạng thái đơn.

Vùng file: `app/models/{cart,order,payment,voucher}.py`, `app/routers/{cart,orders,admin_orders}.py`, `app/schemas/{cart,order}.py`, `app/services/order_service.py` và `tests/test_orders.py`. Schema bổ sung theo domain sales cần thống nhất với Dũng.

<a id="tasks"></a>

## Nhiệm vụ và hướng dẫn

| Việc cần làm | Hướng dẫn áp dụng | Kết quả cần bàn giao |
| --- | --- | --- |
| Thêm/sửa/xóa cart item, tính tiền và áp voucher | [API sales](../API-DESIGN.md#sales), [backend](../CODING-CONVENTION.md#python), [ERD](../DB-MIGRATION.md#erd) | API cart và số tiền để Gấm hiển thị |
| Checkout: tạo order, thanh toán COD + giả lập, trừ kho | [Luồng checkout](../HSHOP-ANALYSIS.md#checkout), [API sales](../API-DESIGN.md#sales), [transaction](../DB-MIGRATION.md#data-safety) | Tạo đơn, trừ stock/voucher trong transaction; tính đúng tiền, tránh race condition |
| Tra cứu đơn, lịch sử user, admin cập nhật trạng thái | [Contract sales](../API-DESIGN.md#sales), [tracking](../HSHOP-ANALYSIS.md#checkout), [quyền admin](../API-DESIGN.md#implementation) | API tracking/history và đổi trạng thái đúng quyền |
| Áp dụng chính sách vận chuyển/bảo hành vào logic giá/ship | [Yêu cầu checkout](../HSHOP-ANALYSIS.md#checkout), [nội dung chính sách](../HSHOP-ANALYSIS.md#content) | Quy tắc phí và thông tin khớp nội dung Gấm hiển thị |
| Test API và luồng cart → checkout → payment → tracking | [Done của API](../DEFINITION-OF-DONE.md#api), [demo Docker](../DEFINITION-OF-DONE.md#monitoring) | Test happy/error, Swagger, ví dụ HTTP và flow E2E bằng Docker |

Tên phương thức thanh toán giả lập và vòng đời order/payment còn cần thống nhất; theo [danh sách cần chốt](../API-DESIGN.md#pending-decisions), không tự chọn khác với contract UI/DB.

<a id="coordination"></a>

## Phối hợp với ai, ở đâu?

| Khi cần… | Đến đúng phần của người đó | Hưng bàn giao / đề xuất |
| --- | --- | --- |
| Thêm schema/migration, quyền user/admin và chốt contract sales | [Dũng — DB/auth](P1-DUNG.md#tasks) | Đề xuất schema và quy tắc trạng thái, quyền truy cập, transaction |
| Lấy sản phẩm, giá, stock hoặc cập nhật tồn kho | [Giàu — phối hợp catalog](P2-GIAU.md#coordination) | Thống nhất field dùng trong cart/order và điểm cập nhật stock; tránh sửa chồng model/service |
| UI cart/checkout/tracking, admin đơn, nội dung phí ship | [Gấm — nhiệm vụ UI](P4-GAM.md#tasks) | Request/response mẫu, tổng tiền/phí, trạng thái và lỗi để UI xử lý |

Gấm sở hữu giao diện admin đơn; Hưng sở hữu API/nghiệp vụ admin đơn. Không sửa CSS; thay đổi chéo vùng theo [quy trình chung](../README.md#ownership).

<a id="handoff"></a>

## Trước khi bàn giao / mở PR

* Flow `cart → checkout → payment → tracking` chạy E2E bằng Docker; đối chiếu [checklist checkout](../HSHOP-ANALYSIS.md#checkout).
* Có kiểm tra tính tiền, stock và voucher theo [an toàn dữ liệu](../DB-MIGRATION.md#data-safety); Gấm xác nhận gọi được API.
* Đạt [Done của API](../DEFINITION-OF-DONE.md#api) và [Done của task](../DEFINITION-OF-DONE.md#task); mở PR theo [quy trình chung](../GIT-WORKFLOW.md#pull-requests).

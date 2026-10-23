# ElectroHub — Công việc của nhóm

**Bắt đầu ở đây:** chọn giai đoạn đang làm, tìm dòng tên mình, rồi tạo ticket cho từng task trong bảng Kanban của nhóm. Mỗi task có một người phụ trách; phối hợp chỉ ghi ở task thực sự cần bàn giao.

<a id="members"></a>
<a id="ownership"></a>

## Thành viên và phần việc

| Thành viên | Phần việc | Chi tiết domain |
| --- | --- | --- |
| **P1 — Nguyễn Lê Văn Dũng** | Nền tảng, auth, database/migration, Docker, tích hợp và review | [Task của Dũng](members/P1-DUNG.md) |
| **P2 — Nguyễn Hữu Giàu** | Catalog: category, brand, product, search, wishlist, compare, seed | [Task của Giàu](members/P2-GIAU.md) |
| **P3 — Lê Nhật Hưng** | Sales: cart, order, payment, voucher, shipping, tracking | [Task của Hưng](members/P3-HUNG.md) |
| **P4 — Phạm Thị Hồng Gấm** | Storefront/admin UI, nội dung, tích hợp frontend | [Task của Gấm](members/P4-GAM.md) |

Stack chung: Python 3.13 + FastAPI, Jinja2/HTML/CSS/JS thuần, SQL Server 2022. Quy tắc nhánh, commit, PR và review nằm trong [GIT-WORKFLOW.md](GIT-WORKFLOW.md). Hướng dẫn API, DB và code được liên kết từ trang thành viên khi task cần.

## Cách dùng kế hoạch

- Mỗi dòng trong giai đoạn là task khung; người phụ trách chuyển thành ticket riêng trên Kanban và cập nhật trạng thái/deadline ở đó.
- `[Tự làm]` có thể bắt đầu ngay trong phạm vi của người phụ trách.
- `[Phối hợp: ...]` ghi người cần thống nhất/nhận bàn giao. Task vẫn có một owner chịu trách nhiệm chốt kết quả.
- Khi đang chờ đầu vào, làm phần độc lập/mock trước; ghi rõ đầu vào đang chờ và điều kiện để tiếp tục.
- Chuyển giai đoạn khi đầu ra ở cột “Bàn giao / điều kiện qua giai đoạn” đã được xác nhận. Ngày lịch và trạng thái không cố định trong tài liệu này.

## Giai đoạn 1 — Nền tảng và hợp đồng

**Mục tiêu:** thống nhất các hợp đồng trước khi các domain phụ thuộc lẫn nhau; tạo khung để frontend và backend cùng bắt đầu.

| Owner | Task tự làm | Phối hợp và bàn giao |
| --- | --- | --- |
| **Dũng P1** | Khung FastAPI, config/logging, cách chạy local/Docker. | Duyệt ERD/API với Giàu và Hưng; chốt route HTML/template với Gấm; chốt nội dung blog tĩnh hay qua API và giao owner nếu cần API. Bàn giao app khởi động được, contract duyệt và cách tạo admin ban đầu. |
| **Giàu P2** | Chốt field product/category/brand/filter và kế hoạch seed. | Gửi schema/API và quy định upload ảnh (format, kích thước, lưu trữ) cho Dũng duyệt; chốt giá/tồn kho với Hưng, payload PLP/PDP với Gấm. |
| **Hưng P3** | Mô tả luồng cart → checkout → order → tracking và trạng thái. | Gửi ERD/API cho Dũng; thống nhất giá/tồn kho với Giàu, dữ liệu checkout/tracking với Gấm. |
| **Gấm P4** | Dựng base layout, CSS variables, `api.js` và UI mock. | Chốt route/page shell với Dũng, payload mock với Giàu và Hưng. |

**Qua giai đoạn khi:** Dũng duyệt ERD/API; chốt route HTML, cách tạo admin và cách lưu/phục vụ blog; các domain thống nhất field giá/tồn kho và thanh toán giả lập; Gấm có payload mock khớp contract.

## Giai đoạn 2 — Auth, catalog và các trang đầu

**Mục tiêu:** hoàn tất nền tảng đăng nhập và catalog; có thể duyệt sản phẩm trên giao diện và bắt đầu giỏ hàng.

| Owner | Task tự làm | Phối hợp và bàn giao |
| --- | --- | --- |
| **Dũng P1** | Hoàn thiện app, DB access, auth và tạo admin ban đầu. | Duyệt migration với Giàu/Hưng; đăng ký route/template với Gấm. Bàn giao auth, migration và trang được phục vụ. |
| **Giàu P2** | CRUD category/brand/product, search/filter/sort/page, upload ảnh. | Duyệt migration với Dũng; nối API với Gấm. Bàn giao catalog đủ [PLP/PDP](HSHOP-ANALYSIS.md#plp). |
| **Hưng P3** | Cart thêm/sửa/xóa và tính tổng theo contract. | Lấy giá/stock từ Giàu; migration/auth với Dũng; nối cart với Gấm. Bàn giao total nhất quán với product. |
| **Gấm P4** | Homepage và khung PLP/PDP bằng mock. | Nối catalog API với Giàu; đăng ký route/template với Dũng. Bàn giao trang hiển thị dữ liệu thật và có loading/empty/error. |

**Qua giai đoạn khi:** auth và catalog chạy; Gấm xác nhận PLP/PDP dùng API thật; Hưng và Giàu xác nhận hợp đồng giá/tồn kho để checkout.

## Giai đoạn 3 — Đơn hàng và luồng mua

**Mục tiêu:** hoàn tất checkout, payment giả lập, tracking và giao diện bán hàng xuyên suốt.

| Owner | Task tự làm | Phối hợp và bàn giao |
| --- | --- | --- |
| **Dũng P1** | Hoàn thiện quyền admin và nền tảng tích hợp. | Rà soát transaction với Hưng; ghép router và chạy Docker với cả nhóm. |
| **Giàu P2** | Hoàn thiện catalog, seed ≥50 sản phẩm và test domain. | Thống nhất stock với Hưng; hoàn tất PLP/PDP/wishlist/compare với Gấm. |
| **Hưng P3** | Voucher, order, trừ stock trong transaction, payment mock, tracking và trạng thái admin. | Quyền/DB với Dũng; stock với Giàu; contract/UI với Gấm. Bàn giao luồng cart → checkout → payment → tracking E2E. |
| **Gấm P4** | Login/register, wishlist/compare và admin UI theo API. | Cart/checkout/tracking với Hưng; catalog với Giàu; auth/route với Dũng. |

**Qua giai đoạn khi:** một luồng mua hàng hoàn chỉnh chạy trên Docker; admin cập nhật trạng thái; người dùng tra cứu đơn theo contract đã thống nhất.

## Giai đoạn 4 — Hoàn thiện và nghiệm thu

**Mục tiêu:** kiểm tra chất lượng domain, giao diện và bản dựng tổng thể trước demo.

| Owner | Task tự làm | Phối hợp và bàn giao |
| --- | --- | --- |
| **Dũng P1** | Kiểm tra local/Docker, quyền, config, hướng dẫn chạy máy sạch. | Điều phối blocker và demo với cả nhóm; bàn giao build/test trên máy sạch. |
| **Giàu P2** | Test filter/sort/ảnh/seed và lỗi catalog. | Rà soát PLP/PDP mobile với Gấm; bàn giao seed/test lặp lại được. |
| **Hưng P3** | Test tính tiền, voucher, hủy đơn, tồn kho đồng thời và lỗi checkout. | Migration/transaction với Dũng; stock với Giàu; lỗi/trạng thái UI với Gấm. |
| **Gấm P4** | Hoàn tất chính sách/blog/review; test responsive, ảnh, console và loading/empty/error. | Rà soát dữ liệu với Giàu/Hưng, route/auth với Dũng; bàn giao page đạt [DoD](DEFINITION-OF-DONE.md#page). |

**Hoàn tất MVP khi:** cả nhóm xác nhận [checklist nghiệm thu](DEFINITION-OF-DONE.md#mvp) và luồng chính chạy trên máy sạch.

<a id="lookup"></a>

## Tài liệu chi tiết theo task

Mở trang thành viên trước, chỉ đọc phần liên quan tới task:

- [Dũng P1](members/P1-DUNG.md): nền tảng, auth, DB và điều phối.
- [Giàu P2](members/P2-GIAU.md): catalog, PLP/PDP, seed.
- [Hưng P3](members/P3-HUNG.md): cart, checkout, order, payment.
- [Gấm P4](members/P4-GAM.md): pages, UI và tích hợp API.
- [Git workflow chung](GIT-WORKFLOW.md): nhánh, commit, PR, phối hợp sửa chéo.

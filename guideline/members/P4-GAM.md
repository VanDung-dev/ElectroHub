# P4 — Phạm Thị Hồng Gấm

[← Chọn thành viên / tra cứu hướng dẫn](../README.md)

**Vai trò:** Storefront + Admin UI — HTML/CSS/JS thuần, trang nội dung và tích hợp API.

<a id="scope"></a>

## Phần Gấm phụ trách

Toàn bộ `app/templates/`, `app/static/`; homepage, PLP (danh sách sản phẩm), PDP (chi tiết sản phẩm), cart/checkout/tracking, login/register, admin UI, chính sách, blog/review và liên hệ.

File chính: `templates/base.html`, các trang trong `templates/{product,cart,auth,admin,blog}/`, `static/css/`, `static/js/` và ảnh trong `static/img/` (đều nằm trong `app/`). API và nghiệp vụ backend thuộc Dũng/Giàu/Hưng theo domain.

<a id="tasks"></a>

## Nhiệm vụ và hướng dẫn

| Việc cần làm | Hướng dẫn áp dụng | Kết quả cần bàn giao |
| --- | --- | --- |
| Layout dùng chung: header/footer/nav/category menu, base CSS/JS và `api.js` | [Jinja/HTML](../CODING-CONVENTION.md#html), [CSS](../CODING-CONVENTION.md#css), [JS](../CODING-CONVENTION.md#javascript) | `base.html`, `base.css`, `base.js`, fetch wrapper dùng chung |
| Homepage, chính sách, liên hệ, blog/review | [Sitemap](../HSHOP-ANALYSIS.md#sitemap), [content/trust](../HSHOP-ANALYSIS.md#content), [điều cần tránh](../HSHOP-ANALYSIS.md#anti-patterns) | Trang có banner/trust/footer và nội dung theo checklist |
| PLP/PDP, wishlist/compare | [Checklist PLP](../HSHOP-ANALYSIS.md#plp), [PDP](../HSHOP-ANALYSIS.md#pdp), [API catalog](../API-DESIGN.md#catalog) | UI filter/sort/paginate, gallery/specs/CTA và dữ liệu sản phẩm đầy đủ |
| Cart, checkout, payment, tra cứu đơn | [Luồng checkout](../HSHOP-ANALYSIS.md#checkout), [API sales](../API-DESIGN.md#sales) | UI khớp tiền/phí/trạng thái do backend trả về |
| Login/register và trạng thái đăng nhập | [API auth](../API-DESIGN.md#auth), [form/CSRF](../CODING-CONVENTION.md#html) | Dùng cookie HttpOnly do backend set; nối CSRF theo hướng dẫn Dũng |
| Admin sản phẩm/tồn kho/đơn hàng | [API catalog](../API-DESIGN.md#catalog), [API sales](../API-DESIGN.md#sales) | Admin UI dùng chung API của Giàu/Hưng; backend kiểm tra quyền |
| Responsive và trạng thái loading/empty/error | [CSS mobile-first](../CODING-CONVENTION.md#css), [Done của page](../DEFINITION-OF-DONE.md#page) | Không lỗi console, chạy không cần Node, kiểm tra 360/768/1024px |

Làm trước bằng mock JSON theo contract đã thống nhất với người phụ trách API. Khi API sẵn sàng, nối API thật trước khi nghiệm thu page. Giữ BEM/CSS variables; thư viện ngoài cần Dũng duyệt.

<a id="coordination"></a>

## Phối hợp với ai, ở đâu?

| Khi cần… | Đến đúng phần của người đó | Gấm cần nhận / xác nhận |
| --- | --- | --- |
| App phục vụ template/static, auth/cookie/CSRF, lỗi chung | [Dũng — nhiệm vụ nền tảng](P1-DUNG.md#tasks) | Cách gắn page vào app, auth contract, cơ chế CSRF và format lỗi |
| Dữ liệu category/brand/product, filter, wishlist/compare, admin sản phẩm | [Giàu — nhiệm vụ catalog](P2-GIAU.md#tasks) | Response mẫu và cách gọi từng API trước khi tạo mock/nối dữ liệu |
| Cart/order/payment/voucher/tracking và admin đơn | [Hưng — nhiệm vụ sales](P3-HUNG.md#tasks) | Request checkout, tiền/phí, trạng thái, lỗi và quyền truy cập |

Thiếu field hoặc endpoint thì báo đúng chủ API, không tự đổi contract hay sửa backend để khớp mock. Chủ API cập nhật tài liệu khi thay đổi; Gấm xác nhận tích hợp bằng `api.js`. Yêu cầu chưa thống nhất được ghi tại [điểm cần chốt](../API-DESIGN.md#pending-decisions).

<a id="handoff"></a>

## Trước khi bàn giao / mở PR

* Mọi page extends `base.html`, dùng `url_for('static')`; không CSS/JS inline, ảnh có alt/lazy/width/height.
* Không lỗi console; responsive 360/768/1024px; có loading/empty/error và đã nối API thật theo [Done của page](../DEFINITION-OF-DONE.md#page).
* PLP/PDP/checkout đủ checklist liên kết ở từng nhiệm vụ; content theo [yêu cầu HSHOP](../HSHOP-ANALYSIS.md#content).
* PR có ảnh UI, ghi API đã nối và cách kiểm tra; xem [quy trình PR](../GIT-WORKFLOW.md#pull-requests) và [Done của task](../DEFINITION-OF-DONE.md#task).

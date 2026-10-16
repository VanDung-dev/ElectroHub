# P2 — Nguyễn Hữu Giàu

[← Chọn thành viên / tra cứu hướng dẫn](../README.md)

**Vai trò:** Catalog — dữ liệu và API sản phẩm, tìm kiếm, wishlist, compare.

<a id="scope"></a>

## Phần Giàu phụ trách

Category, brand, product, ảnh sản phẩm, specs, search/filter/sort/paginate, wishlist, compare và seed sản phẩm.

Vùng file: `app/models/{category,brand,product,product_image}.py`, `app/routers/{categories,brands,products}.py`, `app/schemas/product.py`, `app/services/product_service.py`, `app/seeds/` và `tests/test_products.py`. File bổ sung cho wishlist/compare vẫn thuộc domain catalog; thống nhất schema với Dũng trước.

<a id="tasks"></a>

## Nhiệm vụ và hướng dẫn

| Việc cần làm | Hướng dẫn áp dụng | Kết quả cần bàn giao |
| --- | --- | --- |
| CRUD category đa cấp, brand, product và upload ảnh | [API catalog](../API-DESIGN.md#catalog), [backend](../CODING-CONVENTION.md#python), [ERD](../DB-MIGRATION.md#erd) | API/schema và dữ liệu để Gấm dựng trang sản phẩm/admin |
| List/detail/search/filter/sort/paginate | [Yêu cầu PLP](../HSHOP-ANALYSIS.md#plp), [PDP](../HSHOP-ANALYSIS.md#pdp), [contract catalog](../API-DESIGN.md#catalog) | Dữ liệu đủ checklist; list theo `{items,total,page,page_size}` |
| Wishlist và so sánh sản phẩm | [Scope MVP](../DEFINITION-OF-DONE.md#mvp), [API catalog](../API-DESIGN.md#catalog) | Thống nhất contract và cách lưu với Dũng; bàn giao dữ liệu cho Gấm nối UI |
| Seed 50–100 sản phẩm theo nhóm Arduino, SBC, Sensor, RF, Robot DIY | [Seed chạy lại được](../DB-MIGRATION.md#migrations), [quy tắc nguồn ảnh/nội dung](../HSHOP-ANALYSIS.md#anti-patterns) | Seed tách khỏi migration, có thể chạy lại |
| Test API, tài liệu Swagger, ví dụ HTTP | [Quy định implement](../API-DESIGN.md#implementation), [Done của API](../DEFINITION-OF-DONE.md#api) | Có happy path và trường hợp lỗi, ví dụ trong `test_main.http` |

<a id="coordination"></a>

## Phối hợp với ai, ở đâu?

| Khi cần… | Đến đúng phần của người đó | Giàu bàn giao / đề xuất |
| --- | --- | --- |
| Thêm bảng/field/index, sửa migration, auth hoặc admin guard | [Dũng — DB và nền tảng](P1-DUNG.md#tasks) | Đề xuất schema qua issue; thống nhất ERD/contract trước khi triển khai |
| Hiển thị PLP/PDP, wishlist/compare, admin sản phẩm | [Gấm — nhiệm vụ UI](P4-GAM.md#tasks) | Request/response mẫu, field ảnh/giá/stock/specs và cách gọi API |
| Dùng giá/tồn kho trong cart và checkout | [Hưng — nhiệm vụ sales](P3-HUNG.md#tasks) | Thống nhất dữ liệu sản phẩm, giá áp dụng và cập nhật kho; transaction theo [quy định DB](../DB-MIGRATION.md#data-safety) |

Không sửa CSS; chỉ thêm `data-*` vào template khi cần. Thay đổi UI khác theo [ranh giới công việc](../README.md#ownership). Nếu contract chưa đủ hoặc mâu thuẫn checklist, xem [điểm cần chốt](../API-DESIGN.md#pending-decisions) và trao đổi với Dũng/Gấm trước.

<a id="handoff"></a>

## Trước khi bàn giao / mở PR

* CRUD chạy đầy đủ, filter đúng, seed chạy lại được; đủ dữ liệu theo [PLP](../HSHOP-ANALYSIS.md#plp) và [PDP](../HSHOP-ANALYSIS.md#pdp).
* Gấm xác nhận gọi được API bằng `api.js`; báo trước nếu đổi field required hoặc path.
* Đạt [Done của API](../DEFINITION-OF-DONE.md#api) và [Done của task](../DEFINITION-OF-DONE.md#task); mở PR theo [quy trình chung](../GIT-WORKFLOW.md#pull-requests).

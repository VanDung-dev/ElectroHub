# P1 — Nguyễn Lê Văn Dũng

[← Chọn thành viên / tra cứu hướng dẫn](../README.md)

**Vai trò:** Lead / Platform — core, auth, DB, DevOps và review tích hợp.

<a id="scope"></a>

## Phần Dũng phụ trách

`app/main.py`, `app/core/`, auth/users/RBAC, khung `app/models/`, ERD, `alembic/`, Docker/Compose, CI và `guideline/`. Dũng chủ trì schema chung; Giàu/Hưng phụ trách model nghiệp vụ theo domain sau khi thống nhất ERD.

Các file liên quan: `app/routers/auth.py`, `app/models/user.py`, `app/schemas/auth.py`, `tests/test_auth.py`, `Dockerfile`, `compose.yaml`, `docker/init.sql`, cấu hình dependency và `.env.example`.

<a id="tasks"></a>

## Nhiệm vụ và hướng dẫn

| Việc cần làm | Hướng dẫn áp dụng | Kết quả cần bàn giao |
| --- | --- | --- |
| Dựng app, config, logging, error chuẩn và dependency chung | [Python/FastAPI](../CODING-CONVENTION.md#python), [nguyên tắc API](../API-DESIGN.md#principles) | Khung app để các domain gắn router; phục vụ HTML và API đúng ranh giới |
| Register/login/logout/me, JWT HttpOnly cookie, role admin/customer | [Contract auth](../API-DESIGN.md#auth), [quy định API](../API-DESIGN.md#implementation) | API auth, dependency phân quyền, test và ví dụ Swagger |
| Cấp cơ chế CSRF cho frontend | [Form và CSRF](../CODING-CONVENTION.md#html) | Hướng dẫn sử dụng để Gấm nối form/UI |
| Chốt ERD, naming DB/API, duyệt schema và quản lý migration | [ERD](../DB-MIGRATION.md#erd), [migration](../DB-MIGRATION.md#migrations), [an toàn dữ liệu](../DB-MIGRATION.md#data-safety) | Schema chung và migration có upgrade/downgrade |
| Dựng Docker, môi trường và CI tối thiểu `ruff + pytest + docker compose up --build` | [Chạy môi trường](../../README.md), [nghiệm thu/demo](../DEFINITION-OF-DONE.md#monitoring) | Cách chạy lại trên máy khác; kiểm tra trước merge |
| Review mọi PR vào develop/main, theo dõi tiến độ, xử lý blocker | [Quy trình PR](../GIT-WORKFLOW.md#pull-requests), [giám sát](../DEFINITION-OF-DONE.md#monitoring) | Review theo chủ vùng, giải quyết xung đột kỹ thuật |

<a id="coordination"></a>

## Phối hợp với ai, ở đâu?

| Khi liên quan… | Đến đúng phần của người đó | Cần thống nhất |
| --- | --- | --- |
| Catalog | [Giàu — nhiệm vụ](P2-GIAU.md#tasks) | Schema sản phẩm/category/brand, API và seed |
| Checkout và dữ liệu sales | [Hưng — nhiệm vụ](P3-HUNG.md#tasks) | Schema cart/order/payment/voucher, transaction và quyền truy cập |
| Auth UI, layout và API dùng chung | [Gấm — phối hợp](P4-GAM.md#coordination) | Cookie/CSRF, `api.js`, cách phục vụ template/static, format lỗi |
| Các yêu cầu đang mâu thuẫn hoặc thiếu | [Danh sách cần chốt](../API-DESIGN.md#pending-decisions) | Chốt cùng người phụ trách domain rồi cập nhật tài liệu liên quan trước khi họ implement |

Giàu/Hưng đề xuất schema qua issue; Dũng duyệt trước khi code migration. Không thay đổi contract lặng lẽ khi Gấm đã dùng mock hoặc API cũ.

<a id="handoff"></a>

## Trước khi bàn giao / review

* Auth chạy bằng Docker, có test và ví dụ Swagger; đối chiếu [Done của API](../DEFINITION-OF-DONE.md#api).
* Migration có upgrade/downgrade và đã chạy thử theo [workflow migration](../DB-MIGRATION.md#migrations).
* Kiểm tra [Done của task](../DEFINITION-OF-DONE.md#task), [review checklist](../GIT-WORKFLOW.md#review) và [nghiệm thu MVP](../DEFINITION-OF-DONE.md#mvp).
* Không chạy `docker compose down -v` nếu chưa có đồng ý của cả nhóm; xem [an toàn dữ liệu](../DB-MIGRATION.md#data-safety).

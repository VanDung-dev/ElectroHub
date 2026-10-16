# Git workflow chung

[← Kế hoạch công việc theo giai đoạn](README.md) · [Chọn task của mình](README.md#members)

Tài liệu này chỉ quy định cách cả nhóm tạo nhánh, commit, phối hợp và review. Phạm vi/task domain nằm trong [README theo giai đoạn](README.md) và [trang thành viên](README.md#members).

<a id="branches"></a>

## Nhánh

```text
main                         # release/demo
└── develop                  # tích hợp hàng ngày
    └── feature/<domain>-<mo-ta>
hotfix/<mo-ta>                # tạo từ main cho sửa gấp
```

- Không code trực tiếp trên `main` hoặc `develop`.
- Tạo nhánh feature từ `develop`; giữ nhánh ngắn, một task hoặc một thay đổi liên quan mỗi nhánh.
- Quy ước domain: `core/auth` (Dũng), `product` (Giàu), `cart/order/payment` (Hưng), `ui/admin` (Gấm), `docs` (owner của task tài liệu).
- Ví dụ: `feature/product-search`, `feature/order-checkout`, `feature/ui-pdp`, `feature/core-jwt-cookie`.

<a id="tasks"></a>

## Tạo và cập nhật task

Mỗi task khung trong [README](README.md) thành một ticket riêng trên Kanban. Ticket ghi:

- Giai đoạn, một owner và đầu ra có thể kiểm tra.
- `[Tự làm]` hoặc `[Phối hợp: tên]`; với phối hợp ghi đầu vào, người nhận bàn giao và điều kiện bắt đầu/hoàn tất.
- Deadline và trạng thái được cập nhật ở Kanban, không chép ngày vào tài liệu tĩnh.
- Nếu đang chờ, owner ghi blocker và phần độc lập vẫn làm được.

Một nhánh làm một task. Task phối hợp vẫn có đúng một owner; người còn lại nhận ticket liên quan hoặc được ghi rõ là người bàn giao.

<a id="commits"></a>

## Commit

Dùng Conventional Commits, tiếng Việt hoặc tiếng Anh:

```text
feat(product): thêm lọc theo thương hiệu
fix(order): giữ tồn kho nhất quán khi checkout
chore(docker): sửa healthcheck SQL Server
docs(guideline): cập nhật task theo giai đoạn
```

Một commit chứa một thay đổi có mục đích rõ ràng. Không commit `.env`, `.venv/`, `logs/*`, `.DS_Store`, secret hoặc file build. Stage đúng file, không dùng `git add .` khi working tree có thay đổi của task khác.

<a id="coordination"></a>

## Phối hợp và quyền sở hữu

- Làm trong vùng của mình theo [task map](README.md#members).
- Trước khi sửa vùng người khác: tạo ticket, ghi lý do/đầu ra, xin chủ vùng đồng ý rồi mới code.
- P1 sở hữu thay đổi nền tảng và review chung. Khi PR sửa vùng domain khác, cần chủ vùng đó review cùng P1.
- Nếu contract API/DB ảnh hưởng người khác, cập nhật tài liệu liên quan và báo người nhận trước khi merge.
- Xung đột ERD/migration: dừng, báo Dũng; không xóa migration để né xung đột.
- Nếu `develop` lỗi, người tạo lỗi sửa hoặc revert trong ngày; ghi blocker trên ticket.

<a id="pull-requests"></a>

## Pull request

1. Cập nhật `develop`, tạo nhánh task và commit theo quy ước trên.
2. Trước PR feature, tích hợp `develop` mới nhất vào nhánh. Hotfix tạo từ `main`, mở PR vào `main`, rồi đưa thay đổi đã merge về `develop`.
3. Mở PR về `develop`. Ghi ticket, mục đích, file/domain, phần phối hợp, cách kiểm tra và ảnh UI khi có thay đổi giao diện.
4. Yêu cầu approve của Dũng; thêm approve của chủ vùng nếu PR chạm domain người khác.
5. Chỉ merge khi review và check dự án đều đạt; squash merge, xóa nhánh sau merge.
6. PR `develop → main` do Dũng mở khi nhóm chuẩn bị demo/release.

<a id="checks"></a>

## Kiểm tra trước PR

- Backend: chạy lint/format và pytest theo [quy ước Python](CODING-CONVENTION.md#python); API có ví dụ Swagger và test theo [quy định API](API-DESIGN.md#implementation).
- UI: làm theo [quy ước HTML/CSS/JS](CODING-CONVENTION.md#html) và tiêu chí page trong [Definition of Done](DEFINITION-OF-DONE.md#page).
- Thay đổi ảnh hưởng tích hợp hoặc cấu hình: chạy Docker theo [README chạy dự án](../README.md) và ghi kết quả trong PR.

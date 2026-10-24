# Đề xuất contract catalog — P2 Giàu

**Trạng thái:** Đề xuất của P2, chờ Dũng duyệt schema/API và chờ Hưng, Gấm xác nhận phần phối hợp. Đây chưa phải xác nhận qua giai đoạn 1.

## 1. Schema đề xuất

| Bảng | Field | Quy tắc |
| --- | --- | --- |
| `categories` | `id`, `parent_id`, `name`, `slug` | `parent_id` nullable để tạo cây; `name` và `slug` bắt buộc; `slug` unique; không cho phép category làm cha của chính nó hoặc hậu duệ của nó. |
| `brands` | `id`, `name`, `slug` | Bắt buộc; `slug` unique. |
| `products` | `id`, `slug`, `sku`, `name`, `category_id`, `brand_id`, `price`, `sale_price`, `stock`, `warranty`, `specs`, `description`, `is_active`, `created_at` | `slug` và `sku` unique; category/brand bắt buộc sau backfill migration; tiền VND kiểu int; `price >= 0`; `sale_price` null hoặc từ 0 đến `price`; `stock >= 0`; `specs` là object key-value; `is_active` mặc định true; `created_at` UTC. |
| `product_images` | `id`, `product_id`, `url`, `alt`, `sort` | Lưu URL tương đối dưới `/static/img/products/`, không lưu binary trong DB; xóa product thì xóa ảnh liên quan. |

`warranty` đề xuất là chuỗi ngắn để dùng được các giá trị như `Cơ bản`, `6 tháng`, `12 tháng`; `specs` là object JSON, ví dụ `{ "chip": "ESP32", "flash": "4MB" }`. Product mới phải có category và brand để PLP lọc theo taxonomy thống nhất; migration cần backfill dữ liệu sản phẩm cũ trước khi thêm ràng buộc bắt buộc. `stock` là số lượng có thể bán; cart không giữ hàng, checkout trừ kho nguyên tử khi `stock >= qty`, hủy đơn theo contract sales thì hoàn kho. Đề xuất `DELETE product` chuyển `is_active=false` để giữ lịch sử đơn; category/brand chỉ xóa khi không còn product tham chiếu.

## 2. Contract API đề xuất

```text
GET    /api/v1/categories                         -> cây category
POST   /api/v1/categories                         -> admin tạo
PUT    /api/v1/categories/{id}                   -> admin sửa
DELETE /api/v1/categories/{id}                   -> admin xóa nếu không có product/con
GET    /api/v1/brands                             -> danh sách brand
POST   /api/v1/brands                             -> admin tạo
PUT    /api/v1/brands/{id}                        -> admin sửa
DELETE /api/v1/brands/{id}                       -> admin xóa nếu không có product
GET    /api/v1/products                           -> PLP
GET    /api/v1/products/{slug}                    -> PDP
GET    /api/v1/admin/products                     -> admin quản lý cả active/inactive
POST   /api/v1/products                           -> admin tạo
PUT    /api/v1/products/{id}                      -> admin sửa
DELETE /api/v1/products/{id}                      -> admin xóa
POST   /api/v1/products/{id}/images               -> admin upload multipart file
DELETE /api/v1/products/{id}/images/{image_id}    -> admin xóa ảnh
```

Các request ghi cần admin và CSRF theo contract chung. `POST/PUT` category nhận `name`, `slug`, `parent_id`; brand nhận `name`, `slug`. Product tạo nhận `slug`, `sku`, `name`, `category_id`, `brand_id`, `price`, `sale_price`, `stock`, `warranty`, `specs`, `description`. Khi sửa product, `slug` và `sku` giữ nguyên để tránh đổi định danh/link; các field còn lại được cập nhật. `DELETE product` lưu trữ mềm (`is_active=false`), public PLP chỉ trả sản phẩm active; `GET /admin/products` chỉ admin mới gọi được và có thể lọc inactive để khôi phục sản phẩm. Xóa category/brand đang được tham chiếu trả `409`.

PLP nhận `category`, `brand`, `q`, `price_min`, `price_max`, `sort`, `page`, `page_size`. `category` và `brand` dùng slug; lọc category cha gồm cả sản phẩm thuộc category con. `q` tìm trong tên và SKU. `sort` nhận `name_asc`, `name_desc`, `newest`, `price_asc`, `price_desc`; mặc định `newest`. `page >= 1`, `1 <= page_size <= 24`, mặc định 20. Sort có khóa phụ `id` để phân trang ổn định khi giá/tên trùng. Tám khoảng giá đề xuất, không chồng lấn: `<10.000` (0–9.999), `10.000–49.999`, `50.000–99.999`, `100.000–199.999`, `200.000–499.999`, `500.000–999.999`, `1.000.000–1.999.999`, `>=2.000.000` VND; `price_min` và `price_max` đều inclusive, UI gửi biên tương ứng.

Giá hiển thị, lọc và sort đề xuất dùng giá áp dụng `sale_price` nếu có, còn lại `price`, nhưng response giữ cả hai field để UI gạch giá gốc. Cách này khớp với giá Hưng dùng để tính tiền; cần Hưng xác nhận trước khi đánh dấu contract thống nhất.

Response list giữ `{items, total, page, page_size}`. Mỗi item có `id`, `slug`, `sku`, `name`, `price`, `sale_price`, `stock`, `brand`, `image`; PDP bổ sung `category`, `warranty`, `specs`, `description`, `images` dạng `{url, alt, sort}`. Badge giảm giá tính từ hai field giá; badge “bán chạy” chỉ hiển thị nếu nhóm thống nhất nguồn dữ liệu bán chạy.

Payload mock tối thiểu để Gấm có thể dựng PLP/PDP trước khi API sẵn sàng:

```json
{
  "items": [{
    "id": 1, "slug": "esp32-devkit", "sku": "EH-001", "name": "ESP32 DevKit",
    "price": 185000, "sale_price": 165000, "stock": 42,
    "brand": "Espressif", "image": "/static/img/products/1/front.webp"
  }],
  "total": 1, "page": 1, "page_size": 20
}
```

PDP dùng chung các field trên và thêm `category`, `warranty`, `specs`, `description`, `images: [{url, alt, sort}]`. Category tree trả `{categories: [{id, name, slug, children: []}]}`; brand trả `{items: [{id, name, slug}]}`.

Validation đề xuất: lỗi dữ liệu `422`, không tìm thấy `404`, slug/SKU trùng hoặc xóa category/brand đang dùng `409`, thiếu quyền admin `403`. `price_min`/`price_max` phải không âm và min không lớn hơn max; `q` được trim và giới hạn 100 ký tự.

## 3. Quy định upload ảnh đề xuất

- Chỉ nhận JPEG, PNG và WebP; tối đa 2 MiB mỗi ảnh. Từ chối file không đúng định dạng hoặc vượt giới hạn trước khi ghi.
- `alt` bắt buộc, tối đa 200 ký tự; kiểm tra nội dung file thay vì tin phần mở rộng do client gửi.
- Lưu file dưới `app/static/img/products/{product_id}/` với tên file do server tạo; DB chỉ lưu URL tương đối `/static/img/products/{product_id}/{filename}`.
- Docker/local phải giữ thư mục upload qua lần restart/recreate container; không dựa vào thư mục tạm.
- Endpoint nhận một file mỗi request, `sort` xác định thứ tự; ảnh PLP dùng ảnh đầu tiên theo `sort`; PDP cần đủ 4–6 ảnh, mỗi ảnh có alt text. Chỉ dùng ảnh tự tạo hoặc ảnh có nguồn được phép; nén ảnh lớn hơn 2 MiB.

## 4. Kế hoạch seed

- Chuẩn bị 50 sản phẩm mẫu thuộc 5 nhóm `Arduino`, `SBC`, `Sensor`, `RF`, `Robot DIY`, phân bố trên nhiều brand.
- Mỗi product có SKU/slug ổn định, giá/tồn kho mẫu, warranty, specs, mô tả ngắn và 4–6 ảnh hợp lệ hoặc ảnh demo có ghi nguồn.
- Seed phải chạy lặp lại mà không xóa dữ liệu catalog đã chỉnh hoặc được đơn hàng tham chiếu; seed chỉ upsert dữ liệu demo theo slug/SKU đã định trước.

## 5. Xác nhận cần có để chốt giai đoạn 1

- **Dũng:** duyệt field/nullability, quan hệ/index, quy tắc xóa và cách migration.
- **Hưng:** xác nhận giá áp dụng dùng chung với cart/checkout và ý nghĩa/điểm cập nhật stock.
- **Gấm:** xác nhận payload PLP/PDP, ảnh/specs, badge và cách gọi API.

Sau các xác nhận, cập nhật lại contract chung ở [API-DESIGN.md](../API-DESIGN.md#catalog) và ERD do Dũng sở hữu ở [DB-MIGRATION.md](../DB-MIGRATION.md#erd).

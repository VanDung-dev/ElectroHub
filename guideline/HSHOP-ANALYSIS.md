# HSHOP Analysis → Chuẩn MVP ElectroHub

[← Trang bắt đầu / chọn thành viên](README.md) · [Tra cứu theo công việc](README.md#lookup)

[Giàu](members/P2-GIAU.md#tasks) đọc PLP/PDP; [Hưng](members/P3-HUNG.md#tasks) đọc checkout; [Gấm](members/P4-GAM.md#tasks) đọc các phần giao diện/content; [Dũng](members/P1-DUNG.md#coordination) đối chiếu DB/contract.

> Nguồn đối chiếu: `https://hshop.vn`, `/collections/all`, PDP `MKE-K06 STM32F103C8T6`, `/huong-dan-mua-hang`, `/chinh-sach-bao-hanh`.
> Stack hshop: Sapo/Bizweb server-render (`bizweb.dktcdn.net`), không phải SPA → khớp với stack FastAPI + Jinja + JS thuần của ElectroHub.
> Mục đích file này: khóa scope MVP, chống làm thiếu PDP/PLP/checkout, chống copy điểm yếu của hshop.

<a id="sitemap"></a>

## 1. Sitemap hshop (giữ lại cho MVP)

```text
/                              # homepage: slider 2 banner + 4 badge trust + block Sản phẩm mới
/collections/all                # PLP: filter giá + brand + sort
/products/{slug}                # PDP: gallery + brand/warranty/stock/SKU/price/qty/CTA/tabs/specs/related
/cart -> /checkout              # giỏ + checkout 5 bước
/account/login + /register      # auth
/san-pham-yeu-thich             # wishlist (0)
/so-sanh-san-pham               # compare (0)
/blogs/all + /{tag}             # DỰ ÁN: MICROBIT/ARDUINO/ESP32/RASPBERRY + REVIEW
/huong-dan-mua-hang             # 5 bước mua hàng
/chinh-sach-bao-hanh            # bảo hành 7 ngày quay video bóc hộp
/chinh-sach-doi-tra             # đổi trả
/chinh-sach-van-chuyen          # vận chuyển
/chinh-sach-bao-mat             # bảo mật
/lien-he                        # 269/20 Lý Thường Kiệt + giờ T2-T7 + hotline/Zalo/FB
```

<a id="plp"></a>

## 2. PLP chuẩn (Giàu P2 API + Gấm P4 UI)

* Filter bắt buộc: `Mức giá 8 khoảng (Dưới 10k … Trên 1tr)`, `Thương hiệu ~40 hãng`, `q search`, `category`.
* Sort bắt buộc: `Tên A-Z / Z-A / Hàng mới / Giá thấp-cao / Giá cao-thấp`.
* Card bắt buộc: `image(lazy) + name + price + sale_price gạch + badge(Bán chạy/Giảm %) + Thích + So sánh`.
* Phân trang `page/page_size (max 24)`, response `{items,total,page,page_size}`.
* **Cấm:** copy filter `Loại` rác của hshop (`Anten, 3 tháng, 1 năm, SHT…`). Chỉ dùng taxonomy sạch `Category(parent_id) + Brand`.

<a id="pdp"></a>

## 3. PDP chuẩn (Giàu P2 data + Gấm P4 UI) — checklist nghiệm thu

Lấy PDP `MKE-K06` làm mẫu, mọi PDP phải đủ:

* [ ] Gallery 4-6 ảnh + thumb, `alt + loading=lazy + width/height`.
* [ ] `brand (MakerEdu.vn), warranty (Cơ bản/6 tháng/12 tháng), stock (Còn hàng/Hết hàng), SKU (HS2420V → EH-XXX)`.
* [ ] `price INT + sale_price NULL, note thuế nếu có`.
* [ ] Stepper `-/+`, qty 1..99, 2 CTA `Thêm vào giỏ / Mua ngay`, nút `Zalo OA tư vấn`.
* [ ] 3 cam kết: `kiểm tra trước bán / quay video 7 ngày / báo lỗi 7 ngày`.
* [ ] Tabs: `Mô tả + Thông số kỹ thuật (bảng key-value) + Hướng dẫn mua hàng`.
* [ ] Link tài liệu ngoài (GitHub/datasheet).
* [ ] Block `Sản phẩm liên quan + Đã xem`.
* [ ] JSON-LD / meta SEO cơ bản (title = name + brand).

Thiếu 1 trong các field trên = chưa Done.

<a id="checkout"></a>

## 4. Cart → Checkout → Tracking (Hưng P3 API + Gấm P4 UI)

Flow hshop hiện tại (thủ công, cần tối ưu):
`Đăng ký → Chọn hàng → Check giỏ → Điền info → Nhận email + chờ gọi điện xác nhận → ra cửa hàng hoặc chuyển khoản sau xác nhận`.

ElectroHub MVP giữ 5 bước nhưng tự động hóa:

```text
POST /api/v1/cart/items {product_id, qty}
GET  /api/v1/cart                          # name, qty, price, total
POST /api/v1/orders                         # checkout 1 transaction: tạo order + trừ stock + sinh code EH-XXXX
GET  /api/v1/orders/{code}                  # tra cứu công khai bằng code + sđt
PATCH /api/v1/admin/orders/{code}           # pending→confirmed→shipping→done|cancelled
```

* Thanh toán MVP: `COD + CHUYEN_KHOAN_MOCK` (không tích hợp VNPay thật). Không bắt user chờ gọi điện mới được chuyển khoản.
* Địa chỉ nhận: `name/phone/address + ship_fee cố định W4`. Email thông báo để phase 2.
* Popup `Mua hàng thành công → Thanh toán ngay` của hshop giữ lại dưới dạng redirect `/cart/tracking.html?code=`.

<a id="content"></a>

## 5. Trust / Content (Gấm P4)

* Homepage giữ: slider 2 banner, 4 badge `Giao hàng nhanh / Tư vấn / Chất lượng / Thanh toán linh hoạt`.
* Footer giữ: 4 chính sách + hỗ trợ + tài khoản + block liên hệ `địa chỉ/giờ/hotline/Zalo/FB`.
* Bottom bar mobile 5 icon: `Trang chủ / Danh mục / Giỏ / Yêu thích / So sánh` — làm accessible button, không dùng `javascript:void(0)`.
* Blog tối thiểu 1 bài mỗi tag `ARDUINO/ESP32/RASPBERRY/MICROBIT` + 1 review mẫu.

<a id="anti-patterns"></a>

## 6. Anti-pattern của hshop (cấm mang sang)

* [ ] Menu render 2 lần trùng nhau → chỉ render 1 lần từ API `/categories`.
* [ ] Ảnh placeholder `lazy.png` mọi card → dùng thumb thật + `loading=lazy`.
* [ ] `javascript:void(0)` cho Thích/So sánh/Mua ngay → dùng `button + data-* + api.js`.
* [ ] Tag `Loại` lộn xộn → bỏ, dùng `brand + specs`.
* [ ] Copy ảnh/mô tả hshop nguyên văn → tự chụp/viết lại, ảnh >2MB phải nén, ghi nguồn nếu tham khảo.

<a id="file-mapping"></a>

## 7. Mapping vào file rỗng đã tạo

* [Giàu P2 điền](members/P2-GIAU.md#scope): `app/models/category.py, brand.py, product.py, product_image.py`, `app/routers/categories.py, brands.py, products.py`, `app/services/product_service.py`, `app/seeds/seed.py` (seed 50-100 SP theo nhóm §2).
* [Hưng P3 điền](members/P3-HUNG.md#scope): `app/models/cart.py, order.py, payment.py, voucher.py`, `app/routers/cart.py, orders.py, admin_orders.py`, `app/services/order_service.py`.
* [Gấm P4 điền](members/P4-GAM.md#scope): `app/templates/product/list.html (=PLP §2), product/detail.html (=PDP §3)`, `cart/cart.html, checkout.html, tracking.html (=§4)`, `index.html + base.html (=§5)`.
* [Dũng P1 khóa](members/P1-DUNG.md#scope): `app/core/*`, `alembic/*`; [API contract](API-DESIGN.md#contracts) khớp [PLP](#plp), [PDP](#pdp), [checkout](#checkout).

Không khớp [PLP](#plp), [PDP](#pdp), [checkout](#checkout) khi review = trả về, không merge.

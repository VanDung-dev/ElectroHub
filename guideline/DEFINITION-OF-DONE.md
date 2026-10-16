# Definition of Done + Giám sát — ElectroHub

[← Trang bắt đầu / chọn thành viên](README.md) · [Tra cứu theo công việc](README.md#lookup)

Cả nhóm tự kiểm tra trước khi mở PR; [Dũng phụ trách review/nghiệm thu](members/P1-DUNG.md#handoff).

<a id="task"></a>

## 1. Done của 1 task

* [ ] Code theo đúng vùng sở hữu trong [ranh giới công việc](README.md#ownership). Sửa chéo đã có approve.
* [ ] Backend: có test (`pytest`) + hiện đúng trên `/docs` + chạy bằng `docker compose up --build`.
* [ ] Frontend (Gấm P4): không lỗi console, responsive 360px/768px/1024px, ảnh có `alt + lazy`.
* [ ] Không hardcode secret/port/host trong code. `.env.example` cập nhật nếu thêm biến mới (Dũng P1 duyệt).
* [ ] PR pass `ruff + pytest`, có approve Dũng P1 (+ chủ vùng nếu liên quan: Giàu P2 / Hưng P3 / Gấm P4).

<a id="api"></a>

## 2. Done của 1 API (Giàu P2 / Hưng P3)

* [ ] Đúng path `/api/v1/...`, đúng format list `{items,total,page,page_size}`, lỗi `{detail}`.
* [ ] Có test happy + 1 test lỗi (hết hàng, sai quyền, voucher hết).
* [ ] Gấm P4 xác nhận fetch được bằng `api.js`, không cần sửa JS hack.

<a id="page"></a>

## 3. Done của 1 page (Gấm P4)

* [ ] Extends `base.html`, dùng `url_for('static')`, không CSS/JS inline.
* [ ] Gắn API thật, có trạng thái loading/empty/error. Không để trang trắng khi API lỗi.
* [ ] PLP/PDP/checkout đối chiếu [PLP](HSHOP-ANALYSIS.md#plp), [PDP](HSHOP-ANALYSIS.md#pdp), [checkout](HSHOP-ANALYSIS.md#checkout): PLP đủ filter giá/brand/sort, PDP đủ brand/warranty/stock/SKU/gallery/specs/related, cart tính đúng tiền.

<a id="monitoring"></a>

## 4. Giám sát hàng tuần (Dũng P1 chủ trì)

* Kanban 4 cột: `Todo / Doing / Review / Done`. Mỗi task ghi rõ assignee (Dũng/Giàu/Hưng/Gấm) + domain.
* Daily 15p async: hôm qua / hôm nay / blocker. Blocker > 1 ngày Dũng P1 phải can thiệp.
* Cuối W2/W3/W4 demo bằng Docker trên máy sạch:
  ```sh
  docker compose up --build --wait --wait-timeout 240
  # mở http://localhost:8000 + /docs, chạy flow chính
  ```
* Cấm demo bằng `uvicorn --reload` máy cá nhân khi nghiệm thu phase.

<a id="mvp"></a>

## 5. Checklist nghiệm thu MVP

* [ ] Register/login/logout + phân quyền admin/customer.
* [ ] CRUD product + search/filter/sort + wishlist/compare.
* [ ] Cart -> checkout -> COD/mock pay -> tra cứu đơn -> admin đổi trạng thái.
* [ ] Seed >= 50 sản phẩm + chính sách + 1 blog/review mẫu.
* [ ] [README ở gốc repo](../README.md) hướng dẫn chạy Docker từ đầu tới cuối không lỗi trên máy thứ 2.

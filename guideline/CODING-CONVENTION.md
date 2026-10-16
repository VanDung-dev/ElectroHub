# Coding Convention — FastAPI + HTML/CSS/JS thuần (không Node)

[← Trang bắt đầu / chọn thành viên](README.md) · [Tra cứu theo công việc](README.md#lookup)

Backend: [Dũng](members/P1-DUNG.md#tasks), [Giàu](members/P2-GIAU.md#tasks), [Hưng](members/P3-HUNG.md#tasks) đọc phần Python. [Gấm](members/P4-GAM.md#tasks) đọc HTML/CSS/JS; Dũng phối hợp CSRF.

<a id="python"></a>

## 1. Python / FastAPI (Dũng P1, Giàu P2, Hưng P3)

* Python 3.13, format `ruff` + `black` (line-length 100). Chạy trước khi push:
  ```sh
  ruff check app/ && ruff format --check app/
  pytest -q
  ```
* Đặt tên: file `snake_case`, class `PascalCase`, hàm/biến `snake_case`, hằng `UPPER_SNAKE`.
* Cấu trúc router chuẩn, Giàu P2 / Hưng P3 copy theo:
  ```python
  # app/routers/products.py
  from fastapi import APIRouter, Depends, Query
  router = APIRouter(prefix="/api/v1/products", tags=["products"])
  # GET /api/v1/products?category=&brand=&sort=&page=
  # service chứa logic, router chỉ validate + gọi service
  ```
* Mọi response JSON qua Pydantic schema, không return dict tự do. Request/response ví dụ phải hiện trên `/docs`.
* Không viết SQL thuần trong router. Dùng SQLAlchemy ORM + service layer: `routers/ -> services/ -> models/`.
* Config qua `pydantic-settings`, đọc từ `.env`. Không hardcode password, secret, port.
* Log bằng `logging`, không `print()`. Lỗi nghiệp vụ dùng `HTTPException` với mã rõ ràng.

<a id="html"></a>

## 2. HTML + Jinja2 (Gấm P4 chủ trì, Dũng P1 cấp CSRF)

* Mọi page extends `base.html`. Không copy header/footer.
  ```html
  {% extends "base.html" %}
  {% block title %}Chi tiết sản phẩm{% endblock %}
  {% block content %}...{% endblock %}
  ```
* Dùng `url_for('static', path='...')` cho css/js/img, không hardcode `/static/...`.
* Form POST có CSRF token (do Dũng P1 cấp). Hiển thị lỗi server bằng block chung, không alert bừa.
* Ảnh sản phẩm bắt buộc `alt`, `loading="lazy"`, width/height để tránh nhảy layout.

<a id="css"></a>

## 3. CSS (Gấm P4 chủ trì, Giàu P2 / Hưng P3 không sửa)

* 1 file global duy nhất: `base.css` chứa variables + reset + header/footer. Mỗi page 1 file riêng `home.css, plp.css, pdp.css, checkout.css, admin.css`.
* BEM: `.product-card__price--sale`. Không dùng `!important`, không style global `div { ... }`.
* Variables bắt buộc:
  ```css
  :root { --primary:#0d6efd; --text:#212529; --muted:#6c757d; --radius:8px; }
  ```
* Responsive mobile-first, breakpoint duy nhất: `768px, 1024px`. Test ở 360px trước.

<a id="javascript"></a>

## 4. JS thuần, ES modules (Gấm P4 chủ trì, Giàu P2 / Hưng P3 chỉ thêm data-attribute)

* Chia file, không dồn 1 file:
  ```text
  static/js/api.js       # fetch wrapper duy nhất
  static/js/auth.js
  static/js/product.js   # PLP/PDP
  static/js/cart.js
  static/js/checkout.js
  static/js/admin.js
  ```
* Mọi gọi API đi qua `api.js`, dùng relative path:
  ```js
  // api.js
  export async function api(path, opts = {}) {
    const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
    if (!res.ok) throw new Error((await res.json()).detail ?? res.statusText);
    return res.json();
  }
  // dùng: api("/api/v1/products?page=1")
  ```
* Không hardcode `http://localhost:8000`. Không lưu JWT trong JS (cookie HttpOnly do backend set).
* Gắn dữ liệu bằng `data-*`: `<button data-add-cart="123">`, JS đọc attribute, không render HTML bằng string nối trong JS trừ list nhỏ.
* Không lỗi console là DoD. Dùng `type="module"` + `defer`.

<a id="prohibitions"></a>

## 5. Những điều cấm

* Không thêm framework JS qua CDN khi chưa được Dũng P1 duyệt.
* Không viết CSS/JS inline trong HTML trừ trường hợp bất khả kháng.
* Không commit file build, file nén, ảnh > 2MB vào repo (ảnh lớn để ngoài + nén trước).

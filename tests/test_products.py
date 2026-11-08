import io

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.user import User
from tests.conftest import csrf_headers, login, register


@pytest.mark.parametrize(
    "price,sale,stock,discount",
    [(185000, 165000, 3, "10,8%"), (100000, 0, 3, "100%"), (0, None, 0, None), (100, 100, 3, None)],
)
def test_product_purchase_buttons_and_discount(client, database, price, sale, stock, discount):
    with Session(database) as db:
        db.add(
            Product(
                slug="demo", sku="DEMO-1", name="Demo", price=price, sale_price=sale, stock=stock
            )
        )
        db.commit()
    response = client.get("/products/demo")
    assert response.status_code == 200
    assert "data-buy-now" in response.text and "Mua ngay" in response.text
    assert "data-add-to-cart" in response.text
    if discount:
        assert f"Giảm {discount}" in response.text
    else:
        assert "detail-discount" not in response.text
    if stock == 0:
        assert 'data-buy-now="1" disabled' in response.text


def test_demo_products_seed_and_images(client, database):
    from app.core.config import ROOT
    from app.seeds.seed import seed_products

    all_product_images = (
        "arduino-uno.png",
        "arduino-uno-1.png",
        "arduino-uno-2.png",
        "arduino-uno-3.png",
        "esp32-devkit.png",
        "esp32-devkit-1.png",
        "esp32-devkit-2.png",
        "dht22.png",
        "dht22-1.png",
        "dht22-2.png",
        "dht22-3.png",
    )

    # 1. Verify all image files exist on disk
    for filename in all_product_images:
        path = ROOT / "app/static/img/products" / filename
        assert path.is_file(), f"Missing product image: {filename}"

    # 2. Seed database
    with Session(database) as db:
        updated = seed_products(db)
        assert updated >= 3

    # 3. Check storefront renders the new image URLs
    html = client.get("/").text
    assert "/static/img/products/esp32-devkit.png" in html
    assert "/static/img/products/arduino-uno.png" in html
    assert "/static/img/products/dht22.png" in html

    # 4. Check static endpoint serves all product images with 200
    for filename in all_product_images:
        res = client.get(f"/static/img/products/{filename}")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("image/png")

    # 5. Check PDP gallery for demo products (multi-image)
    for slug in ("arduino-uno-demo", "esp32-devkit-demo", "dht22-demo"):
        pdp_html = client.get(f"/products/{slug}").text
        assert "product-gallery" in pdp_html
        assert "gallery-thumbs" in pdp_html
        assert "gallery-thumb is-active" in pdp_html
        assert "gallery-nav--prev" in pdp_html
        assert "gallery-nav--next" in pdp_html
        # Textual face labels and badge removed per UX requirements
        assert "product-gallery-badge" not in pdp_html
        assert "thumb-label" not in pdp_html

    # Check specific gallery items for Arduino Uno
    uno_html = client.get("/products/arduino-uno-demo").text
    assert "/static/img/products/arduino-uno-1.png" in uno_html
    assert "/static/img/products/arduino-uno-2.png" in uno_html
    assert "/static/img/products/arduino-uno-3.png" in uno_html

    # Check specific gallery items for DHT22
    dht_html = client.get("/products/dht22-demo").text
    assert "/static/img/products/dht22.png" in dht_html
    assert "/static/img/products/dht22-1.png" in dht_html
    assert "/static/img/products/dht22-2.png" in dht_html
    assert "/static/img/products/dht22-3.png" in dht_html


def test_product_detail_single_image_no_thumbnails(client, database):
    with Session(database) as db:
        db.add(
            Product(
                slug="single-img-product",
                sku="SINGLE-001",
                name="Sản phẩm một ảnh",
                price=50000,
                stock=5,
                image_url="/static/img/product-placeholder.svg",
            )
        )
        db.commit()

    html = client.get("/products/single-img-product").text
    assert "product-gallery" in html
    assert "gallery-main" in html
    assert "gallery-thumbs" not in html
    assert "gallery-nav" not in html


def make_admin(client, database, email="admin_products@example.com"):
    register(client, email=email, name="Quản trị")
    with Session(database) as db:
        user = db.scalar(select(User).where(User.email == email))
        user.role = "admin"
        db.commit()
    assert login(client, email=email).status_code == 200
    return csrf_headers(client)


def test_product_detail_renders_rich_html_description(client, database):
    html_desc = (
        "<h3>Đặc điểm nổi bật</h3>"
        "<ul><li>Hỗ trợ Wi-Fi &amp; Bluetooth</li><li>Điện áp 3.3V</li></ul>"
        "<p>Thiết bị chuẩn công nghiệp.</p>"
    )
    with Session(database) as db:
        db.add(
            Product(
                slug="esp32-rich-desc",
                sku="ESP32-RICH-1",
                name="ESP32 Rich Description",
                price=150000,
                stock=20,
                description=html_desc,
                image_url="/static/img/products/esp32-devkit.png",
            )
        )
        db.commit()

    response = client.get("/products/esp32-rich-desc")
    assert response.status_code == 200
    assert "product-description-body" in response.text
    # Ensure HTML is rendered safe (not escaped into &lt;h3&gt;)
    assert "<h3>Đặc điểm nổi bật</h3>" in response.text
    assert "<li>Hỗ trợ Wi-Fi &amp; Bluetooth</li>" in response.text
    assert "<p>Thiết bị chuẩn công nghiệp.</p>" in response.text


def test_admin_products_page_and_tinymce_integration(client, database):
    admin_headers = make_admin(client, database)
    response = client.get("/admin/products", headers=admin_headers)
    assert response.status_code == 200
    html = response.text

    # Verify TinyMCE library CDN inclusion
    assert "tinymce" in html
    assert "tinymce.min.js" in html

    # Verify Product creation form elements and helpers
    assert 'id="admin-product-description"' in html
    assert "data-generate-slug" in html
    assert "data-generate-sku" in html
    assert "data-preset-stock" in html
    assert "data-upload-primary" in html
    assert "data-open-library" in html
    assert "data-insert-template" in html

    # Verify Live Storefront Preview Frame
    assert "storefront-preview-card" in html
    assert "data-live-desc" in html
    assert "data-live-info-text" in html


def test_admin_create_and_update_product_with_html_description(client, database):
    admin_headers = make_admin(client, database, email="admin_create_update@example.com")

    # 1. Create a product with rich HTML description
    create_payload = {
        "slug": "esp32-tinymce-test",
        "sku": "ESP32-TINY-01",
        "name": "ESP32 TinyMCE Test Board",
        "price": 180000,
        "sale_price": 150000,
        "stock": 45,
        "image_url": "/static/img/products/esp32-devkit.png",
        "description": "<h3>Thông số</h3><ul><li>Flash 4MB</li><li>SRAM 520KB</li></ul>",
    }
    create_res = client.post("/api/v1/admin/products", json=create_payload, headers=admin_headers)
    assert create_res.status_code == 201
    created_id = create_res.json()["id"]

    # 2. Verify on public product detail page
    pdp_res = client.get("/products/esp32-tinymce-test")
    assert pdp_res.status_code == 200
    assert "<h3>Thông số</h3>" in pdp_res.text
    assert "<li>Flash 4MB</li>" in pdp_res.text

    # 3. Update product description with modified HTML
    update_payload = {
        **create_payload,
        "description": "<h3>Thông số bản nâng cấp</h3><p>Đã tích hợp ăng-ten gốm ceramic.</p>",
    }
    update_res = client.put(
        f"/api/v1/admin/products/{created_id}", json=update_payload, headers=admin_headers
    )
    assert update_res.status_code == 200

    # 4. Verify updated description on PDP
    pdp_res2 = client.get("/products/esp32-tinymce-test")
    assert pdp_res2.status_code == 200
    assert "<h3>Thông số bản nâng cấp</h3>" in pdp_res2.text
    assert "<p>Đã tích hợp ăng-ten gốm ceramic.</p>" in pdp_res2.text


def test_admin_create_product_with_multi_images_and_gallery(client, database):
    admin_headers = make_admin(client, database, email="admin_multi_images@example.com")

    # 1. Check admin page has gallery elements
    admin_page = client.get("/admin/products", headers=admin_headers).text
    assert "data-gallery-container" in admin_page
    assert "data-add-gallery-item" in admin_page
    assert "data-preset-gallery" in admin_page
    assert "data-live-gallery" in admin_page

    # 2. Create product with primary image and secondary gallery images
    payload = {
        "slug": "esp32-multi-angle",
        "sku": "ESP32-MULTI-01",
        "name": "ESP32 Multi Angle Board",
        "price": 160000,
        "stock": 30,
        "image_url": "/static/img/products/esp32-devkit.png",
        "description": "<p>Bo mạch nhiều ảnh xem thực tế.</p>",
        "images": [
            {"url": "/static/img/products/esp32-devkit.png", "alt": "Mặt trước", "sort": 0},
            {"url": "/static/img/products/esp32-devkit-1.png", "alt": "Góc nghiêng", "sort": 1},
            {"url": "/static/img/products/esp32-devkit-2.png", "alt": "Mặt sau", "sort": 2},
        ],
    }
    create_res = client.post("/api/v1/admin/products", json=payload, headers=admin_headers)
    assert create_res.status_code == 201
    created_id = create_res.json()["id"]
    assert len(create_res.json()["images"]) == 3

    # 3. Check public PDP renders gallery thumbs & nav buttons
    pdp_html = client.get("/products/esp32-multi-angle").text
    assert "gallery-thumbs" in pdp_html
    assert "gallery-nav--prev" in pdp_html
    assert "gallery-nav--next" in pdp_html
    assert "/static/img/products/esp32-devkit-1.png" in pdp_html
    assert "/static/img/products/esp32-devkit-2.png" in pdp_html

    # 4. Update product gallery images
    update_payload = {
        **payload,
        "images": [
            {"url": "/static/img/products/esp32-devkit.png", "alt": "Mặt trước", "sort": 0},
            {"url": "/static/img/products/esp32-devkit-1.png", "alt": "Góc nghiêng", "sort": 1},
        ],
    }
    update_res = client.put(
        f"/api/v1/admin/products/{created_id}", json=update_payload, headers=admin_headers
    )
    assert update_res.status_code == 200
    assert len(update_res.json()["images"]) == 2

    # Verify on PDP
    pdp_html2 = client.get("/products/esp32-multi-angle").text
    assert "/static/img/products/esp32-devkit-2.png" not in pdp_html2


def test_admin_upload_image_and_library_list(client, database):
    admin_headers = make_admin(client, database, email="admin_uploader@example.com")

    # 1. Non-admin cannot upload
    fake_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
        b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    no_auth_res = client.post(
        "/api/v1/admin/products/upload-image",
        files={"file": ("test_chip.png", io.BytesIO(fake_png), "image/png")},
    )
    assert no_auth_res.status_code in (401, 403)

    # 2. Admin uploads valid PNG image (with standard and browser-specific MIME types)
    upload_res = client.post(
        "/api/v1/admin/products/upload-image",
        files={"file": ("test_chip.png", io.BytesIO(fake_png), "image/png")},
        headers=admin_headers,
    )
    assert upload_res.status_code == 200
    uploaded_url = upload_res.json()["url"]
    uploaded_filename = upload_res.json()["filename"]
    assert uploaded_url.startswith("/static/img/products/prod_")
    assert uploaded_url.endswith(".png")

    # 2b. Admin uploads PNG with uppercase extension and octet-stream MIME
    upload_res2 = client.post(
        "/api/v1/admin/products/upload-image",
        files={"file": ("MY_MODULE.PNG", io.BytesIO(fake_png), "application/octet-stream")},
        headers=admin_headers,
    )
    assert upload_res2.status_code == 200
    uploaded_url2 = upload_res2.json()["url"]
    uploaded_filename2 = upload_res2.json()["filename"]
    assert uploaded_url2.endswith(".png")

    # Verify static file can be retrieved
    file_res = client.get(uploaded_url)
    assert file_res.status_code == 200

    # 3. List library images
    lib_res = client.get("/api/v1/admin/products/library-images", headers=admin_headers)
    assert lib_res.status_code == 200
    items = lib_res.json()["items"]
    assert any(item["url"] == uploaded_url for item in items)

    # Clean up uploaded test file
    from app.core.config import ROOT

    test_file_path = ROOT / "app" / "static" / "img" / "products" / uploaded_filename
    if test_file_path.exists():
        test_file_path.unlink()
    test_file_path2 = ROOT / "app" / "static" / "img" / "products" / uploaded_filename2
    if test_file_path2.exists():
        test_file_path2.unlink()

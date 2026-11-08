import pytest
from sqlalchemy.orm import Session

from app.models.product import Product


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

"""Server-rendered catalog: product links must exist in the raw HTML.

`/` and `/collections/all` used to be empty containers filled by `store.js`, so a
crawler without JavaScript saw no product links. These tests pin the SSR markup
and the `q` / `sale` filters that mirror the client-side behaviour.
"""

import re

from sqlalchemy.orm import Session

from app.models.product import Product


def add_product(database, **overrides) -> Product:
    values = {
        "slug": "esp32-devkit",
        "sku": "EH-ESP32",
        "name": "ESP32 DevKit",
        "description": "Bo mạch phát triển ESP32.",
        "price": 185000,
        "sale_price": 165000,
        "stock": 5,
    }
    values.update(overrides)
    with Session(database) as db:
        product = Product(**values)
        db.add(product)
        db.commit()
        db.refresh(product)
        return product


def card_slugs(html: str) -> list[str]:
    pattern = r'<a class="product-name" href="/products/([^"]+)"'
    return list(dict.fromkeys(re.findall(pattern, html)))


def test_catalog_page_renders_products_without_javascript(client, database):
    add_product(database)
    add_product(
        database,
        slug="dht22",
        sku="EH-DHT22",
        name="Cảm biến DHT22",
        price=95000,
        sale_price=None,
        stock=0,
    )
    html = client.get("/collections/all").text
    assert "Đang tải sản phẩm" not in html
    assert html.count('class="product-card"') == 2
    assert card_slugs(html) == ["dht22", "esp32-devkit"]
    assert "2 sản phẩm" in html
    assert "Tạm hết hàng" in html


def test_homepage_renders_product_links(client, database):
    add_product(database)
    html = client.get("/").text
    assert 'href="/products/esp32-devkit"' in html
    assert 'class="product-card"' in html
    assert "Đang tải sản phẩm" not in html


def test_catalog_search_is_server_side_and_accent_insensitive(client, database):
    add_product(database)
    add_product(
        database,
        slug="dht22",
        sku="EH-DHT22",
        name="Cảm biến DHT22",
        price=95000,
        sale_price=None,
        stock=0,
    )
    assert card_slugs(client.get("/collections/all", params={"q": "cam bien"}).text) == ["dht22"]
    assert card_slugs(client.get("/collections/all", params={"q": "eh-esp"}).text) == [
        "esp32-devkit"
    ]
    assert card_slugs(client.get("/collections/all", params={"q": "khong-co"}).text) == []


def test_catalog_sale_filter_is_server_side(client, database):
    add_product(database)
    add_product(
        database,
        slug="dht22",
        sku="EH-DHT22",
        name="Cảm biến DHT22",
        price=95000,
        sale_price=None,
        stock=0,
    )
    assert card_slugs(client.get("/collections/all", params={"sale": "1"}).text) == ["esp32-devkit"]


def test_server_rendered_card_matches_storefront_contract(client, database):
    product = add_product(database)
    html = client.get("/collections/all").text
    assert f'data-add-to-cart="{product.id}"' in html
    assert f'data-buy-now="{product.id}"' in html
    assert 'loading="lazy"' in html
    assert f'alt="{product.name}"' in html
    # vi-VN grouping (dots), the same format `toLocaleString("vi-VN")` produces.
    assert "165.000 ₫" in html and "185.000 ₫" in html
    assert "Giảm 10,8%" in html
    assert "Còn hàng · 5" in html


def test_catalog_empty_state_without_products(client, database):
    html = client.get("/collections/all").text
    assert "Không tìm thấy sản phẩm" in html
    assert "0 sản phẩm" in html
    assert 'class="product-card"' not in html

import json
import re

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.pages import product_meta_description
from app.models.product import Product

JSON_LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def json_ld_blocks(html: str) -> list[dict]:
    return [json.loads(block) for block in JSON_LD.findall(html)]


def add_product(database, **overrides) -> Product:
    values = {
        "slug": "esp32-devkit",
        "sku": "EH-ESP32",
        "name": "ESP32 DevKit",
        "description": "Bo mạch phát triển ESP32 với WiFi và Bluetooth cho dự án nhà thông minh.",
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


def meta(html: str, name: str, attribute: str = "name") -> str | None:
    if attribute == "rel":
        pattern = rf'<link rel="{re.escape(name)}" href="([^"]*)">'
    else:
        pattern = rf'<meta {attribute}="{re.escape(name)}" content="([^"]*)">'
    match = re.search(pattern, html)
    return match.group(1) if match else None


def test_homepage_meta_and_site_structured_data(client):
    base = get_settings().site_url.rstrip("/")
    response = client.get("/")
    assert response.status_code == 200
    html = response.text
    assert meta(html, "description") == (
        "Tìm bo mạch, cảm biến và linh kiện điện tử cho dự án của bạn tại ElectroHub."
    )
    assert meta(html, "robots") == "index,follow"
    assert meta(html, "canonical", "rel") == f"{base}/"
    assert meta(html, "og:type", "property") == "website"

    blocks = json_ld_blocks(html)
    assert len(blocks) == 1
    types = {node["@type"] for node in blocks[0]["@graph"]}
    assert types == {"WebSite", "Organization"}
    website = next(node for node in blocks[0]["@graph"] if node["@type"] == "WebSite")
    action = website["potentialAction"]
    assert action["@type"] == "SearchAction"
    assert action["target"]["urlTemplate"].endswith("/collections/all?q={search_term_string}")


def test_product_detail_meta_and_json_ld(client, database):
    base = get_settings().site_url.rstrip("/")
    product = add_product(database)
    response = client.get(f"/products/{product.slug}")
    assert response.status_code == 200
    html = response.text

    assert meta(html, "canonical", "rel") == f"{base}/products/{product.slug}"
    assert meta(html, "robots") == "index,follow"
    assert meta(html, "og:type", "property") == "product"
    assert meta(html, "og:url", "property") == f"{base}/products/{product.slug}"
    assert re.search(r"<h1[^>]*>", html)
    assert html.count("<h1") == 1

    description = meta(html, "description")
    assert description is not None and len(description) <= 160
    assert "165.000₫" in description and "Còn hàng" in description
    assert "165.000 ₫" in html  # vi-VN price format, matching the product cards

    product_node = next(
        node
        for block in json_ld_blocks(html)
        for node in block.get("@graph", [])
        if node.get("@type") == "Product"
    )
    assert product_node["name"] == "ESP32 DevKit"
    assert product_node["sku"] == "EH-ESP32"
    assert product_node["url"] == f"{base}/products/{product.slug}"
    assert product_node["image"] == [f"{base}/static/img/product-placeholder.svg"]
    offer = product_node["offers"]
    assert offer["price"] == "165000"
    assert offer["priceCurrency"] == "VND"
    assert offer["availability"] == "https://schema.org/InStock"

    breadcrumb = next(
        node
        for block in json_ld_blocks(html)
        for node in block.get("@graph", [])
        if node.get("@type") == "BreadcrumbList"
    )
    assert [item["name"] for item in breadcrumb["itemListElement"]] == [
        "Trang chủ",
        "Sản phẩm",
        "ESP32 DevKit",
    ]


def test_product_out_of_stock_offer(client, database):
    product = add_product(database, slug="hong-son", sku="EH-HS", stock=0, sale_price=None)
    html = client.get(f"/products/{product.slug}").text
    product_node = next(
        node
        for block in json_ld_blocks(html)
        for node in block.get("@graph", [])
        if node.get("@type") == "Product"
    )
    assert product_node["offers"]["availability"] == "https://schema.org/OutOfStock"
    assert product_node["offers"]["price"] == "185000"


def test_product_json_ld_escapes_script_breakout(client, database):
    product = add_product(
        database,
        slug="safe",
        sku="EH-SAFE",
        description='Mô tả </script><script>alert("xss")</script> kết thúc.',
    )
    html = client.get(f"/products/{product.slug}").text
    # json_ld_blocks would raise if a raw </script> had closed the JSON-LD element.
    blocks = json_ld_blocks(html)
    assert "<\\/script>" in html
    product_node = next(
        node
        for block in blocks
        for node in block.get("@graph", [])
        if node.get("@type") == "Product"
    )
    assert product_node["description"] == product.description
    # A raw </script> in the description would close the JSON-LD element early and
    # leave an orphan "<script>alert..." tag behind.
    assert "</script><script>alert" not in html


def test_product_meta_description_keeps_word_boundaries():
    long_text = " ".join(["từ"] * 80)
    description = product_meta_description(
        Product(
            slug="x",
            sku="X",
            name="X",
            description=long_text,
            price=1000,
            sale_price=None,
            stock=1,
        )
    )
    assert len(description) <= 160
    assert not description.endswith(" ")


def test_product_meta_description_falls_back_without_description():
    product = Product(
        slug="x",
        sku="EH-X",
        name="Cảm biến nhiệt",
        description="",
        price=90000,
        sale_price=None,
        stock=2,
    )
    description = product_meta_description(product)
    assert description.startswith("Mua Cảm biến nhiệt (SKU EH-X)")
    assert "90.000₫" in description
    assert len(description) <= 160


def test_sitemap_lists_indexable_urls_with_lastmod(client, database):
    base = get_settings().site_url.rstrip("/")
    product = add_product(database)
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    body = response.text
    assert f"<loc>{base}/</loc>" in body
    assert f"<loc>{base}/collections/all</loc>" in body
    assert f"<loc>{base}/products/{product.slug}</loc>" in body
    assert body.count("<lastmod>") == 3
    assert re.search(r"<lastmod>\d{4}-\d{2}-\d{2}</lastmod>", body)


def test_robots_txt(client):
    body = client.get("/robots.txt").text
    assert body.startswith("User-agent: *\nAllow: /\n")
    assert "Disallow: /api/\n" in body
    assert "Disallow: /admin/\n" in body
    assert "Disallow: /manager\n" in body
    assert "Disallow: /staff/\n" in body
    assert f"Sitemap: {get_settings().site_url.rstrip('/')}/sitemap.xml\n" in body


def test_private_pages_are_noindex(client):
    # Pages that require a session answer 401, so only anonymous ones are checked here.
    for path in ("/cart", "/checkout", "/account/login", "/account/register"):
        assert meta(client.get(path).text, "robots") == "noindex,follow", path
    for path in ("/", "/collections/all"):
        assert meta(client.get(path).text, "robots") == "index,follow", path


def test_social_cards_use_raster_image_with_dimensions(client, database):
    base = get_settings().site_url.rstrip("/")
    product = add_product(database)
    for path in ("/", "/collections/all", f"/products/{product.slug}"):
        html = client.get(path).text
        assert meta(html, "og:image", "property") == f"{base}/static/img/og-default.png", path
        assert meta(html, "og:image:type", "property") == "image/png", path
        assert meta(html, "og:image:width", "property") == "1200", path
        assert meta(html, "og:image:height", "property") == "630", path
        assert meta(html, "twitter:image:alt"), path


def test_raster_product_image_is_kept_for_sharing(client, database):
    product = add_product(database, image_url="https://cdn.example.com/products/esp32.jpg")
    html = client.get(f"/products/{product.slug}").text
    assert meta(html, "og:image", "property") == "https://cdn.example.com/products/esp32.jpg"
    assert meta(html, "og:image:type", "property") == "image/jpeg"


def test_pages_declare_a_favicon(client):
    html = client.get("/").text
    assert 'rel="icon"' in html and "img/favicon.svg" in html
    assert 'rel="apple-touch-icon"' in html


def test_product_title_is_long_enough_and_keyword_rich(client, database):
    product = add_product(database)
    html = client.get(f"/products/{product.slug}").text
    title = re.search(r"<title>(.*?)</title>", html).group(1)
    assert title == f"{product.name} | Giá tốt tại ElectroHub"
    assert 30 <= len(title) <= 70


def test_product_title_truncates_very_long_names(client, database):
    product = add_product(
        database, slug="ten-rat-dai", sku="EH-LONG", name="Bo mạch " + "rất dài " * 20
    )
    html = client.get(f"/products/{product.slug}").text
    title = re.search(r"<title>(.*?)</title>", html).group(1)
    assert len(title) <= 70
    assert title.endswith("| Giá tốt tại ElectroHub")


def test_trailing_slash_redirects_permanently(client, database):
    product = add_product(database)
    response = client.get(f"/products/{product.slug}/", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"].endswith(f"/products/{product.slug}")


def test_missing_page_returns_html_with_a_way_home(client):
    response = client.get("/products/khong-ton-tai")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")
    assert 'href="/"' in response.text
    assert meta(response.text, "robots") == "noindex,follow"


def test_api_404_stays_json(client):
    response = client.get("/api/v1/products/khong-ton-tai")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_unsubscribe_page_is_noindex(client):
    html = client.get("/newsletter/unsubscribe", params={"token": "abc"}).text
    assert meta(html, "robots") == "noindex,follow"


def test_facebook_share_link_is_nofollow(client, database):
    product = add_product(database)
    html = client.get(f"/products/{product.slug}").text
    assert 'rel="noopener noreferrer nofollow"' in html

"""Insert a small, clearly labeled demo catalog without replacing existing products."""

from sqlalchemy import select

from app.core.database import Session, get_engine
from app.models.product import Product, ProductImage

DEMO_PRODUCTS = (
    {
        "slug": "esp32-devkit-demo",
        "sku": "EH-DEMO-001",
        "name": "ESP32 DevKit (sản phẩm mẫu)",
        "description": "Bo mạch phát triển ESP32 mẫu để kiểm tra giao diện cửa hàng.",
        "image_url": "/static/img/products/esp32-devkit.png",
        "price": 185_000,
        "sale_price": 165_000,
        "stock": 25,
    },
    {
        "slug": "arduino-uno-demo",
        "sku": "EH-DEMO-002",
        "name": "Arduino Uno (sản phẩm mẫu)",
        "description": "Bo mạch Arduino Uno mẫu để kiểm tra luồng xem sản phẩm và giỏ hàng.",
        "image_url": "/static/img/products/arduino-uno.png",
        "price": 220_000,
        "sale_price": None,
        "stock": 18,
    },
    {
        "slug": "dht22-demo",
        "sku": "EH-DEMO-003",
        "name": "Cảm biến DHT22 (sản phẩm mẫu)",
        "description": "Cảm biến nhiệt độ và độ ẩm mẫu để kiểm tra giá và tình trạng kho.",
        "image_url": "/static/img/products/dht22.png",
        "price": 95_000,
        "sale_price": None,
        "stock": 40,
    },
)

# Additional mappings for sample products from initial SQL seeds
ADDITIONAL_IMAGE_MAPPINGS = {
    "EH-ESP32": "/static/img/products/esp32-devkit.png",
    "EH-UNO-R3": "/static/img/products/arduino-uno.png",
    "EH-DHT22": "/static/img/products/dht22.png",
}

# Multi-image gallery definitions (supporting front, angle, back, and flexible other/khác)
PRODUCT_GALLERY_MAPPINGS = {
    "arduino-uno": [
        {"url": "/static/img/products/arduino-uno.png", "alt": "Mặt trước", "sort": 0},
        {"url": "/static/img/products/arduino-uno-1.png", "alt": "Góc nghiêng", "sort": 1},
        {"url": "/static/img/products/arduino-uno-2.png", "alt": "Mặt sau", "sort": 2},
        {
            "url": "/static/img/products/arduino-uno-3.png",
            "alt": "Khác / Sơ đồ chi tiết",
            "sort": 3,
        },
    ],
    "esp32": [
        {"url": "/static/img/products/esp32-devkit.png", "alt": "Mặt trước", "sort": 0},
        {"url": "/static/img/products/esp32-devkit-1.png", "alt": "Góc nghiêng", "sort": 1},
        {"url": "/static/img/products/esp32-devkit-2.png", "alt": "Khác / Chi tiết", "sort": 2},
    ],
    "dht22": [
        {"url": "/static/img/products/dht22.png", "alt": "Mặt trước", "sort": 0},
        {"url": "/static/img/products/dht22-1.png", "alt": "Mặt sau", "sort": 1},
        {"url": "/static/img/products/dht22-2.png", "alt": "Chân cắm", "sort": 2},
        {"url": "/static/img/products/dht22-3.png", "alt": "Khác / Thông số", "sort": 3},
    ],
}


def _match_gallery_key(product: Product) -> str | None:
    text = f"{product.slug} {product.sku}".lower()
    if "arduino-uno" in text or "uno" in text:
        return "arduino-uno"
    if "esp32" in text:
        return "esp32"
    if "dht22" in text:
        return "dht22"
    return None


def _sync_gallery(product: Product, images_data: list[dict]) -> bool:
    existing_urls = [img.url for img in product.images]
    target_urls = [img["url"] for img in images_data]
    if existing_urls == target_urls and all(
        img.alt == d["alt"] and img.sort == d["sort"]
        for img, d in zip(product.images, images_data, strict=False)
    ):
        return False
    product.images.clear()
    for d in images_data:
        product.images.append(
            ProductImage(
                product_id=product.id,
                url=d["url"],
                alt=d.get("alt", "Khác"),
                sort=d.get("sort", 0),
            )
        )
    return True


def seed_products(db: Session) -> int:
    """Insert or update demo products with image URLs, inventory, and gallery images."""
    updated = 0
    for values in DEMO_PRODUCTS:
        product = db.scalar(
            select(Product).where((Product.slug == values["slug"]) | (Product.sku == values["sku"]))
        )
        if product is None:
            product = Product(**values)
            db.add(product)
            db.flush()
            updated += 1
        else:
            for k, v in values.items():
                setattr(product, k, v)
            updated += 1
        gallery_key = _match_gallery_key(product)
        if gallery_key and gallery_key in PRODUCT_GALLERY_MAPPINGS:
            if _sync_gallery(product, PRODUCT_GALLERY_MAPPINGS[gallery_key]):
                updated += 1

    for sku, image_url in ADDITIONAL_IMAGE_MAPPINGS.items():
        product = db.scalar(select(Product).where(Product.sku == sku))
        if product is not None:
            if product.image_url != image_url:
                product.image_url = image_url
                updated += 1
            gallery_key = _match_gallery_key(product)
            if gallery_key and gallery_key in PRODUCT_GALLERY_MAPPINGS:
                if _sync_gallery(product, PRODUCT_GALLERY_MAPPINGS[gallery_key]):
                    updated += 1

    db.commit()
    return updated


def main() -> None:
    with Session(get_engine()) as db:
        count = seed_products(db)
    print(f"Demo products are ready. Processed {count} product(s).")


if __name__ == "__main__":
    main()

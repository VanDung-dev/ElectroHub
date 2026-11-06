"""Insert a small, clearly labeled demo catalog without replacing existing products."""

from sqlalchemy import select

from app.core.database import Session, get_engine
from app.models.product import Product

DEMO_PRODUCTS = (
    {
        "slug": "esp32-devkit-demo",
        "sku": "EH-DEMO-001",
        "name": "ESP32 DevKit (sản phẩm mẫu)",
        "description": "Bo mạch phát triển ESP32 mẫu để kiểm tra giao diện cửa hàng.",
        "price": 185_000,
        "sale_price": 165_000,
        "stock": 25,
    },
    {
        "slug": "arduino-uno-demo",
        "sku": "EH-DEMO-002",
        "name": "Arduino Uno (sản phẩm mẫu)",
        "description": "Bo mạch Arduino Uno mẫu để kiểm tra luồng xem sản phẩm và giỏ hàng.",
        "price": 220_000,
        "sale_price": None,
        "stock": 18,
    },
    {
        "slug": "dht22-demo",
        "sku": "EH-DEMO-003",
        "name": "Cảm biến DHT22 (sản phẩm mẫu)",
        "description": "Cảm biến nhiệt độ và độ ẩm mẫu để kiểm tra giá và tình trạng kho.",
        "price": 95_000,
        "sale_price": None,
        "stock": 40,
    },
)


def main() -> None:
    with Session(get_engine()) as db:
        for values in DEMO_PRODUCTS:
            if db.scalar(select(Product.id).where(Product.slug == values["slug"])) is None:
                db.add(Product(**values))
        db.commit()
    print("Demo products are ready. Existing product records were left unchanged.")


if __name__ == "__main__":
    main()

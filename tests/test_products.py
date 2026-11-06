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

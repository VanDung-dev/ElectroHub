from typing import Annotated
from urllib.parse import unquote, urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.deps import DbSession, require_admin
from app.models.product import Product
from app.models.user import User

router = APIRouter(prefix="/api/v1/products", tags=["products"])
admin_router = APIRouter(prefix="/api/v1/admin/products", tags=["admin", "products"])
AdminUser = Annotated[User, Depends(require_admin)]


class ProductCard(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    sku: str
    name: str
    description: str
    image_url: str
    price: int
    sale_price: int | None
    stock: int


class ProductList(BaseModel):
    items: list[ProductCard]


class ProductUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=200)
    sku: str = Field(pattern=r"^[A-Z0-9-]{1,32}$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    image_url: str = Field(default="/static/img/product-placeholder.svg", max_length=500)
    price: int = Field(ge=0)
    sale_price: int | None = Field(default=None, ge=0)
    stock: int = Field(ge=0)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Tên sản phẩm không được để trống")
        return value

    @model_validator(mode="after")
    def validate_product(self):
        if self.sale_price is not None and self.sale_price > self.price:
            raise ValueError("Giá khuyến mãi không được cao hơn giá gốc")
        image = urlsplit(self.image_url)
        if not (
            (
                image.scheme == "https"
                and image.hostname
                and not image.username
                and not image.password
            )
            or (
                not image.scheme
                and not image.netloc
                and image.path.startswith("/static/img/")
                and ".." not in unquote(image.path).split("/")
            )
        ):
            raise ValueError("Ảnh phải là URL HTTPS hoặc đường dẫn trong /static/img/")
        return self


@router.get("", response_model=ProductList)
def list_products(db: DbSession) -> dict:
    return {"items": db.scalars(select(Product).order_by(Product.name, Product.id)).all()}


@router.get("/{slug}", response_model=ProductCard)
def get_product(slug: str, db: DbSession) -> Product:
    product = db.scalar(select(Product).where(Product.slug == slug))
    if product is None:
        raise HTTPException(404, "Không tìm thấy sản phẩm")
    return product


@admin_router.get("", response_model=ProductList)
def list_admin_products(user: AdminUser, db: DbSession):
    return {"items": db.scalars(select(Product).order_by(Product.name, Product.id)).all()}


@admin_router.post("", response_model=ProductCard, status_code=201)
def create_product(data: ProductUpsert, user: AdminUser, db: DbSession):
    product = Product(**data.model_dump())
    db.add(product)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Slug hoặc mã SKU đã được sử dụng") from None
    db.refresh(product)
    return product


@admin_router.put("/{product_id}", response_model=ProductCard)
def update_product(product_id: int, data: ProductUpsert, user: AdminUser, db: DbSession):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(404, "Không tìm thấy sản phẩm")
    for key, value in data.model_dump().items():
        setattr(product, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Slug hoặc mã SKU đã được sử dụng") from None
    db.refresh(product)
    return product

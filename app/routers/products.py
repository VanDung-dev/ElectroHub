import io
import secrets
from pathlib import Path
from typing import Annotated
from urllib.parse import unquote, urlsplit

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.core.config import ROOT
from app.core.deps import DbSession, require_admin
from app.models.cart import CartItem
from app.models.order import OrderItem
from app.models.product import Product, ProductImage
from app.models.user import User

ALLOWED_UPLOAD_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB

router = APIRouter(prefix="/api/v1/products", tags=["products"])
admin_router = APIRouter(prefix="/api/v1/admin/products", tags=["admin", "products"])
AdminUser = Annotated[User, Depends(require_admin)]


class ProductImageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    alt: str = ""
    sort: int = 0


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
    images: list[ProductImageOut] = Field(default_factory=list)


class ProductList(BaseModel):
    items: list[ProductCard]


def _validate_image_url(url_str: str) -> None:
    image = urlsplit(url_str)
    if not (
        (image.scheme == "https" and image.hostname and not image.username and not image.password)
        or (
            not image.scheme
            and not image.netloc
            and image.path.startswith("/static/img/")
            and ".." not in unquote(image.path).split("/")
        )
    ):
        raise ValueError("Ảnh phải là URL HTTPS hoặc đường dẫn trong /static/img/")


class ProductImageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(max_length=500)
    alt: str = Field(default="", max_length=200)
    sort: int = Field(default=0, ge=0)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        _validate_image_url(v)
        return v


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
    images: list[ProductImageIn] = Field(default_factory=list)

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
        _validate_image_url(self.image_url)
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
    product_data = data.model_dump(exclude={"images"})
    product = Product(**product_data)
    for idx, img in enumerate(data.images):
        product.images.append(
            ProductImage(
                url=img.url,
                alt=img.alt or product.name,
                sort=img.sort if img.sort else idx,
            )
        )
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
    product_data = data.model_dump(exclude={"images"})
    for key, value in product_data.items():
        setattr(product, key, value)

    product.images.clear()
    for idx, img in enumerate(data.images):
        product.images.append(
            ProductImage(
                product_id=product.id,
                url=img.url,
                alt=img.alt or product.name,
                sort=img.sort if img.sort else idx,
            )
        )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Slug hoặc mã SKU đã được sử dụng") from None
    db.refresh(product)
    return product


@admin_router.delete("/{product_id}")
def delete_product(product_id: int, user: AdminUser, db: DbSession):
    """Delete an existing product if it has not been ordered yet."""
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(404, "Không tìm thấy sản phẩm")

    has_orders = db.scalar(select(OrderItem.id).where(OrderItem.product_id == product_id).limit(1))
    if has_orders is not None:
        raise HTTPException(
            400,
            "Không thể xóa sản phẩm đã có trong đơn hàng. Bạn có thể chỉnh sửa số lượng tồn kho về 0 để ngừng bán.",
        )

    db.execute(delete(CartItem).where(CartItem.product_id == product_id))
    db.delete(product)
    db.commit()
    return {"detail": "Đã xóa sản phẩm thành công", "id": product_id}


@admin_router.post("/upload-image", include_in_schema=False)
async def upload_product_image(
    user: AdminUser,
    file: UploadFile = File(...),
):
    """Upload a product image from user's computer, convert to WebP, and return its static URL."""
    ext = Path(file.filename or "").suffix.lower()
    if not ext:
        ct = (file.content_type or "").lower()
        if "png" in ct:
            ext = ".png"
        elif "jpeg" in ct or "jpg" in ct:
            ext = ".jpg"
        elif "webp" in ct:
            ext = ".webp"
        elif "gif" in ct:
            ext = ".gif"
        elif "svg" in ct:
            ext = ".svg"
        else:
            ext = ".png"

    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            400, "Định dạng ảnh không hợp lệ (chỉ chấp nhận PNG, JPG, JPEG, WEBP, GIF, SVG)"
        )

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(400, "Dung lượng ảnh vượt quá giới hạn 10MB")
    if not content:
        raise HTTPException(400, "Tệp tải lên rỗng")

    upload_dir = ROOT / "app" / "static" / "img" / "products"
    upload_dir.mkdir(parents=True, exist_ok=True)

    if ext == ".svg":
        filename = f"prod_{secrets.token_hex(8)}.svg"
        file_path = upload_dir / filename
        file_path.write_bytes(content)
        return {
            "url": f"/static/img/products/{filename}",
            "filename": filename,
        }

    try:
        img = Image.open(io.BytesIO(content))
        out_buf = io.BytesIO()
        if getattr(img, "is_animated", False):
            img.save(out_buf, format="WEBP", save_all=True)
        else:
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                img = img.convert("RGBA")
            elif img.mode != "RGB":
                img = img.convert("RGB")
            img.save(out_buf, format="WEBP", quality=85, method=4)
        webp_bytes = out_buf.getvalue()
    except Exception:
        raise HTTPException(400, "Tệp ảnh không hợp lệ hoặc bị hỏng")

    filename = f"prod_{secrets.token_hex(8)}.webp"
    file_path = upload_dir / filename
    file_path.write_bytes(webp_bytes)

    return {
        "url": f"/static/img/products/{filename}",
        "filename": filename,
    }


@admin_router.get("/library-images", include_in_schema=False)
def list_library_images(user: AdminUser):
    """List available stock and uploaded product images for visual selection."""
    upload_dir = ROOT / "app" / "static" / "img" / "products"
    if not upload_dir.exists():
        return {"items": []}
    files = []
    for f in sorted(upload_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in ALLOWED_UPLOAD_EXTENSIONS:
            name_clean = f.stem.replace("-", " ").replace("_", " ").title()
            files.append(
                {
                    "url": f"/static/img/products/{f.name}",
                    "name": name_clean,
                    "filename": f.name,
                }
            )
    return {"items": files}

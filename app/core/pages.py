import json
import unicodedata
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.core.config import ROOT, get_settings
from app.core.deps import DbSession, get_current_user, require_admin, require_staff
from app.core.security import issue_csrf
from app.models.product import Product


def format_vnd(value: int) -> str:
    """Format a VND amount like the storefront JS: `185.000` (vi-VN grouping)."""
    return f"{int(value):,.0f}".replace(",", ".")


templates = Jinja2Templates(directory=ROOT / "app/templates")
templates.env.filters["vnd"] = format_vnd
router = APIRouter(include_in_schema=False)

SITE_NAME = "ElectroHub"
# Facebook/X do not render SVG attachments, so social cards always point at a
# raster image. Keep these in sync with `og-default.png` in app/static/img.
DEFAULT_OG_IMAGE = "/static/img/og-default.png"
DEFAULT_OG_IMAGE_WIDTH = 1200
DEFAULT_OG_IMAGE_HEIGHT = 630
OG_RASTER_TYPES = {"png", "jpg", "jpeg", "webp"}
# These two pages list products; they are rendered on the server so crawlers see
# product links without executing JavaScript, then store.js re-renders the same
# markup for client-side filtering.
CATALOG_TEMPLATES = {"index.html", "product/list.html"}
PAGE_TEMPLATES = {
    "/": "index.html",
    "/collections/all": "product/list.html",
    "/cart": "cart/cart.html",
    "/checkout": "cart/checkout.html",
    "/payments/{code}": "cart/payment.html",
    "/cart/tracking": "cart/tracking.html",
    "/account/login": "auth/login.html",
    "/account/register": "auth/register.html",
    "/account/orders": "account/orders.html",
    "/blogs/all": "blog/list.html",
    "/blogs/{slug}": "blog/detail.html",
    "/manager": "admin/dashboard.html",
    "/admin/products": "admin/products.html",
    "/admin/orders": "admin/orders.html",
    "/admin/newsletter": "admin/newsletter.html",
    "/staff/orders": "admin/orders.html",
}
PAGE_META = {
    "/": (
        "ElectroHub | Thiết bị điện tử và linh kiện",
        "Tìm bo mạch, cảm biến và linh kiện điện tử cho dự án của bạn tại ElectroHub.",
    ),
    "/collections/all": (
        "Sản phẩm điện tử và linh kiện | ElectroHub",
        "Xem giá, tình trạng kho và thông tin sản phẩm điện tử tại ElectroHub.",
    ),
    "/cart": ("Giỏ hàng | ElectroHub", "Kiểm tra sản phẩm và số lượng trong giỏ hàng ElectroHub."),
    "/checkout": (
        "Đặt hàng | ElectroHub",
        "Nhập thông tin giao hàng và chọn phương thức thanh toán.",
    ),
    "/account/login": ("Đăng nhập | ElectroHub", "Đăng nhập tài khoản ElectroHub."),
    "/account/register": (
        "Tạo tài khoản | ElectroHub",
        "Đăng ký tài khoản ElectroHub để đặt hàng.",
    ),
    "/account/orders": ("Đơn hàng của tôi | ElectroHub", "Lịch sử đơn hàng ElectroHub của bạn."),
    "/manager": ("Tổng quan cửa hàng | ElectroHub", "Khu vực quản lý cửa hàng ElectroHub."),
    "/staff/orders": ("Xử lý đơn hàng | ElectroHub", "Danh sách và trạng thái đơn hàng."),
}


MAX_DESCRIPTION = 160


def _json_ld(data) -> str:
    """Serialize JSON-LD so product content cannot break out of the script tag."""
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def _truncate(text: str, limit: int = MAX_DESCRIPTION) -> str:
    """Cut at a word boundary so the meta description never ends mid-word."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;·-–")


def social_image(image_url: str | None, base: str, alt: str) -> dict:
    """Absolute Open Graph image, falling back to a raster card for SVG/missing art.

    Facebook, Messenger and X only render raster images, so a product that still
    uses the SVG placeholder must share the branded PNG instead of a blank card.
    """
    image = (image_url or "").strip() or DEFAULT_OG_IMAGE
    if not image.startswith(("http://", "https://")):
        image = f"{base}{image}"
    suffix = urlsplit(image).path.rsplit(".", 1)[-1].lower()
    if suffix not in OG_RASTER_TYPES:
        image = f"{base}{DEFAULT_OG_IMAGE}"
        suffix = "png"
    content_type = "image/jpeg" if suffix in {"jpg", "jpeg"} else f"image/{suffix}"
    context = {
        "page_image": image,
        "page_image_type": content_type,
        "page_image_alt": alt,
    }
    if image == f"{base}{DEFAULT_OG_IMAGE}":
        context["page_image_width"] = DEFAULT_OG_IMAGE_WIDTH
        context["page_image_height"] = DEFAULT_OG_IMAGE_HEIGHT
    return context


def site_structured_data() -> str:
    """WebSite + Organization for every storefront page (sitewide JSON-LD)."""
    settings = get_settings()
    base = settings.site_url.rstrip("/")
    website = {
        "@type": "WebSite",
        "name": SITE_NAME,
        "url": f"{base}/",
        "inLanguage": "vi",
        "potentialAction": {
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": f"{base}/collections/all?q={{search_term_string}}",
            },
            "query-input": "required name=search_term_string",
        },
    }
    organization = {
        "@type": "Organization",
        "name": SITE_NAME,
        "url": f"{base}/",
        "logo": f"{base}/static/img/favicon-180.png",
        "inLanguage": "vi",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": settings.store_address,
            "addressLocality": "Tân Hưng",
            "addressRegion": "Hồ Chí Minh",
            "addressCountry": "VN",
        },
    }
    same_as = [url for url in (settings.facebook_page_url, settings.zalo_page_url) if url]
    if same_as:
        organization["sameAs"] = same_as
    return _json_ld({"@context": "https://schema.org", "@graph": [website, organization]})


def product_offer_price(product: Product) -> int:
    """Price shown on the page: sale price when present, list price otherwise."""
    return product.sale_price if product.sale_price is not None else product.price


def product_page_title(product: Product) -> str:
    """Keyword-rich title kept inside the ~65 characters Google usually shows."""
    suffix = " | Giá tốt tại ElectroHub"
    name = _truncate(product.name.strip(), 70 - len(suffix)) or product.sku
    return f"{name}{suffix}"


def product_meta_description(product: Product) -> str:
    text = " ".join((product.description or "").split())
    price_line = (
        f"Giá {format_vnd(product_offer_price(product))}₫ · "
        f"{'Còn hàng' if product.stock > 0 else 'Tạm hết hàng'} tại {SITE_NAME}."
    )
    if not text:
        return _truncate(f"Mua {product.name} (SKU {product.sku}) — {price_line}")
    if len(text) + len(price_line) + 1 <= MAX_DESCRIPTION:
        return f"{text} {price_line}"
    return _truncate(text)


def product_structured_data(product: Product) -> str:
    """Product + Offer + BreadcrumbList JSON-LD for the product detail page."""
    base = get_settings().site_url.rstrip("/")
    url = f"{base}/products/{product.slug}"
    image = (
        product.image_url
        if product.image_url.startswith(("http://", "https://"))
        else f"{base}{product.image_url}"
    )
    if getattr(product, "images", None):
        images = [
            img.url if img.url.startswith(("http://", "https://")) else f"{base}{img.url}"
            for img in product.images
        ]
        if image not in images:
            images.insert(0, image)
    else:
        images = [image]
    offer = {
        "@type": "Offer",
        "priceCurrency": "VND",
        "price": str(product_offer_price(product)),
        "availability": "https://schema.org/InStock"
        if product.stock > 0
        else "https://schema.org/OutOfStock",
        "itemCondition": "https://schema.org/NewCondition",
        "url": url,
    }
    breadcrumb = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Trang chủ", "item": f"{base}/"},
            {
                "@type": "ListItem",
                "position": 2,
                "name": "Sản phẩm",
                "item": f"{base}/collections/all",
            },
            {"@type": "ListItem", "position": 3, "name": product.name, "item": url},
        ],
    }
    description = " ".join((product.description or "").split())
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Product",
                "name": product.name,
                "sku": product.sku,
                "url": url,
                "image": images,
                "description": description or product_meta_description(product),
                "offers": offer,
            },
            breadcrumb,
        ],
    }
    return _json_ld(data)


def _normalize(value: str) -> str:
    """Match the storefront search: case-, accent- and đ-insensitive."""
    value = unicodedata.normalize("NFD", value.casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return value.replace("đ", "d")


# ponytail: cache template readiness check to avoid synchronous disk read_text() on every request
@lru_cache(maxsize=64)
def _is_template_ready(root_path: Path, template_name: str) -> bool:
    target = root_path / "app/templates" / template_name
    return target.exists() and bool(target.read_text().strip())


def catalog_context(request: Request, db: DbSession) -> dict:
    """Server-side product list for the home and catalog pages.

    Mirrors `/api/v1/products` plus the `q` and `sale` filters store.js applies,
    so the first paint already contains the links and prices crawlers index.
    """
    stmt = select(Product).order_by(Product.name, Product.id)
    # ponytail: push sale filter directly to DB query when active
    if request.query_params.get("sale") == "1":
        stmt = stmt.where(Product.sale_price.is_not(None), Product.sale_price < Product.price)
    products = list(db.scalars(stmt).all())
    query = " ".join(request.query_params.get("q", "").split())
    if query:
        needle = _normalize(query)
        products = [
            product for product in products if needle in _normalize(f"{product.name} {product.sku}")
        ]
    return {"products": products, "product_count": len(products)}


def page_endpoint(template_name: str):
    def page(request: Request, db: DbSession):
        # P4 owns the templates; surface unfinished pages instead of a blank 200 response.
        # ponytail: use cached readiness check instead of reading template file from disk every hit
        if not _is_template_ready(ROOT, template_name):
            return HTMLResponse(
                '<!doctype html><html lang="vi"><meta charset="utf-8">'
                "<title>ElectroHub</title><h1>Giao diện đang được xây dựng</h1>"
                '<p>API và tài liệu: <a href="/docs">Swagger UI</a>.</p></html>',
                status_code=503,
            )
        cookie_response = HTMLResponse()
        csrf_token = issue_csrf(request, cookie_response)
        page_title, page_description = PAGE_META.get(
            request.url.path,
            (
                "ElectroHub | Thiết bị điện tử và linh kiện",
                "Mua thiết bị điện tử và linh kiện tại ElectroHub.",
            ),
        )
        context = {
            "csrf_token": csrf_token,
            "site_url": get_settings().site_url.rstrip("/"),
            "payment_mode": get_settings().payment_mode,
            "vat_percent": get_settings().vat_percent,
            "paypal_vnd_per_usd": get_settings().paypal_vnd_per_usd,
            "facebook_page_url": get_settings().facebook_page_url,
            "zalo_page_url": get_settings().zalo_page_url,
            "subiz_embed_code": get_settings().subiz_embed_code,
            "tawkto_embed_code": get_settings().tawkto_embed_code,
            "tawkto_property_id": get_settings().tawkto_property_id,
            "tawkto_widget_id": get_settings().tawkto_widget_id,
            "store_address": get_settings().store_address,
            "google_maps_embed_url": get_settings().google_maps_embed_url,
            "google_maps_direct_url": get_settings().google_maps_direct_url,
            "page_title": page_title,
            "page_description": page_description,
            **social_image(
                None,
                get_settings().site_url.rstrip("/"),
                "ElectroHub - thiết bị điện tử và linh kiện",
            ),
            "canonical_url": f"{get_settings().site_url.rstrip('/')}{request.url.path}",
            "page_type": "website",
            "site_json_ld": site_structured_data(),
            "tracking_code": request.query_params.get("code", ""),
            "robots_policy": "noindex,follow"
            if request.url.path.startswith(
                (
                    "/cart",
                    "/checkout",
                    "/payments",
                    "/account",
                    "/admin",
                    "/manager",
                    "/staff",
                    "/newsletter/unsubscribe",
                )
            )
            else "index,follow",
            **request.path_params,
        }
        if template_name in CATALOG_TEMPLATES:
            context.update(catalog_context(request, db))
        response = templates.TemplateResponse(
            request=request,
            name=template_name,
            context=context,
        )
        response.headers["set-cookie"] = cookie_response.headers["set-cookie"]
        response.headers["Cache-Control"] = "no-store"
        return response

    return page


for path, template_name in PAGE_TEMPLATES.items():
    page_dependency = (
        require_admin
        if path.startswith(("/manager", "/admin/"))
        else require_staff
        if path.startswith("/staff/")
        else get_current_user
        if path.startswith("/payments/")
        else None
    )
    router.add_api_route(
        path,
        page_endpoint(template_name),
        methods=["GET"],
        response_class=HTMLResponse,
        name=path.strip("/").replace("/", "_") or "home",
        dependencies=[Depends(page_dependency)] if page_dependency else [],
    )


@router.get("/products/{slug}", response_class=HTMLResponse, name="product_detail")
def product_detail(slug: str, request: Request, db: DbSession):
    product = db.scalar(select(Product).where(Product.slug == slug))
    if product is None:
        raise HTTPException(404, "Không tìm thấy sản phẩm")
    cookie_response = HTMLResponse()
    csrf_token = issue_csrf(request, cookie_response)
    base = get_settings().site_url.rstrip("/")
    response = templates.TemplateResponse(
        request=request,
        name="product/detail.html",
        context={
            "csrf_token": csrf_token,
            "site_url": base,
            "facebook_page_url": get_settings().facebook_page_url,
            "zalo_page_url": get_settings().zalo_page_url,
            "subiz_embed_code": get_settings().subiz_embed_code,
            "tawkto_embed_code": get_settings().tawkto_embed_code,
            "tawkto_property_id": get_settings().tawkto_property_id,
            "tawkto_widget_id": get_settings().tawkto_widget_id,
            "store_address": get_settings().store_address,
            "google_maps_embed_url": get_settings().google_maps_embed_url,
            "google_maps_direct_url": get_settings().google_maps_direct_url,
            "product": product,
            "page_title": product_page_title(product),
            "page_description": product_meta_description(product),
            "page_type": "product",
            "site_json_ld": site_structured_data(),
            "product_json_ld": product_structured_data(product),
            **social_image(product.image_url, base, product.name),
            "canonical_url": f"{base}/products/{product.slug}",
        },
    )
    response.headers["set-cookie"] = cookie_response.headers["set-cookie"]
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get(
    "/newsletter/unsubscribe", response_class=HTMLResponse, name="newsletter_unsubscribe_page"
)
def newsletter_unsubscribe_page(request: Request, token: str):
    cookie_response = HTMLResponse()
    csrf_token = issue_csrf(request, cookie_response)
    response = templates.TemplateResponse(
        request=request,
        name="newsletter/unsubscribe.html",
        context={
            "csrf_token": csrf_token,
            "token": token,
            "site_url": get_settings().site_url.rstrip("/"),
            "store_address": get_settings().store_address,
            "google_maps_embed_url": get_settings().google_maps_embed_url,
            "google_maps_direct_url": get_settings().google_maps_direct_url,
            "page_title": "Hủy nhận email | ElectroHub",
            "page_description": "Hủy đăng ký nhận email marketing.",
            "robots_policy": "noindex,follow",
            **social_image(None, get_settings().site_url.rstrip("/"), SITE_NAME),
            "canonical_url": f"{get_settings().site_url.rstrip('/')}/newsletter/unsubscribe",
            "site_json_ld": site_structured_data(),
        },
    )
    response.headers["set-cookie"] = cookie_response.headers["set-cookie"]
    return response


def not_found_response(request: Request):
    """HTML 404 with the store chrome so a removed product link still leads home."""
    cookie_response = HTMLResponse()
    csrf_token = issue_csrf(request, cookie_response)
    base = get_settings().site_url.rstrip("/")
    response = templates.TemplateResponse(
        request=request,
        name="404.html",
        status_code=404,
        context={
            "csrf_token": csrf_token,
            "site_url": base,
            "store_address": get_settings().store_address,
            "google_maps_embed_url": get_settings().google_maps_embed_url,
            "google_maps_direct_url": get_settings().google_maps_direct_url,
            "page_title": "Không tìm thấy trang | ElectroHub",
            "page_description": "Trang bạn tìm không tồn tại hoặc sản phẩm đã được thay thế.",
            "robots_policy": "noindex,follow",
            "canonical_url": f"{base}{request.url.path}",
            "page_type": "website",
            **social_image(None, base, SITE_NAME),
        },
    )
    response.headers["set-cookie"] = cookie_response.headers["set-cookie"]
    return response

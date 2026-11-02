from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from app.core.config import ROOT, get_settings
from app.core.deps import DbSession, get_current_user, require_admin, require_staff
from app.core.security import issue_csrf
from app.models.product import Product

templates = Jinja2Templates(directory=ROOT / "app/templates")
router = APIRouter(include_in_schema=False)
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


def page_endpoint(template_name: str):
    def page(request: Request):
        # P4 owns the templates; surface unfinished pages instead of a blank 200 response.
        if not (ROOT / "app/templates" / template_name).read_text().strip():
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
        response = templates.TemplateResponse(
            request=request,
            name=template_name,
            context={
                "csrf_token": csrf_token,
                "site_url": get_settings().site_url.rstrip("/"),
                "facebook_page_url": get_settings().facebook_page_url,
                "zalo_page_url": get_settings().zalo_page_url,
                "subiz_embed_code": get_settings().subiz_embed_code,
                "page_title": page_title,
                "page_description": page_description,
                "page_image": (
                    f"{get_settings().site_url.rstrip('/')}/static/img/product-placeholder.svg"
                ),
                "page_image_alt": "ElectroHub - thiết bị điện tử và linh kiện",
                "canonical_url": f"{get_settings().site_url.rstrip('/')}{request.url.path}",
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
            },
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
        if path == "/account/orders" or path.startswith("/payments/")
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
            "product": product,
            "page_title": f"{product.name} | ElectroHub",
            "page_description": (product.description or f"Mua {product.name} tại ElectroHub.")[
                :160
            ],
            "page_image": f"{base}{product.image_url}"
            if product.image_url.startswith("/")
            else product.image_url,
            "page_image_alt": product.name,
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
            "page_title": "Hủy nhận email | ElectroHub",
            "page_description": "Hủy đăng ký nhận email marketing.",
            "page_image": (
                f"{get_settings().site_url.rstrip('/')}/static/img/product-placeholder.svg"
            ),
            "canonical_url": f"{get_settings().site_url.rstrip('/')}/newsletter/unsubscribe",
        },
    )
    response.headers["set-cookie"] = cookie_response.headers["set-cookie"]
    return response

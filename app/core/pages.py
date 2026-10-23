from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.core.config import ROOT
from app.core.deps import require_admin
from app.core.security import issue_csrf

templates = Jinja2Templates(directory=ROOT / "app/templates")
router = APIRouter(include_in_schema=False)
PAGE_TEMPLATES = {
    "/": "index.html",
    "/collections/all": "product/list.html",
    "/products/{slug}": "product/detail.html",
    "/cart": "cart/cart.html",
    "/checkout": "cart/checkout.html",
    "/cart/tracking": "cart/tracking.html",
    "/account/login": "auth/login.html",
    "/account/register": "auth/register.html",
    "/blogs/all": "blog/list.html",
    "/blogs/{slug}": "blog/detail.html",
    "/admin/products": "admin/products.html",
    "/admin/orders": "admin/orders.html",
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
        response = templates.TemplateResponse(
            request=request,
            name=template_name,
            context={"csrf_token": csrf_token, **request.path_params},
        )
        response.headers["set-cookie"] = cookie_response.headers["set-cookie"]
        response.headers["Cache-Control"] = "no-store"
        return response

    return page


for path, template_name in PAGE_TEMPLATES.items():
    router.add_api_route(
        path,
        page_endpoint(template_name),
        methods=["GET"],
        response_class=HTMLResponse,
        name=template_name.replace("/", "_"),
        dependencies=[Depends(require_admin)] if path.startswith("/admin/") else [],
    )

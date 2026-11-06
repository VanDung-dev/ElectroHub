import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from app.core.config import ROOT, get_settings
from app.core.database import get_engine
from app.core.deps import DbSession, require_csrf
from app.core.pages import router as pages_router
from app.models.product import Product
from app.routers.admin_orders import router as admin_orders_router
from app.routers.admin_refunds import router as admin_refunds_router
from app.routers.auth import router as auth_router
from app.routers.cart import router as cart_router
from app.routers.newsletter import router as newsletter_router
from app.routers.orders import router as orders_router
from app.routers.payment_returns import router as payment_returns_router
from app.routers.payments import router as payments_router
from app.routers.products import admin_router as admin_products_router
from app.routers.products import router as products_router
from app.schemas.auth import DetailResponse

logger = logging.getLogger("electrohub")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    yield
    if get_engine.cache_info().currsize:
        get_engine().dispose()
        get_engine.cache_clear()


def create_app() -> FastAPI:
    app = FastAPI(
        title="ElectroHub",
        lifespan=lifespan,
        dependencies=[Depends(require_csrf)],
        responses={422: {"model": DetailResponse}},
    )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else "Yêu cầu không hợp lệ"
        return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse({"detail": "Dữ liệu không hợp lệ"}, status_code=422)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        logger.error("Database request failed: %s", type(exc).__name__)
        return JSONResponse({"detail": "Dịch vụ dữ liệu chưa sẵn sàng"}, status_code=503)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.error("Request failed: %s", type(exc).__name__)
        return JSONResponse({"detail": "Lỗi hệ thống"}, status_code=500)

    @app.get("/api/v1/health", tags=["platform"], response_model=DetailResponse)
    def health(db: DbSession):
        db.execute(text("SELECT 1"))
        return DetailResponse(detail="ok")

    app.include_router(auth_router)
    app.include_router(cart_router)
    app.include_router(orders_router)
    app.include_router(admin_orders_router)
    app.include_router(admin_refunds_router)
    app.include_router(products_router)
    app.include_router(admin_products_router)
    app.include_router(newsletter_router)
    app.include_router(payments_router)
    app.include_router(payment_returns_router)
    app.include_router(pages_router)

    @app.get("/sitemap.xml", include_in_schema=False)
    def sitemap():
        with Session(get_engine()) as db:
            pages = ["/", "/collections/all"]
            pages.extend(f"/products/{slug}" for slug in db.scalars(select(Product.slug)).all())
        base = get_settings().site_url.rstrip("/")
        urls = "".join(f"<url><loc>{base}{path}</loc></url>" for path in pages)
        return Response(
            f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
            media_type="application/xml",
        )

    @app.get("/robots.txt", include_in_schema=False)
    def robots():
        return Response(
            "User-agent: *\nAllow: /\nDisallow: /admin/\nDisallow: /manager\nDisallow: /staff/\n"
            f"Sitemap: {get_settings().site_url.rstrip('/')}/sitemap.xml\n",
            media_type="text/plain",
        )

    app.mount("/static", StaticFiles(directory=ROOT / "app/static"), name="static")
    return app


app = create_app()

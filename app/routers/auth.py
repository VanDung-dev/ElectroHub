from fastapi import APIRouter, Request, Response

from app.core.deps import CurrentUser, DbSession
from app.core.security import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    clear_cookie,
    create_access_token,
    set_cookie,
)
from app.core.security import issue_csrf as set_csrf_cookie
from app.schemas.auth import (
    CsrfResponse,
    DetailResponse,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from app.services.auth_service import authenticate, create_user

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"],
    responses={401: {"model": DetailResponse}, 403: {"model": DetailResponse}},
)


@router.get("/csrf", response_model=CsrfResponse)
def csrf(request: Request, response: Response):
    return CsrfResponse(csrf_token=set_csrf_cookie(request, response))


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=201,
    responses={409: {"model": DetailResponse}},
)
def register(data: RegisterRequest, db: DbSession):
    return create_user(db, data)


@router.post("/login", response_model=UserResponse)
def login(data: LoginRequest, response: Response, db: DbSession):
    user = authenticate(db, data)
    set_cookie(response, ACCESS_COOKIE, create_access_token(user.id))
    clear_cookie(response, CSRF_COOKIE)
    return user


@router.post("/logout", response_model=DetailResponse)
def logout(response: Response):
    # shortcut: JWTs expire naturally; add server-side revocation before production sessions.
    clear_cookie(response, ACCESS_COOKIE)
    clear_cookie(response, CSRF_COOKIE)
    response.headers["Cache-Control"] = "no-store"
    return DetailResponse(detail="Đã đăng xuất")


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return user

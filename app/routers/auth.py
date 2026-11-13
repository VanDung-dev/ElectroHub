from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select

from app.core.deps import CurrentUser, DbSession, require_admin
from app.core.security import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    clear_cookie,
    create_access_token,
    hash_password,
    set_cookie,
    verify_password,
)
from app.core.security import issue_csrf as set_csrf_cookie
from app.models.newsletter import NewsletterSubscriber
from app.models.user import User
from app.schemas.auth import (
    CsrfResponse,
    DetailResponse,
    LoginRequest,
    RegisterRequest,
    ToggleUserBlockRequest,
    UpdateProfileRequest,
    UpdateUserRoleRequest,
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
    is_sub = (
        db.scalar(
            select(NewsletterSubscriber.id).where(
                NewsletterSubscriber.email == user.email.lower()
            )
        )
        is not None
    )
    resp = UserResponse.model_validate(user)
    resp.is_subscribed_newsletter = is_sub
    return resp


@router.post("/logout", response_model=DetailResponse)
def logout(response: Response):
    # shortcut: JWTs expire naturally; add server-side revocation before production sessions.
    clear_cookie(response, ACCESS_COOKIE)
    clear_cookie(response, CSRF_COOKIE)
    response.headers["Cache-Control"] = "no-store"
    return DetailResponse(detail="Đã đăng xuất")


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser, response: Response, db: DbSession):
    response.headers["Cache-Control"] = "no-store"
    is_sub = (
        db.scalar(
            select(NewsletterSubscriber.id).where(
                NewsletterSubscriber.email == user.email.lower()
            )
        )
        is not None
    )
    resp = UserResponse.model_validate(user)
    resp.is_subscribed_newsletter = is_sub
    return resp


@router.put("/me", response_model=UserResponse, include_in_schema=False)
def update_profile(
    data: UpdateProfileRequest,
    user: CurrentUser,
    db: DbSession,
):
    clean_name = data.name.strip()
    if not clean_name:
        raise HTTPException(422, "Tên không được để trống")
    user.name = clean_name
    if data.new_password:
        if not data.current_password or not verify_password(
            data.current_password, user.password_hash
        ):
            raise HTTPException(400, "Mật khẩu hiện tại không chính xác")
        if len(data.new_password) < 8:
            raise HTTPException(400, "Mật khẩu mới phải có tối thiểu 8 ký tự")
        user.password_hash = hash_password(data.new_password)

    user_email = user.email.lower()
    if data.is_subscribed_newsletter is not None:
        sub = db.scalar(
            select(NewsletterSubscriber).where(NewsletterSubscriber.email == user_email)
        )
        if data.is_subscribed_newsletter:
            if not sub:
                db.add(NewsletterSubscriber(email=user_email))
        else:
            if sub:
                db.delete(sub)

    db.commit()
    db.refresh(user)

    is_sub = (
        db.scalar(
            select(NewsletterSubscriber.id).where(
                NewsletterSubscriber.email == user_email
            )
        )
        is not None
    )
    resp = UserResponse.model_validate(user)
    resp.is_subscribed_newsletter = is_sub
    return resp


@router.get("/admin/users", include_in_schema=False, dependencies=[Depends(require_admin)])
def list_users(db: DbSession):
    users = db.scalars(select(User).order_by(User.id.asc())).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "role": u.role,
            "is_blocked": bool(u.is_blocked),
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]


@router.patch(
    "/admin/users/{user_id}/role", include_in_schema=False, dependencies=[Depends(require_admin)]
)
def update_user_role(user_id: int, data: UpdateUserRoleRequest, db: DbSession, admin: CurrentUser):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Không tìm thấy người dùng")
    if user.id == admin.id:
        raise HTTPException(400, "Không thể tự thay đổi vai trò của chính mình")
    user.role = data.role
    db.commit()
    db.refresh(user)
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "is_blocked": bool(user.is_blocked),
        "created_at": user.created_at.isoformat(),
    }


@router.patch(
    "/admin/users/{user_id}/block", include_in_schema=False, dependencies=[Depends(require_admin)]
)
def toggle_user_block(
    user_id: int, data: ToggleUserBlockRequest, db: DbSession, admin: CurrentUser
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Không tìm thấy người dùng")
    if user.id == admin.id:
        raise HTTPException(400, "Không thể tự khóa tài khoản của chính mình")
    user.is_blocked = data.is_blocked
    db.commit()
    db.refresh(user)
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "is_blocked": bool(user.is_blocked),
        "created_at": user.created_at.isoformat(),
    }


@router.get("/admin/revenue", include_in_schema=False, dependencies=[Depends(require_admin)])
def get_revenue_report(
    db: DbSession,
    period_type: str = "month",
    year: int | None = None,
    month: int | None = None,
    quarter: int | None = None,
):
    from app.services.revenue_service import get_revenue_analytics

    return get_revenue_analytics(
        db, period_type=period_type, year=year, month=month, quarter=quarter
    )


@router.get("/admin/revenue/export", include_in_schema=False, dependencies=[Depends(require_admin)])
def export_revenue_report(
    db: DbSession,
    period_type: str = "month",
    year: int | None = None,
    month: int | None = None,
    quarter: int | None = None,
):
    from app.services.revenue_service import generate_revenue_csv

    csv_text, filename = generate_revenue_csv(
        db, period_type=period_type, year=year, month=month, quarter=quarter
    )
    content = "\ufeff" + csv_text
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )


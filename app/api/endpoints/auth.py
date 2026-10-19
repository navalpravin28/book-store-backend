from fastapi import APIRouter, Depends, Request, Response

from app.core.db import get_db
from app.core.middleware import limiter
from app.core.security import get_current_user
from app.core.utils import serialize_doc
from app.schema.userSchema import (
    ChangePasswordSchema,
    LoginSchema,
    RegisterSchema,
    TokenResponse,
    UserResponse,
)
from app.services.authService import AuthService
from app.core.security import require_admin
router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=201, summary="Create a viewer account")
@limiter.limit("5/minute")
async def register(request: Request, payload: RegisterSchema, db=Depends(get_db)):
    user = await AuthService(db).register(payload)
    return serialize_doc(user)


@router.post("/login", response_model=TokenResponse, summary="Login with email + password")
@limiter.limit("10/minute")
async def login(request: Request, payload: LoginSchema, db=Depends(get_db)):
    token, expires_at, user = await AuthService(db).login(payload)
    return TokenResponse(accessToken=token, expiresAt=expires_at, user=UserResponse(**serialize_doc(user)))


@router.post("/logout", status_code=204, summary="Revoke the current token")
async def logout(user: dict = Depends(get_current_user), db=Depends(get_db)):
    await AuthService(db).logout(user)
    return Response(status_code=204)


@router.post("/change-password", status_code=204, summary="Change password (invalidates all old tokens)")
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    payload: ChangePasswordSchema,
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    await AuthService(db).change_password(user, payload)
    return Response(status_code=204)

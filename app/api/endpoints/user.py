from fastapi import APIRouter, Depends, Query

from app.core.db import get_db
from app.core.security import get_current_user, require_admin
from app.core.utils import serialize_doc
from app.schema.commonSchema import ObjectIdStr, Paginated
from app.schema.userSchema import UserResponse, UserStatusSchema, UserUpdateSchema
from app.services.userService import UserService

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_me(user: dict = Depends(get_current_user)):
    return serialize_doc(user)


@router.put("/me", response_model=UserResponse)
async def update_me(payload: UserUpdateSchema, user: dict = Depends(get_current_user), db=Depends(get_db)):
    return serialize_doc(await UserService(db).update_me(user["id"], payload.name))


# ---- admin only ----
@router.get("", response_model=Paginated[UserResponse], summary="[Admin] List users")
async def list_users(
    page: int = Query(1, ge=1, le=100000),
    limit: int = Query(20, ge=1, le=100),
    role: str | None = Query(None, pattern="^(admin|viewer)$"),
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    return serialize_doc(await UserService(db).list_users(page, limit, role))


@router.patch("/{user_id}/status", response_model=UserResponse, summary="[Admin] Enable / disable a viewer")
async def set_user_status(
    user_id: ObjectIdStr,
    payload: UserStatusSchema,
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    return serialize_doc(await UserService(db).set_status(admin, user_id, payload.isActive))

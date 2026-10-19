from fastapi import APIRouter, Depends, File, Request, UploadFile

from app.core.db import get_db
from app.core.exception import ForbiddenException
from app.core.middleware import limiter
from app.core.security import get_current_user
from app.models.userModel import UserRole
from app.schema.uploadSchema import UploadKind, UploadResponse
from app.services.uploadService import UploadService

router = APIRouter()


@router.post("/{kind}", response_model=UploadResponse, status_code=201,
             summary="Upload an image (books/categories: admin only, advertisements: any logged-in user)")
@limiter.limit("20/minute")
async def upload_image(
    request: Request,
    kind: UploadKind,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    if kind != "advertisements" and user["role"] != UserRole.ADMIN.value:
        raise ForbiddenException()
    return await UploadService().save_image(file, kind)

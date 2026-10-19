from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

from app.core.db import get_db
from app.core.security import require_admin, require_any_user
from app.core.utils import serialize_doc
from app.schema.advertisementSchema import (
    AdvertisementAdmin,
    AdvertisementCreate,
    AdvertisementMine,
    AdvertisementPublic,
    AdvertisementUpdate,
)
from app.schema.commonSchema import ObjectIdStr, Paginated
from app.services.advertisementService import AdvertisementService

router = APIRouter()


# ---------------- public: only ads that have not expired ----------------
@router.get("", response_model=Paginated[AdvertisementPublic], summary="Active advertisements")
async def list_active_ads(
    page: int = Query(1, ge=1, le=100000), limit: int = Query(20, ge=1, le=100), db=Depends(get_db)
):
    return serialize_doc(await AdvertisementService(db).list_public(page, limit))


# ---------------- logged-in viewer (or admin) ----------------
@router.get("/mine", response_model=Paginated[AdvertisementMine], summary="My advertisements (active + expired)")
async def list_my_ads(
    page: int = Query(1, ge=1, le=100000),
    limit: int = Query(20, ge=1, le=100),
    user: dict = Depends(require_any_user),
    db=Depends(get_db),
):
    return serialize_doc(await AdvertisementService(db).list_mine(user, page, limit))


@router.post("", response_model=AdvertisementMine, status_code=201, summary="Create an ad for 1, 2 or 3 days")
async def create_ad(payload: AdvertisementCreate, user: dict = Depends(require_any_user), db=Depends(get_db)):
    return serialize_doc(await AdvertisementService(db).create(payload, user))


@router.put("/{ad_id}", response_model=AdvertisementMine, summary="Update my ad (send durationDays to renew)")
async def update_ad(
    ad_id: ObjectIdStr, payload: AdvertisementUpdate, user: dict = Depends(require_any_user), db=Depends(get_db)
):
    return serialize_doc(await AdvertisementService(db).update(ad_id, payload, user))


@router.delete("/{ad_id}", status_code=204, summary="Delete my ad (admin can delete any)")
async def delete_ad(ad_id: ObjectIdStr, user: dict = Depends(require_any_user), db=Depends(get_db)):
    await AdvertisementService(db).delete(ad_id, user)
    return Response(status_code=204)


# ---------------- admin moderation ----------------
@router.get("/manage/all", response_model=Paginated[AdvertisementAdmin], summary="[Admin] All advertisements")
async def admin_list_ads(
    page: int = Query(1, ge=1, le=100000),
    limit: int = Query(20, ge=1, le=100),
    status: Literal["active", "expired"] | None = None,
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    return serialize_doc(await AdvertisementService(db).list_all(page, limit, status))

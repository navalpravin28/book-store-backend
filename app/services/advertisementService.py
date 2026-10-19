from datetime import timedelta

from pymongo import ReturnDocument

from app.core.config import settings
from app.core.exception import BadRequestException, ConflictException, NotFoundException
from app.core.utils import as_aware, to_object_id, utcnow
from app.models.userModel import UserRole
from app.schema.advertisementSchema import AdvertisementCreate, AdvertisementUpdate
from app.services.auditService import AuditService
from app.services.uploadService import UploadService


class AdvertisementService:
    def __init__(self, db):
        self.db = db
        self.col = db.advertisements
        self.audit = AuditService(db)

    @staticmethod
    def _present(doc: dict) -> dict:
        doc["status"] = "active" if as_aware(doc["expiresAt"]) > utcnow() else "expired"
        return doc

    @staticmethod
    def _is_admin(user: dict) -> bool:
        return user["role"] == UserRole.ADMIN.value

    async def _get_manageable(self, ad_id: str, user: dict) -> dict:
        """Owner or admin only. Others get 404 (not 403) so ad ids cannot be probed."""
        doc = await self.col.find_one({"_id": to_object_id(ad_id)})
        if not doc or (not self._is_admin(user) and doc["ownerId"] != user["id"]):
            raise NotFoundException("Advertisement not found")
        return doc

    # ---------------------------------------------------------------- create
    async def create(self, data: AdvertisementCreate, user: dict) -> dict:
        now = utcnow()
        if not self._is_admin(user):
            active = await self.col.count_documents({"ownerId": user["id"], "expiresAt": {"$gt": now}})
            if active >= settings.MAX_ACTIVE_ADS_PER_USER:
                raise ConflictException(
                    f"You can have at most {settings.MAX_ACTIVE_ADS_PER_USER} active advertisements"
                )
        doc = {
            "ownerId": user["id"],
            "ownerName": user["name"],
            "title": data.title,
            "description": data.description,
            "imageUrl": data.imageUrl,
            "linkUrl": data.linkUrl,
            "durationDays": data.durationDays,
            "startsAt": now,
            "expiresAt": now + timedelta(days=data.durationDays),
            "createdAt": now,
            "updatedAt": now,
        }
        result = await self.col.insert_one(doc)
        return self._present(await self.col.find_one({"_id": result.inserted_id}))

    # ------------------------------------------------------------------ read
    async def _page(self, query: dict, page: int, limit: int, sort_field: str = "startsAt") -> dict:
        total = await self.col.count_documents(query)
        cursor = self.col.find(query).sort(sort_field, -1).skip((page - 1) * limit).limit(limit)
        return {"items": [self._present(d) async for d in cursor], "total": total, "page": page, "limit": limit}

    async def list_public(self, page: int, limit: int) -> dict:
        # expired ads are filtered by the query itself, so they vanish exactly on time
        return await self._page({"expiresAt": {"$gt": utcnow()}}, page, limit)

    async def list_mine(self, user: dict, page: int, limit: int) -> dict:
        return await self._page({"ownerId": user["id"]}, page, limit)

    async def list_all(self, page: int, limit: int, status: str | None) -> dict:
        query: dict = {}
        if status == "active":
            query["expiresAt"] = {"$gt": utcnow()}
        elif status == "expired":
            query["expiresAt"] = {"$lte": utcnow()}
        return await self._page(query, page, limit)

    # ---------------------------------------------------------------- update
    async def update(self, ad_id: str, data: AdvertisementUpdate, user: dict) -> dict:
        existing = await self._get_manageable(ad_id, user)
        updates = {k: v for k, v in data.model_dump(exclude_unset=True).items()
                   if v is not None or k in ("imageUrl", "linkUrl")}
        now = utcnow()

        if "durationDays" in updates:  # renew / change the time limit
            updates["startsAt"] = now
            updates["expiresAt"] = now + timedelta(days=updates["durationDays"])
        elif as_aware(existing["expiresAt"]) <= now:
            raise BadRequestException("This advertisement has expired. Send durationDays to renew it")
        if not updates:
            raise BadRequestException("Nothing to update")
        updates["updatedAt"] = now

        doc = await self.col.find_one_and_update(
            {"_id": existing["_id"]}, {"$set": updates}, return_document=ReturnDocument.AFTER
        )
        if "imageUrl" in updates and existing.get("imageUrl") != updates["imageUrl"]:
            UploadService.delete_local(existing.get("imageUrl"))
        return self._present(doc)

    # ---------------------------------------------------------------- delete
    async def delete(self, ad_id: str, user: dict) -> None:
        existing = await self._get_manageable(ad_id, user)
        await self.col.delete_one({"_id": existing["_id"]})
        UploadService.delete_local(existing.get("imageUrl"))
        if self._is_admin(user) and existing["ownerId"] != user["id"]:
            await self.audit.log(user["id"], "advertisement.delete", "advertisement", ad_id)

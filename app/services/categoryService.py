from __future__ import annotations

import random

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.exception import ConflictException, NotFoundException
from app.core.utils import escape_regex, slugify, to_object_id, utcnow
from app.schema.categorySchema import CategoryCreate, CategoryUpdate
from app.services.auditService import AuditService
from app.services.uploadService import UploadService


CATEGORY_COLOR_PALETTES = (
    {"color": "#294C3B", "spineColor": "#1D362A", "textColor": "#FFF4D8", "accentColor": "#E9D7A5"},
    {"color": "#233B65", "spineColor": "#172744", "textColor": "#FFFFFF", "accentColor": "#7FD9E8"},
    {"color": "#493323", "spineColor": "#2E2017", "textColor": "#FFF4D8", "accentColor": "#D9B77C"},
    {"color": "#5B2C3A", "spineColor": "#3D1D27", "textColor": "#FFF4E8", "accentColor": "#E6B8A2"},
    {"color": "#3B6663", "spineColor": "#274542", "textColor": "#F4F7E8", "accentColor": "#D5DFA5"},
    {"color": "#3B3632", "spineColor": "#282522", "textColor": "#F5EFE6", "accentColor": "#C9A87C"},
)


class CategoryService:
    def __init__(self, db):
        self.db = db
        self.col = db.categories
        self.books = db.books
        self.audit = AuditService(db)

    async def _with_counts(self, docs: list[dict]) -> list[dict]:
        ids = [d["_id"] for d in docs]
        counts: dict = {}
        if ids:
            pipeline = [
                {"$match": {"categoryId": {"$in": ids}}},
                {"$group": {"_id": "$categoryId", "count": {"$sum": 1}}},
            ]
            async for row in self.books.aggregate(pipeline):
                counts[row["_id"]] = row["count"]
        for d in docs:
            d["bookCount"] = counts.get(d["_id"], 0)
        return docs

    async def create(self, data: CategoryCreate, actor_id: str) -> dict:
        now = utcnow()
        doc = {
            "categoryName": data.categoryName,
            "description": data.description,
            "imageUrl": data.imageUrl,
            "slug": slugify(data.categoryName),
            "categoryColors": random.choice(CATEGORY_COLOR_PALETTES).copy(),
            "createdAt": now,
            "updatedAt": now,
        }
        try:
            result = await self.col.insert_one(doc)
        except DuplicateKeyError:
            raise ConflictException("A category with this name already exists")
        await self.audit.log(actor_id, "category.create", "category", str(result.inserted_id))
        created = await self.col.find_one({"_id": result.inserted_id})
        return (await self._with_counts([created]))[0]

    async def list(self, page: int, limit: int, q: str | None) -> dict:
        query = {"categoryName": {"$regex": escape_regex(q), "$options": "i"}} if q else {}
        total = await self.col.count_documents(query)
        cursor = self.col.find(query).sort("categoryName", 1).skip((page - 1) * limit).limit(limit)
        docs = await self._with_counts([d async for d in cursor])
        return {"items": docs, "total": total, "page": page, "limit": limit}

    async def get_by_slug(self, slug: str) -> dict:
        doc = await self.col.find_one({"slug": slug})
        if not doc:
            raise NotFoundException("Category not found")
        return (await self._with_counts([doc]))[0]

    async def update(self, category_id: str, data: CategoryUpdate, actor_id: str) -> dict:
        oid = to_object_id(category_id)
        existing = await self.col.find_one({"_id": oid})
        if not existing:
            raise NotFoundException("Category not found")

        updates = data.model_dump(exclude_unset=True)
        if "categoryName" in updates and updates["categoryName"] is None:
            updates.pop("categoryName")
        if "description" in updates and updates["description"] is None:
            updates.pop("description")
        if "categoryName" in updates:
            updates["slug"] = slugify(updates["categoryName"])
        updates["updatedAt"] = utcnow()

        try:
            doc = await self.col.find_one_and_update(
                {"_id": oid}, {"$set": updates}, return_document=ReturnDocument.AFTER
            )
        except DuplicateKeyError:
            raise ConflictException("A category with this name already exists")

        if "imageUrl" in updates and existing.get("imageUrl") != updates["imageUrl"]:
            UploadService.delete_local(existing.get("imageUrl"))
        await self.audit.log(actor_id, "category.update", "category", category_id)
        return (await self._with_counts([doc]))[0]

    async def delete(self, category_id: str, actor_id: str) -> None:
        oid = to_object_id(category_id)
        if await self.books.count_documents({"categoryId": oid}, limit=1):
            raise ConflictException("Category still has books. Move or delete them first")
        doc = await self.col.find_one_and_delete({"_id": oid})
        if not doc:
            raise NotFoundException("Category not found")
        UploadService.delete_local(doc.get("imageUrl"))
        await self.audit.log(actor_id, "category.delete", "category", category_id, {"name": doc["categoryName"]})

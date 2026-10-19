import asyncio
import logging

from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.core.exception import ConflictException, ForbiddenException, NotFoundException
from app.core.security import hash_password
from app.core.utils import to_object_id, utcnow
from app.models.userModel import UserRole, new_user_document
from app.schema.userSchema import validate_password_strength
from app.services.auditService import AuditService

logger = logging.getLogger("bookstore")


class UserService:
    def __init__(self, db):
        self.db = db
        self.col = db.users
        self.audit = AuditService(db)

    async def create(self, name: str, email: str, password: str, role: UserRole = UserRole.VIEWER) -> dict:
        hashed = await asyncio.to_thread(hash_password, password)  # bcrypt is CPU heavy
        doc = new_user_document(name, email.lower(), hashed, role)
        try:
            result = await self.col.insert_one(doc)
        except DuplicateKeyError:
            raise ConflictException("Email is already registered")
        return await self.col.find_one({"_id": result.inserted_id})

    async def get(self, user_id: str) -> dict:
        user = await self.col.find_one({"_id": to_object_id(user_id)})
        if not user:
            raise NotFoundException("User not found")
        return user

    async def update_me(self, user_id: str, name: str) -> dict:
        await self.col.update_one({"_id": to_object_id(user_id)}, {"$set": {"name": name, "updatedAt": utcnow()}})
        return await self.get(user_id)

    async def list_users(self, page: int, limit: int, role: str | None = None) -> dict:
        query = {"role": role} if role in (UserRole.ADMIN.value, UserRole.VIEWER.value) else {}
        total = await self.col.count_documents(query)
        cursor = self.col.find(query, {"hashedPassword": 0}).sort("createdAt", -1).skip((page - 1) * limit).limit(limit)
        return {"items": [d async for d in cursor], "total": total, "page": page, "limit": limit}

    async def set_status(self, actor: dict, user_id: str, is_active: bool) -> dict:
        if user_id == actor["id"]:
            raise ForbiddenException("You cannot change your own status")
        user = await self.get(user_id)
        if user["role"] == UserRole.ADMIN.value:
            raise ForbiddenException("Admin accounts cannot be disabled from the API")
        await self.col.update_one(
            {"_id": user["_id"]},
            {"$set": {"isActive": is_active, "updatedAt": utcnow(), "failedLoginAttempts": 0, "lockUntil": None}},
        )
        await self.audit.log(actor["id"], "user.status", "user", user_id, {"isActive": is_active})
        return await self.get(user_id)

    async def seed_admin(self) -> None:
        """Creates the first admin from env vars if no admin exists yet."""
        if not (settings.ADMIN_EMAIL and settings.ADMIN_PASSWORD):
            return
        if await self.col.find_one({"role": UserRole.ADMIN.value}, {"_id": 1}):
            return
        validate_password_strength(settings.ADMIN_PASSWORD)  # fail fast on a weak bootstrap password
        await self.create(settings.ADMIN_NAME, settings.ADMIN_EMAIL, settings.ADMIN_PASSWORD, UserRole.ADMIN)
        logger.info("Seeded initial admin account")

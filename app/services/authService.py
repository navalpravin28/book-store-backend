import asyncio
from datetime import datetime, timedelta

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.core.exception import BadRequestException, TooManyRequestsException, UnauthorizedException
from app.core.security import (
    burn_password_check,
    create_access_token,
    hash_password,
    verify_password,
)
from app.core.utils import as_aware, utcnow
from app.models.userModel import UserRole
from app.schema.userSchema import ChangePasswordSchema, LoginSchema, RegisterSchema
from app.services.userService import UserService

GENERIC_LOGIN_ERROR = "Invalid email or password"


class AuthService:
    def __init__(self, db):
        self.db = db
        self.col = db.users
        self.users = UserService(db)

    async def register(self, payload: RegisterSchema) -> dict:
        # role is NEVER taken from the request - self-registration always creates a viewer
        return await self.users.create(payload.name, payload.email, payload.password, UserRole.VIEWER)

    async def login(self, payload: LoginSchema) -> tuple[str, datetime, dict]:
        email = payload.email.lower()
        now = utcnow()
        user = await self.col.find_one({"email": email})

        if not user:
            await asyncio.to_thread(burn_password_check, payload.password)  # constant-ish timing
            raise UnauthorizedException(GENERIC_LOGIN_ERROR)

        lock_until = as_aware(user.get("lockUntil"))
        if lock_until and lock_until > now:
            raise TooManyRequestsException("Account temporarily locked due to repeated failures. Try again later.")

        valid = await asyncio.to_thread(verify_password, payload.password, user["hashedPassword"])
        if not valid:
            await self._register_failure(user["_id"], now)
            raise UnauthorizedException(GENERIC_LOGIN_ERROR)
        if not user.get("isActive", False):
            raise UnauthorizedException(GENERIC_LOGIN_ERROR)

        await self.col.update_one(
            {"_id": user["_id"]},
            {"$set": {"failedLoginAttempts": 0, "lockUntil": None, "lastLoginAt": now}},
        )
        user["lastLoginAt"] = now
        token, expires = create_access_token(str(user["_id"]), user["role"])
        return token, expires, user

    async def _register_failure(self, user_id, now: datetime) -> None:
        updated = await self.col.find_one_and_update(
            {"_id": user_id},
            {"$inc": {"failedLoginAttempts": 1}},
            return_document=ReturnDocument.AFTER,
        )
        if updated and updated.get("failedLoginAttempts", 0) >= settings.MAX_LOGIN_ATTEMPTS:
            await self.col.update_one(
                {"_id": user_id},
                {"$set": {"lockUntil": now + timedelta(minutes=settings.LOCKOUT_MINUTES), "failedLoginAttempts": 0}},
            )

    async def logout(self, user: dict) -> None:
        try:
            await self.db.revokedTokens.insert_one({"jti": user["jti"], "expiresAt": user["tokenExp"]})
        except DuplicateKeyError:
            pass

    async def change_password(self, user: dict, payload: ChangePasswordSchema) -> None:
        if not await asyncio.to_thread(verify_password, payload.currentPassword, user["hashedPassword"]):
            raise UnauthorizedException("Current password is incorrect")
        if payload.currentPassword == payload.newPassword:
            raise BadRequestException("New password must be different from the current password")
        hashed = await asyncio.to_thread(hash_password, payload.newPassword)
        now = utcnow()
        # passwordChangedAt invalidates every token issued before this moment
        await self.col.update_one(
            {"_id": user["_id"]},
            {"$set": {"hashedPassword": hashed, "passwordChangedAt": now, "updatedAt": now}},
        )

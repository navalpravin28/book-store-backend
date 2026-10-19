import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from bson import ObjectId
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.db import get_db
from app.core.exception import ForbiddenException, UnauthorizedException
from app.core.utils import as_aware
from app.models.userModel import UserRole

bearer_scheme = HTTPBearer(auto_error=False)

# Used to burn the same CPU time when the e-mail does not exist (stops user enumeration by timing)
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password-for-timing", bcrypt.gensalt(rounds=12))


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


def burn_password_check(plain: str) -> None:
    try:
        bcrypt.checkpw(plain.encode(), _DUMMY_HASH)
    except ValueError:
        pass


# --------------------------------------------------------------------- JWT
def create_access_token(user_id: str, role: str) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "role": role,
        "jti": uuid.uuid4().hex,
        "type": "access",
        "iat": now,
        "exp": expires,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM), expires


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],  # pinned: blocks alg=none / alg confusion
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
            options={"require": ["exp", "iat", "sub", "jti"]},
        )
    except jwt.PyJWTError:
        raise UnauthorizedException("Invalid or expired token")


# ------------------------------------------------------- auth dependencies
async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db=Depends(get_db),
) -> dict:
    """
    Resolves the caller from the Bearer token. The role is always read from the
    database (not trusted from the token), so demoting/disabling a user takes
    effect immediately.
    """
    if credentials is None:
        raise UnauthorizedException("Authentication required")

    payload = decode_token(credentials.credentials)
    if payload.get("type") != "access":
        raise UnauthorizedException("Invalid or expired token")

    if await db.revokedTokens.find_one({"jti": payload["jti"]}, {"_id": 1}):
        raise UnauthorizedException("Token has been revoked")

    sub = payload["sub"]
    if not isinstance(sub, str) or not ObjectId.is_valid(sub):
        raise UnauthorizedException("Invalid or expired token")

    user = await db.users.find_one({"_id": ObjectId(sub)})
    if not user or not user.get("isActive", False):
        raise UnauthorizedException("Invalid or expired token")

    changed_at = as_aware(user.get("passwordChangedAt"))
    if changed_at and payload["iat"] < int(changed_at.timestamp()):
        raise UnauthorizedException("Session expired, please log in again")

    user["id"] = str(user["_id"])
    user["jti"] = payload["jti"]
    user["tokenExp"] = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    return user


def require_roles(*roles: UserRole):
    allowed = {r.value for r in roles}

    async def checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed:
            raise ForbiddenException()
        return user

    return checker


require_admin = require_roles(UserRole.ADMIN)
require_any_user = require_roles(UserRole.ADMIN, UserRole.VIEWER)

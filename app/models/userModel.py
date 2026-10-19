from datetime import datetime, timezone
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    VIEWER = "viewer"


def new_user_document(name: str, email: str, hashed_password: str, role: UserRole = UserRole.VIEWER) -> dict:
    """Single place that defines how a user document looks in MongoDB."""
    now = datetime.now(timezone.utc)
    return {
        "name": name,
        "email": email,
        "hashedPassword": hashed_password,
        "role": role.value,
        "isActive": True,
        "failedLoginAttempts": 0,
        "lockUntil": None,
        "lastLoginAt": None,
        "passwordChangedAt": None,
        "createdAt": now,
        "updatedAt": now,
    }

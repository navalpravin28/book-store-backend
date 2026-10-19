import re
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field

from app.schema.commonSchema import SafeText, StrictModel


def validate_password_strength(v: str) -> str:
    if len(v.encode()) > 72:
        raise ValueError("Password is too long")
    problems = []
    if not re.search(r"[a-z]", v):
        problems.append("a lowercase letter")
    if not re.search(r"[A-Z]", v):
        problems.append("an uppercase letter")
    if not re.search(r"\d", v):
        problems.append("a digit")
    if not re.search(r"[^\w\s]", v):
        problems.append("a special character")
    if problems:
        raise ValueError("Password must contain " + ", ".join(problems))
    return v


StrongPassword = Annotated[
    str, Field(min_length=8, max_length=64), AfterValidator(validate_password_strength)
]


class RegisterSchema(StrictModel):
    name: SafeText = Field(min_length=2, max_length=80)
    email: EmailStr
    password: StrongPassword


class LoginSchema(StrictModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordSchema(StrictModel):
    currentPassword: str = Field(min_length=1, max_length=128)
    newPassword: StrongPassword


class UserUpdateSchema(StrictModel):
    name: SafeText = Field(min_length=2, max_length=80)


class UserStatusSchema(StrictModel):
    isActive: bool


class UserResponse(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: str
    isActive: bool = True
    createdAt: datetime | None = None
    lastLoginAt: datetime | None = None


class TokenResponse(BaseModel):
    accessToken: str
    tokenType: str = "bearer"
    expiresAt: datetime
    user: UserResponse

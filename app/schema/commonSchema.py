import re
from typing import Annotated, Generic, TypeVar
from urllib.parse import urlparse

from bson import ObjectId
from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.core.config import settings
from app.core.utils import LOCAL_IMAGE_RE


class StrictModel(BaseModel):
    """Every request body inherits this: unknown fields are rejected (blocks mass-assignment)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------------------------------------------------------- validators
def _object_id(v: str) -> str:
    if not isinstance(v, str) or len(v) != 24 or not ObjectId.is_valid(v):
        raise ValueError("Invalid id")
    return v


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# def _safe_text(v: str) -> str:
#     v = v.strip()
#     if "<" in v or ">" in v:
#         raise ValueError("Angle brackets / HTML are not allowed")
#     if _CONTROL.search(v):
#         raise ValueError("Invalid control characters")
#     return v


# def _image_url(v: str) -> str:
#     if LOCAL_IMAGE_RE.match(v):
#         return v
#     parsed = urlparse(v)
#     allowed_schemes = {"https"}
#     if settings.ENVIRONMENT == "development":
#         allowed_schemes.add("http")
#     if parsed.scheme in allowed_schemes and parsed.netloc and len(v) <= 500 and not re.search(r"[\s<>\"'\\]", v):
#         return v
#     raise ValueError("imageUrl must be an uploaded image path or a valid HTTPS URL (HTTP is allowed only in development)")


# def _https_url(v: str) -> str:
#     parsed = urlparse(v)
#     if parsed.scheme != "https" or not parsed.netloc or len(v) > 500 or re.search(r"[\s<>\"'\\]", v):
#         raise ValueError("Only https:// links are allowed")
#     return v

def _safe_text(v: str) -> str:
    v = v.strip()
    if "<" in v or ">" in v:
        raise ValueError("Angle brackets / HTML are not allowed")
    if _CONTROL.search(v):
        raise ValueError("Invalid control characters")
    return v


def _image_url(v: str) -> str:
    if LOCAL_IMAGE_RE.match(v):
        return v
    parsed = urlparse(v)
    allowed_schemes = {"http", "https"}
    if parsed.scheme in allowed_schemes and parsed.netloc and len(v) <= 500 and not re.search(r"[\s<>\"'\\]", v):
        return v
    raise ValueError("imageUrl must be an uploaded image path or a valid HTTP/HTTPS URL")


def _https_url(v: str) -> str:  # You can keep your function name or update it to match
    parsed = urlparse(v)
    allowed_schemes = {"http", "https"}
    if parsed.scheme not in allowed_schemes or not parsed.netloc or len(v) > 500 or re.search(r"[\s<>\"'\\]", v):
        raise ValueError("Only http:// and https:// links are allowed")
    return v

ObjectIdStr = Annotated[str, AfterValidator(_object_id)]
SafeText = Annotated[str, AfterValidator(_safe_text)]
ImageUrl = Annotated[str, AfterValidator(_image_url)]
HttpsUrl = Annotated[str, AfterValidator(_https_url)]
HexColor = Annotated[str, Field(pattern=r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")]

T = TypeVar("T")


class Paginated(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    limit: int

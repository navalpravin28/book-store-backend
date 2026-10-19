import re
import unicodedata
import uuid
from datetime import datetime, timezone

from bson import ObjectId

from app.core.exception import BadRequestException

LOCAL_IMAGE_RE = re.compile(
    r"^/static/uploads/(books|categories|advertisements)/[a-f0-9]{32}\.(jpg|png|webp)$"
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_object_id(value: str) -> ObjectId:
    if not isinstance(value, str) or len(value) != 24 or not ObjectId.is_valid(value):
        raise BadRequestException("Invalid id")
    return ObjectId(value)


def serialize_doc(doc):
    """Mongo doc -> JSON friendly (ObjectId -> str, _id -> id). Works recursively."""
    if isinstance(doc, list):
        return [serialize_doc(d) for d in doc]
    if isinstance(doc, dict):
        out = {}
        for k, v in doc.items():
            key = "id" if k == "_id" else k
            out[key] = serialize_doc(v)
        return out
    if isinstance(doc, ObjectId):
        return str(doc)
    return doc


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()[:80]
    return text or f"category-{uuid.uuid4().hex[:8]}"


def escape_regex(text: str) -> str:
    """User text is searched literally - never as a regex (blocks NoSQL regex injection / ReDoS)."""
    return re.escape(text[:100])


def csv_safe(value) -> str:
    """Neutralise CSV/Excel formula injection (=, +, -, @ at the start of a cell)."""
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


def mask_mobile(mobile: str) -> str:
    return "*" * max(len(mobile) - 4, 0) + mobile[-4:]


# ------------------------------------------------------------ date helpers
from datetime import date, time  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from app.core.config import settings  # noqa: E402


def local_tz() -> ZoneInfo:
    return ZoneInfo(settings.APP_TIMEZONE)


def today_local() -> date:
    return datetime.now(local_tz()).date()


def day_start_utc(d: date) -> datetime:
    """Midnight of local day `d` expressed in UTC (what Mongo stores)."""
    return datetime.combine(d, time.min, tzinfo=local_tz()).astimezone(timezone.utc)


def as_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

import re
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field

from app.schema.commonSchema import ImageUrl, ObjectIdStr, SafeText, StrictModel


def _empty_isbn_to_none(v: str | None) -> str | None:
    if isinstance(v, str) and not v.strip():
        return None
    return v


def _isbn(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.replace("-", "").replace(" ", "").upper()
    if not re.fullmatch(r"\d{9}[\dX]|\d{13}", v):
        raise ValueError("ISBN must be a valid ISBN-10 or ISBN-13")
    return v


Isbn = Annotated[str | None, BeforeValidator(_empty_isbn_to_none), AfterValidator(_isbn)]


class BookCreate(StrictModel):
    name: SafeText = Field(min_length=1, max_length=200)
    author: SafeText = Field(min_length=1, max_length=120)
    publisher: SafeText = Field(min_length=1, max_length=120)
    description: SafeText = Field(default="", max_length=2000)
    imageUrl: ImageUrl | None = None
    categoryId: ObjectIdStr
    isbn: Isbn = None
    price: float = Field(ge=0, le=1_000_000)
    stock: int = Field(default=0, ge=0, le=1_000_000)


class BookUpdate(StrictModel):
    """Stock is changed only via PATCH /books/{id}/stock; soldCount only changes through sales."""

    name: SafeText | None = Field(default=None, min_length=1, max_length=200)
    author: SafeText | None = Field(default=None, min_length=1, max_length=120)
    publisher: SafeText | None = Field(default=None, min_length=1, max_length=120)
    description: SafeText | None = Field(default=None, max_length=2000)
    imageUrl: ImageUrl | None = None
    categoryId: ObjectIdStr | None = None
    isbn: Isbn = None
    price: float | None = Field(default=None, ge=0, le=1_000_000)


class StockUpdate(StrictModel):
    delta: int = Field(ge=-100_000, le=100_000, description="+ to add stock, - to remove")


class BookPublic(BaseModel):
    """What anonymous viewers see: no exact stock, no sales numbers."""

    id: str
    name: str
    author: str
    publisher: str
    description: str = ""
    imageUrl: str | None = None
    categoryId: str
    categoryName: str | None = None
    isbn: str | None = None
    price: float
    inStock: bool


class BookAdmin(BookPublic):
    stock: int
    soldCount: int
    createdAt: datetime | None = None
    updatedAt: datetime | None = None


class RowError(BaseModel):
    row: int
    errors: list[str]


class BulkImportResult(BaseModel):
    dryRun: bool
    totalRows: int
    inserted: int
    failed: list[RowError]

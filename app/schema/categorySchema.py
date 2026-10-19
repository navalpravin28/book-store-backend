from datetime import datetime

from pydantic import BaseModel, Field

from app.schema.commonSchema import HexColor, ImageUrl, SafeText, StrictModel


class CategoryColors(BaseModel):
    color: HexColor = "#294C3B"
    spineColor: HexColor = "#1D362A"
    textColor: HexColor = "#FFF4D8"
    accentColor: HexColor = "#E9D7A5"


class CategoryCreate(StrictModel):
    categoryName: SafeText = Field(min_length=2, max_length=80)
    description: SafeText = Field(default="", max_length=500)
    imageUrl: ImageUrl | None = None  # use POST /uploads/categories first, then pass the returned imageUrl


class CategoryUpdate(StrictModel):
    categoryName: SafeText | None = Field(default=None, min_length=2, max_length=80)
    description: SafeText | None = Field(default=None, max_length=500)
    imageUrl: ImageUrl | None = None


class CategoryResponse(BaseModel):
    id: str
    categoryName: str
    description: str = ""
    imageUrl: str | None = None
    slug: str
    categoryColors: CategoryColors = Field(default_factory=CategoryColors)
    bookCount: int = 0
    createdAt: datetime | None = None
    updatedAt: datetime | None = None

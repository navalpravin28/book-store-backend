from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schema.commonSchema import HttpsUrl, ImageUrl, SafeText, StrictModel

DurationDays = Literal[1, 2, 3]


class AdvertisementCreate(StrictModel):
    title: SafeText = Field(min_length=3, max_length=100)
    description: SafeText = Field(default="", max_length=500)
    imageUrl: ImageUrl | None = None
    linkUrl: HttpsUrl | None = None
    durationDays: DurationDays


class AdvertisementUpdate(StrictModel):
    title: SafeText | None = Field(default=None, min_length=3, max_length=100)
    description: SafeText | None = Field(default=None, max_length=500)
    imageUrl: ImageUrl | None = None
    linkUrl: HttpsUrl | None = None
    durationDays: DurationDays | None = Field(
        default=None, description="Sending this (re)starts the timer from now"
    )


class AdvertisementPublic(BaseModel):
    id: str
    title: str
    description: str = ""
    imageUrl: str | None = None
    linkUrl: str | None = None
    startsAt: datetime
    expiresAt: datetime


class AdvertisementMine(AdvertisementPublic):
    durationDays: int
    status: Literal["active", "expired"]
    createdAt: datetime
    updatedAt: datetime


class AdvertisementAdmin(AdvertisementMine):
    ownerId: str
    ownerName: str

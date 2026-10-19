from typing import Literal

from pydantic import BaseModel

UploadKind = Literal["books", "categories", "advertisements"]


class UploadResponse(BaseModel):
    imageUrl: str
    contentType: str
    size: int

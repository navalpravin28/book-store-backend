import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schema.commonSchema import ObjectIdStr, SafeText, StrictModel


class SaleCreate(StrictModel):
    bookId: ObjectIdStr
    quantity: int = Field(ge=1, le=1000)
    buyerName: SafeText = Field(min_length=2, max_length=80)
    buyerMobile: str = Field(description="10-13 digits, optional leading +")
    note: SafeText = Field(default="", max_length=200)

    @field_validator("buyerMobile")
    @classmethod
    def _mobile(cls, v: str) -> str:
        v = re.sub(r"[\s-]", "", v)
        if not re.fullmatch(r"\+?\d{10,13}", v):
            raise ValueError("Enter a valid mobile number")
        return v


class SaleResponse(BaseModel):
    id: str
    bookId: str
    bookName: str
    categoryId: str | None = None
    quantity: int
    unitPrice: float
    totalAmount: float
    buyerName: str
    buyerMobile: str
    note: str = ""
    soldBy: str
    soldByName: str | None = None
    soldAt: datetime

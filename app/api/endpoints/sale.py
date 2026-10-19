from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.core.db import get_db
from app.core.security import require_admin
from app.core.utils import serialize_doc
from app.schema.commonSchema import ObjectIdStr, Paginated
from app.schema.saleSchema import SaleCreate, SaleResponse
from app.services.saleService import SaleService

router = APIRouter()  # every route here is admin only (buyer names + mobile numbers are personal data)


@router.post("", response_model=SaleResponse, status_code=201, summary="[Admin] Record a sale (reduces stock)")
async def create_sale(payload: SaleCreate, admin: dict = Depends(require_admin), db=Depends(get_db)):
    return serialize_doc(await SaleService(db).create(payload, admin))


@router.get("", response_model=Paginated[SaleResponse], summary="[Admin] Sold data with buyer name + mobile")
async def list_sales(
    page: int = Query(1, ge=1, le=100000),
    limit: int = Query(20, ge=1, le=100),
    dateFrom: date | None = None,
    dateTo: date | None = None,
    bookId: ObjectIdStr | None = None,
    q: str | None = Query(None, max_length=60, description="buyer name or mobile"),
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    result = await SaleService(db).list(page=page, limit=limit, date_from=dateFrom, date_to=dateTo, book_id=bookId, q=q)
    return serialize_doc(result)


@router.get("/export/csv", summary="[Admin] Download sold data as CSV")
async def export_sales_csv(
    dateFrom: date | None = None,
    dateTo: date | None = None,
    bookId: ObjectIdStr | None = None,
    q: str | None = Query(None, max_length=60),
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    return StreamingResponse(
        SaleService(db).export_csv(admin["id"], dateFrom, dateTo, bookId, q),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="sales.csv"'},
    )


@router.get("/{sale_id}", response_model=SaleResponse, summary="[Admin] One sale")
async def get_sale(sale_id: ObjectIdStr, admin: dict = Depends(require_admin), db=Depends(get_db)):
    return serialize_doc(await SaleService(db).get(sale_id))

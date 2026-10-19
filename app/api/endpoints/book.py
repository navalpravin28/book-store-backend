from typing import Literal

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.db import get_db
from app.core.exception import BadRequestException
from app.core.security import require_admin
from app.core.utils import serialize_doc
from app.schema.bookSchema import (
    BookAdmin,
    BookCreate,
    BookPublic,
    BookUpdate,
    BulkImportResult,
    StockUpdate,
)
from app.schema.commonSchema import ObjectIdStr, Paginated
from app.services.bookService import BookService
from app.services.uploadService import UploadService

router = APIRouter()

Order = Literal["asc", "desc"]


# ================= ADMIN (static paths first so they never clash with /{book_id}) =================
@router.get("/manage/list", response_model=Paginated[BookAdmin], summary="[Admin] List books with stock + sold counts")
async def admin_list_books(
    page: int = Query(1, ge=1, le=100000),
    limit: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, max_length=100),
    categoryId: ObjectIdStr | None = None,
    inStock: bool | None = None,
    sortBy: str = Query("createdAt", max_length=20),
    order: Order = "desc",
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    result = await BookService(db).list(page=page, limit=limit, q=q, category_id=categoryId, in_stock=inStock,
                                        sort_by=sortBy, order=order, admin=True)
    return serialize_doc(result)


@router.get("/export/csv", summary="[Admin] Download the full book list as CSV")
async def export_books_csv(admin: dict = Depends(require_admin), db=Depends(get_db)):
    return StreamingResponse(
        BookService(db).export_csv(admin["id"]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="books.csv"'},
    )


@router.post("/bulk", response_model=BulkImportResult, summary="[Admin] Bulk create books from a CSV file")
async def bulk_import_books(
    file: UploadFile = File(...),
    dryRun: bool = Query(False, description="Validate only, insert nothing"),
    admin: dict = Depends(require_admin),
    db=Depends(get_db),
):
    if not (file.filename or "").lower().endswith(".csv"):
        raise BadRequestException("Please upload a .csv file")
    raw = await UploadService.read_limited(file, settings.MAX_CSV_SIZE_MB * 1024 * 1024)
    return await BookService(db).bulk_import(raw, dryRun, admin["id"])


@router.post("", response_model=BookAdmin, status_code=201, summary="[Admin] Create a single book")
async def create_book(payload: BookCreate, admin: dict = Depends(require_admin), db=Depends(get_db)):
    return serialize_doc(await BookService(db).create(payload, admin["id"]))


@router.put("/{book_id}", response_model=BookAdmin, summary="[Admin] Update a book")
async def update_book(book_id: ObjectIdStr, payload: BookUpdate, admin: dict = Depends(require_admin), db=Depends(get_db)):
    return serialize_doc(await BookService(db).update(book_id, payload, admin["id"]))


@router.patch("/{book_id}/stock", response_model=BookAdmin, summary="[Admin] Add (+) or remove (-) stock")
async def update_stock(book_id: ObjectIdStr, payload: StockUpdate, admin: dict = Depends(require_admin), db=Depends(get_db)):
    return serialize_doc(await BookService(db).adjust_stock(book_id, payload.delta, admin["id"]))


@router.delete("/{book_id}", status_code=204, summary="[Admin] Delete a book")
async def delete_book(book_id: ObjectIdStr, admin: dict = Depends(require_admin), db=Depends(get_db)):
    await BookService(db).delete(book_id, admin["id"])
    return Response(status_code=204)


# ================= PUBLIC (no login needed) =================
@router.get("", response_model=Paginated[BookPublic], summary="Browse / search books")
async def list_books(
    page: int = Query(1, ge=1, le=100000),
    limit: int = Query(20, ge=1, le=100),
    q: str | None = Query(None, max_length=100),
    categoryId: ObjectIdStr | None = None,
    inStock: bool | None = None,
    sortBy: str = Query("createdAt", max_length=20),
    order: Order = "desc",
    db=Depends(get_db),
):
    result = await BookService(db).list(page=page, limit=limit, q=q, category_id=categoryId, in_stock=inStock,
                                        sort_by=sortBy, order=order, admin=False)
    return serialize_doc(result)


@router.get("/{book_id}", response_model=BookPublic, summary="Get one book")
async def get_book(book_id: ObjectIdStr, db=Depends(get_db)):
    return serialize_doc(await BookService(db).get(book_id))

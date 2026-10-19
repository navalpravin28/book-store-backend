from fastapi import APIRouter, Depends, Path, Query, Response

from app.core.db import get_db
from app.core.security import require_admin
from app.core.utils import serialize_doc
from app.schema.categorySchema import CategoryCreate, CategoryResponse, CategoryUpdate
from app.schema.commonSchema import Paginated
from app.services.categoryService import CategoryService

router = APIRouter()


# ---------------- public (no login needed) ----------------
@router.get("", response_model=Paginated[CategoryResponse], summary="List categories")
async def list_categories(
    page: int = Query(1, ge=1, le=100000),
    limit: int = Query(50, ge=1, le=100),
    q: str | None = Query(None, max_length=100),
    db=Depends(get_db),
):
    return serialize_doc(await CategoryService(db).list(page, limit, q))


@router.get("/{slug}", response_model=CategoryResponse, summary="Get a category by slug")
async def get_category(slug: str = Path(pattern=r"^[a-z0-9-]{1,100}$"), db=Depends(get_db)):
    return serialize_doc(await CategoryService(db).get_by_slug(slug))


# ---------------- admin only ----------------
@router.post("", response_model=CategoryResponse, status_code=201, summary="[Admin] Create category")
async def create_category(payload: CategoryCreate, admin: dict = Depends(require_admin), db=Depends(get_db)):
    return serialize_doc(await CategoryService(db).create(payload, admin["id"]))


@router.put("/{category_id}", response_model=CategoryResponse, summary="[Admin] Update category")
async def update_category(
    category_id: str, payload: CategoryUpdate, admin: dict = Depends(require_admin), db=Depends(get_db)
):
    return serialize_doc(await CategoryService(db).update(category_id, payload, admin["id"]))


@router.delete("/{category_id}", status_code=204, summary="[Admin] Delete category (must have no books)")
async def delete_category(category_id: str, admin: dict = Depends(require_admin), db=Depends(get_db)):
    await CategoryService(db).delete(category_id, admin["id"])
    return Response(status_code=204)

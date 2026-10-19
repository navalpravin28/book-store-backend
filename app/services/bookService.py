from __future__ import annotations

import csv
import io

from pydantic import ValidationError
from pymongo import ReturnDocument
from pymongo.errors import BulkWriteError, DuplicateKeyError

from app.core.config import settings
from app.core.exception import BadRequestException, ConflictException, NotFoundException
from app.core.utils import csv_safe, escape_regex, to_object_id, utcnow
from app.schema.bookSchema import BookCreate, BookUpdate, BulkImportResult, RowError
from app.services.auditService import AuditService
from app.services.uploadService import UploadService

PUBLIC_SORT = {"name": "name", "price": "price", "createdAt": "createdAt"}
ADMIN_SORT = {**PUBLIC_SORT, "stock": "stock", "soldCount": "soldCount"}

CSV_REQUIRED = {"name", "author", "publisher", "price"}
EXPORT_HEADERS = [
    "id", "name", "author", "publisher", "description", "category", "isbn", "price",
    "stock", "soldCount", "imageUrl", "createdAt",
]


class BookService:
    def __init__(self, db):
        self.db = db
        self.col = db.books
        self.categories = db.categories
        self.audit = AuditService(db)

    # ---------------------------------------------------------------- helpers
    async def _category_oid(self, category_id: str):
        oid = to_object_id(category_id)
        if not await self.categories.find_one({"_id": oid}, {"_id": 1}):
            raise NotFoundException("Category not found")
        return oid

    async def _present(self, docs: list[dict]) -> list[dict]:
        """Adds categoryName + inStock. Response models decide which fields leave the API."""
        ids = list({d["categoryId"] for d in docs})
        names = {}
        if ids:
            async for c in self.categories.find({"_id": {"$in": ids}}, {"categoryName": 1}):
                names[c["_id"]] = c["categoryName"]
        for d in docs:
            d["categoryName"] = names.get(d["categoryId"])
            d["inStock"] = d.get("stock", 0) > 0
        return docs

    # ------------------------------------------------------------------- CRUD
    async def create(self, data: BookCreate, actor_id: str) -> dict:
        category_oid = await self._category_oid(data.categoryId)
        now = utcnow()
        doc = data.model_dump()
        doc.update({
            "categoryId": category_oid,
            "soldCount": 0,
            "createdAt": now,
            "updatedAt": now,
        })
        try:
            result = await self.col.insert_one(doc)
        except DuplicateKeyError:
            raise ConflictException("A book with this ISBN already exists")
        await self.audit.log(actor_id, "book.create", "book", str(result.inserted_id))
        return (await self._present([await self.col.find_one({"_id": result.inserted_id})]))[0]

    async def get(self, book_id: str) -> dict:
        doc = await self.col.find_one({"_id": to_object_id(book_id)})
        if not doc:
            raise NotFoundException("Book not found")
        return (await self._present([doc]))[0]

    async def list(self, *, page: int, limit: int, q: str | None, category_id: str | None,
                   in_stock: bool | None, sort_by: str, order: str, admin: bool) -> dict:
        query: dict = {}
        if category_id:
            query["categoryId"] = to_object_id(category_id)
        if q:
            rx = escape_regex(q)
            query["$or"] = [
                {"name": {"$regex": rx, "$options": "i"}},
                {"author": {"$regex": rx, "$options": "i"}},
            ]
        if in_stock is True:
            query["stock"] = {"$gt": 0}
        elif in_stock is False:
            query["stock"] = 0

        allowed = ADMIN_SORT if admin else PUBLIC_SORT
        field = allowed.get(sort_by, "createdAt")  # whitelist: never sort by a user-supplied raw field
        direction = 1 if order == "asc" else -1

        total = await self.col.count_documents(query)
        cursor = self.col.find(query).sort(field, direction).skip((page - 1) * limit).limit(limit)
        docs = await self._present([d async for d in cursor])
        return {"items": docs, "total": total, "page": page, "limit": limit}

    async def update(self, book_id: str, data: BookUpdate, actor_id: str) -> dict:
        oid = to_object_id(book_id)
        existing = await self.col.find_one({"_id": oid})
        if not existing:
            raise NotFoundException("Book not found")

        updates = {k: v for k, v in data.model_dump(exclude_unset=True).items()
                   if v is not None or k in ("imageUrl", "isbn")}
        if "categoryId" in updates:
            updates["categoryId"] = await self._category_oid(updates["categoryId"])
        updates["updatedAt"] = utcnow()

        try:
            doc = await self.col.find_one_and_update({"_id": oid}, {"$set": updates}, return_document=ReturnDocument.AFTER)
        except DuplicateKeyError:
            raise ConflictException("A book with this ISBN already exists")

        if "imageUrl" in updates and existing.get("imageUrl") != updates["imageUrl"]:
            UploadService.delete_local(existing.get("imageUrl"))
        await self.audit.log(actor_id, "book.update", "book", book_id)
        return (await self._present([doc]))[0]

    async def adjust_stock(self, book_id: str, delta: int, actor_id: str) -> dict:
        oid = to_object_id(book_id)
        flt: dict = {"_id": oid}
        if delta < 0:
            flt["stock"] = {"$gte": -delta}  # atomic: stock can never go negative
        doc = await self.col.find_one_and_update(
            flt, {"$inc": {"stock": delta}, "$set": {"updatedAt": utcnow()}}, return_document=ReturnDocument.AFTER
        )
        if not doc:
            if not await self.col.find_one({"_id": oid}, {"_id": 1}):
                raise NotFoundException("Book not found")
            raise ConflictException("Not enough stock to remove that quantity")
        await self.audit.log(actor_id, "book.stock", "book", book_id, {"delta": delta, "newStock": doc["stock"]})
        return (await self._present([doc]))[0]

    async def delete(self, book_id: str, actor_id: str) -> None:
        doc = await self.col.find_one_and_delete({"_id": to_object_id(book_id)})
        if not doc:
            raise NotFoundException("Book not found")
        UploadService.delete_local(doc.get("imageUrl"))
        await self.audit.log(actor_id, "book.delete", "book", book_id, {"name": doc["name"]})

    # ------------------------------------------------------------- CSV import
    async def bulk_import(self, raw: bytes, dry_run: bool, actor_id: str) -> BulkImportResult:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise BadRequestException("CSV must be UTF-8 encoded")

        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise BadRequestException("CSV is empty")
        reader.fieldnames = [h.strip() for h in reader.fieldnames]
        headers = set(reader.fieldnames)
        missing = CSV_REQUIRED - headers
        if missing:
            raise BadRequestException(f"Missing CSV columns: {', '.join(sorted(missing))}")
        if not ({"categorySlug", "categoryId"} & headers):
            raise BadRequestException("CSV needs a categorySlug (or categoryId) column")

        slug_map = {}
        async for c in self.categories.find({}, {"slug": 1}):
            slug_map[c["slug"]] = c["_id"]

        valid: list[tuple[int, dict]] = []
        failed: list[RowError] = []
        seen_isbn: set[str] = set()
        total = 0

        try:
            for line_no, row in enumerate(reader, start=2):
                total += 1
                if total > settings.MAX_CSV_ROWS:
                    raise BadRequestException(f"Too many rows (max {settings.MAX_CSV_ROWS} per file)")
                row = {k: (v or "").strip() for k, v in row.items() if k}
                doc, errors = await self._row_to_doc(row, slug_map, seen_isbn)
                if errors:
                    failed.append(RowError(row=line_no, errors=errors))
                else:
                    valid.append((line_no, doc))
        except csv.Error:
            raise BadRequestException("Malformed CSV file")

        inserted = len(valid)
        if valid and not dry_run:
            inserted = await self._insert_rows(valid, failed)
            await self.audit.log(actor_id, "book.bulk_import", "book", None, {"inserted": inserted, "failed": len(failed)})

        failed.sort(key=lambda r: r.row)
        return BulkImportResult(dryRun=dry_run, totalRows=total, inserted=inserted if not dry_run else len(valid), failed=failed[:100])

    async def _row_to_doc(self, row: dict, slug_map: dict, seen_isbn: set):
        errors: list[str] = []
        category_oid = None
        if row.get("categoryId"):
            try:
                oid = to_object_id(row["categoryId"])
                if oid in slug_map.values():
                    category_oid = oid
            except Exception:
                pass
            if not category_oid:
                errors.append("categoryId: unknown category")
        elif row.get("categorySlug"):
            category_oid = slug_map.get(row["categorySlug"].lower())
            if not category_oid:
                errors.append(f"categorySlug: '{row['categorySlug']}' does not exist")
        else:
            errors.append("category: categorySlug or categoryId is required")

        payload = {
            "name": row.get("name"),
            "author": row.get("author"),
            "publisher": row.get("publisher"),
            "price": row.get("price"),
            "categoryId": str(category_oid) if category_oid else "0" * 24,
        }
        for key in ("description", "imageUrl", "isbn", "stock"):
            if row.get(key):
                payload[key] = row[key]
        try:
            data = BookCreate.model_validate(payload)
        except ValidationError as exc:
            errors += [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
            return None, errors

        if errors:
            return None, errors
        if data.isbn:
            if data.isbn in seen_isbn:
                return None, ["isbn: duplicated inside the file"]
            seen_isbn.add(data.isbn)

        now = utcnow()
        doc = data.model_dump()
        doc.update({
            "categoryId": category_oid,
            "soldCount": 0,
            "createdAt": now,
            "updatedAt": now,
        })
        return doc, []

    async def _insert_rows(self, valid: list[tuple[int, dict]], failed: list[RowError]) -> int:
        docs = [d for _, d in valid]
        try:
            await self.col.insert_many(docs, ordered=False)
            return len(docs)
        except BulkWriteError as exc:
            write_errors = exc.details.get("writeErrors", [])
            for we in write_errors:
                line_no = valid[we["index"]][0]
                msg = "isbn: already exists" if we.get("code") == 11000 else "could not be saved"
                failed.append(RowError(row=line_no, errors=[msg]))
            return len(docs) - len(write_errors)

    # ------------------------------------------------------------- CSV export
    async def export_csv(self, actor_id: str):
        """Async generator -> streams rows so large catalogues never sit fully in memory."""
        await self.audit.log(actor_id, "book.export", "book")
        names = {}
        async for c in self.categories.find({}, {"categoryName": 1}):
            names[c["_id"]] = c["categoryName"]

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(EXPORT_HEADERS)
        yield "﻿" + buf.getvalue()  # BOM so Excel opens UTF-8 correctly

        async for d in self.col.find({}).sort("name", 1):
            row = [
                str(d["_id"]), d.get("name"), d.get("author"), d.get("publisher"), d.get("description"),
                names.get(d.get("categoryId")), d.get("isbn"), d.get("price"), d.get("stock"),
                d.get("soldCount"), d.get("imageUrl"),
                d["createdAt"].isoformat() if d.get("createdAt") else "",
            ]
            buf.seek(0)
            buf.truncate(0)
            writer.writerow([csv_safe(v) for v in row])
            yield buf.getvalue()

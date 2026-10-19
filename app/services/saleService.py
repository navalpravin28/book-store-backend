from __future__ import annotations

import csv
import io
from datetime import date, timedelta

from pymongo.errors import PyMongoError

from app.core.exception import ConflictException, NotFoundException
from app.core.utils import as_aware, csv_safe, day_start_utc, escape_regex, local_tz, to_object_id, utcnow
from app.schema.saleSchema import SaleCreate
from app.services.auditService import AuditService


class SaleService:
    def __init__(self, db):
        self.db = db
        self.col = db.sales
        self.books = db.books
        self.audit = AuditService(db)

    async def create(self, data: SaleCreate, actor: dict) -> dict:
        oid = to_object_id(data.bookId)
        qty = data.quantity

        # ONE atomic step: only decrement when enough stock exists -> no overselling under concurrency
        book = await self.books.find_one_and_update(
            {"_id": oid, "stock": {"$gte": qty}},
            {"$inc": {"stock": -qty, "soldCount": qty}, "$set": {"updatedAt": utcnow()}},
            return_document=True,
        )
        if not book:
            if not await self.books.find_one({"_id": oid}, {"_id": 1}):
                raise NotFoundException("Book not found")
            raise ConflictException("Not enough stock for this sale")

        sale = {
            "bookId": oid,
            "bookName": book["name"],
            "categoryId": book.get("categoryId"),
            "quantity": qty,
            "unitPrice": book["price"],
            "totalAmount": round(book["price"] * qty, 2),
            "buyerName": data.buyerName,
            "buyerMobile": data.buyerMobile,
            "note": data.note,
            "soldBy": actor["id"],
            "soldByName": actor["name"],
            "soldAt": utcnow(),
        }
        try:
            result = await self.col.insert_one(sale)
        except PyMongoError:
            # compensate so stock is not lost if the sale row could not be written
            await self.books.update_one({"_id": oid}, {"$inc": {"stock": qty, "soldCount": -qty}})
            raise
        await self.audit.log(actor["id"], "sale.create", "sale", str(result.inserted_id),
                             {"bookId": data.bookId, "quantity": qty})
        return await self.col.find_one({"_id": result.inserted_id})

    # -------------------------------------------------------------- querying
    @staticmethod
    def _query(date_from: date | None, date_to: date | None, book_id: str | None, q: str | None) -> dict:
        query: dict = {}
        if date_from or date_to:
            rng = {}
            if date_from:
                rng["$gte"] = day_start_utc(date_from)
            if date_to:
                rng["$lt"] = day_start_utc(date_to + timedelta(days=1))
            query["soldAt"] = rng
        if book_id:
            query["bookId"] = to_object_id(book_id)
        if q:
            digits = q.replace(" ", "")
            query["$or"] = [
                {"buyerName": {"$regex": escape_regex(q), "$options": "i"}},
                {"buyerMobile": {"$regex": escape_regex(digits)}},
            ]
        return query

    async def get(self, sale_id: str) -> dict:
        doc = await self.col.find_one({"_id": to_object_id(sale_id)})
        if not doc:
            raise NotFoundException("Sale not found")
        return doc

    async def list(self, *, page: int, limit: int, date_from, date_to, book_id, q) -> dict:
        query = self._query(date_from, date_to, book_id, q)
        total = await self.col.count_documents(query)
        cursor = self.col.find(query).sort("soldAt", -1).skip((page - 1) * limit).limit(limit)
        return {"items": [d async for d in cursor], "total": total, "page": page, "limit": limit}

    async def export_csv(self, actor_id: str, date_from, date_to, book_id, q):
        # exports contain customer phone numbers -> always leave an audit trail
        await self.audit.log(actor_id, "sale.export", "sale", None,
                             {"from": str(date_from), "to": str(date_to), "bookId": book_id})
        headers = ["saleId", "soldAt", "bookName", "quantity", "unitPrice", "totalAmount",
                   "buyerName", "buyerMobile", "note", "soldBy"]
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(headers)
        yield "﻿" + buf.getvalue()

        tz = local_tz()
        async for d in self.col.find(self._query(date_from, date_to, book_id, q)).sort("soldAt", -1):
            sold_at = as_aware(d["soldAt"]).astimezone(tz).strftime("%Y-%m-%d %H:%M:%S")
            row = [str(d["_id"]), sold_at, d["bookName"], d["quantity"], d["unitPrice"], d["totalAmount"],
                   d["buyerName"], d["buyerMobile"], d.get("note", ""), d.get("soldByName", "")]
            buf.seek(0)
            buf.truncate(0)
            writer.writerow([csv_safe(v) for v in row])
            yield buf.getvalue()

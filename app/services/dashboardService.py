import asyncio
from datetime import timedelta

from app.core.config import settings
from app.core.utils import day_start_utc, mask_mobile, today_local, utcnow


def _r(value) -> float:
    return round(float(value or 0), 2)


class DashboardService:
    """All analytics are Mongo aggregation pipelines - the heavy lifting stays in the database."""

    def __init__(self, db):
        self.db = db

    # --------------------------------------------------------------- overview
    async def _period(self, since) -> dict:
        pipeline = [
            {"$match": {"soldAt": {"$gte": since}}},
            {"$group": {"_id": None, "sales": {"$sum": 1}, "units": {"$sum": "$quantity"},
                        "revenue": {"$sum": "$totalAmount"}}},
        ]
        rows = await self.db.sales.aggregate(pipeline).to_list(1)
        r = rows[0] if rows else {}
        return {"sales": r.get("sales", 0), "units": r.get("units", 0), "revenue": _r(r.get("revenue"))}

    async def overview(self) -> dict:
        threshold = settings.LOW_STOCK_THRESHOLD
        today = today_local()

        async def books_stats():
            pipeline = [{"$group": {
                "_id": None,
                "totalBooks": {"$sum": 1},
                "totalStock": {"$sum": "$stock"},
                "inventoryValue": {"$sum": {"$multiply": ["$stock", "$price"]}},
                "outOfStock": {"$sum": {"$cond": [{"$eq": ["$stock", 0]}, 1, 0]}},
                "lowStock": {"$sum": {"$cond": [{"$and": [{"$gt": ["$stock", 0]}, {"$lte": ["$stock", threshold]}]}, 1, 0]}},
                "totalSoldUnits": {"$sum": "$soldCount"},
            }}]
            rows = await self.db.books.aggregate(pipeline).to_list(1)
            return rows[0] if rows else {}

        async def all_time_sales():
            pipeline = [{"$group": {"_id": None, "sales": {"$sum": 1}, "revenue": {"$sum": "$totalAmount"}}}]
            rows = await self.db.sales.aggregate(pipeline).to_list(1)
            return rows[0] if rows else {}

        (books, sales, today_p, week_p, month_p, categories, viewers, ads) = await asyncio.gather(
            books_stats(),
            all_time_sales(),
            self._period(day_start_utc(today)),
            self._period(day_start_utc(today - timedelta(days=6))),
            self._period(day_start_utc(today - timedelta(days=29))),
            self.db.categories.count_documents({}),
            self.db.users.count_documents({"role": "viewer"}),
            self.db.advertisements.count_documents({"expiresAt": {"$gt": utcnow()}}),
        )
        return {
            "totalBooks": books.get("totalBooks", 0),
            "totalCategories": categories,
            "totalStock": books.get("totalStock", 0),
            "inventoryValue": _r(books.get("inventoryValue")),
            "outOfStock": books.get("outOfStock", 0),
            "lowStock": books.get("lowStock", 0),
            "totalSoldUnits": books.get("totalSoldUnits", 0),
            "totalSales": sales.get("sales", 0),
            "totalRevenue": _r(sales.get("revenue")),
            "today": today_p,
            "last7Days": week_p,
            "last30Days": month_p,
            "totalViewers": viewers,
            "activeAdvertisements": ads,
        }

    # ------------------------------------------------------------ sales trend
    async def sales_trend(self, days: int) -> list[dict]:
        today = today_local()
        first_day = today - timedelta(days=days - 1)
        pipeline = [
            {"$match": {"soldAt": {"$gte": day_start_utc(first_day)}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$soldAt", "timezone": settings.APP_TIMEZONE}},
                "sales": {"$sum": 1},
                "units": {"$sum": "$quantity"},
                "revenue": {"$sum": "$totalAmount"},
            }},
        ]
        found = {row["_id"]: row async for row in self.db.sales.aggregate(pipeline)}
        points = []
        for i in range(days):  # fill days with no sales so charts have a continuous axis
            d = (first_day + timedelta(days=i)).isoformat()
            row = found.get(d, {})
            points.append({"date": d, "sales": row.get("sales", 0), "units": row.get("units", 0),
                           "revenue": _r(row.get("revenue"))})
        return points

    # -------------------------------------------------------------- top books
    async def top_books(self, limit: int, by: str, days: int | None) -> list[dict]:
        match = {}
        if days:
            match = {"soldAt": {"$gte": day_start_utc(today_local() - timedelta(days=days - 1))}}
        sort_field = "revenue" if by == "revenue" else "units"
        pipeline = [
            {"$match": match},
            {"$group": {"_id": "$bookId", "bookName": {"$last": "$bookName"},
                        "units": {"$sum": "$quantity"}, "revenue": {"$sum": "$totalAmount"}}},
            {"$sort": {sort_field: -1}},
            {"$limit": limit},
        ]
        return [
            {"bookId": str(r["_id"]), "bookName": r["bookName"], "units": r["units"], "revenue": _r(r["revenue"])}
            async for r in self.db.sales.aggregate(pipeline)
        ]

    # ---------------------------------------------------- category performance
    async def category_performance(self) -> list[dict]:
        sales: dict = {}
        async for r in self.db.sales.aggregate([
            {"$group": {"_id": "$categoryId", "units": {"$sum": "$quantity"}, "revenue": {"$sum": "$totalAmount"}}}
        ]):
            sales[r["_id"]] = r

        stock: dict = {}
        async for r in self.db.books.aggregate([
            {"$group": {"_id": "$categoryId", "titles": {"$sum": 1}, "stock": {"$sum": "$stock"}}}
        ]):
            stock[r["_id"]] = r

        result = []
        async for c in self.db.categories.find({}, {"categoryName": 1}):
            s, st = sales.get(c["_id"], {}), stock.get(c["_id"], {})
            result.append({
                "categoryId": str(c["_id"]),
                "categoryName": c["categoryName"],
                "titles": st.get("titles", 0),
                "stock": st.get("stock", 0),
                "unitsSold": s.get("units", 0),
                "revenue": _r(s.get("revenue")),
            })
        result.sort(key=lambda x: x["revenue"], reverse=True)
        return result

    # -------------------------------------------------------------- low stock
    async def low_stock(self, threshold: int | None, limit: int) -> list[dict]:
        t = settings.LOW_STOCK_THRESHOLD if threshold is None else threshold
        cursor = self.db.books.find({"stock": {"$lte": t}}).sort("stock", 1).limit(limit)
        return [
            {"id": str(d["_id"]), "name": d["name"], "author": d["author"], "stock": d["stock"],
             "soldCount": d.get("soldCount", 0)}
            async for d in cursor
        ]

    # ------------------------------------------------------------- top buyers
    async def top_buyers(self, limit: int) -> list[dict]:
        pipeline = [
            {"$group": {"_id": "$buyerMobile", "buyerName": {"$last": "$buyerName"},
                        "purchases": {"$sum": 1}, "units": {"$sum": "$quantity"},
                        "totalSpent": {"$sum": "$totalAmount"}, "lastPurchaseAt": {"$max": "$soldAt"}}},
            {"$sort": {"totalSpent": -1}},
            {"$limit": limit},
        ]
        return [
            {"buyerName": r["buyerName"], "buyerMobileMasked": mask_mobile(r["_id"]),  # PII is masked here
             "purchases": r["purchases"], "units": r["units"], "totalSpent": _r(r["totalSpent"]),
             "lastPurchaseAt": r["lastPurchaseAt"]}
            async for r in self.db.sales.aggregate(pipeline)
        ]

    # ---------------------------------------------------------- advertisements
    async def ads_overview(self) -> dict:
        now = utcnow()
        total, active, expired = await asyncio.gather(
            self.db.advertisements.count_documents({}),
            self.db.advertisements.count_documents({"expiresAt": {"$gt": now}}),
            self.db.advertisements.count_documents({"expiresAt": {"$lte": now}}),
        )
        by_duration = {"1": 0, "2": 0, "3": 0}
        async for r in self.db.advertisements.aggregate([
            {"$match": {"expiresAt": {"$gt": now}}},
            {"$group": {"_id": "$durationDays", "count": {"$sum": 1}}},
        ]):
            by_duration[str(r["_id"])] = r["count"]
        return {"total": total, "active": active, "expired": expired, "activeByDuration": by_duration}

    # ----------------------------------------------------------------- summary
    async def summary(self) -> dict:
        overview, trend, top, cats, low, buyers, ads = await asyncio.gather(
            self.overview(), self.sales_trend(30), self.top_books(5, "units", None),
            self.category_performance(), self.low_stock(None, 10), self.top_buyers(5), self.ads_overview(),
        )
        return {"overview": overview, "salesTrend": trend, "topBooks": top, "categories": cats,
                "lowStock": low, "topBuyers": buyers, "advertisements": ads}

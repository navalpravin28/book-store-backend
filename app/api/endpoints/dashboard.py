from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.core.db import get_db
from app.core.security import require_admin
from app.schema.dashboardSchema import (
    AdsOverview,
    CategoryStat,
    DashboardSummary,
    LowStockBook,
    OverviewResponse,
    TopBook,
    TopBuyer,
    TrendPoint,
)
from app.services.dashboardService import DashboardService

router = APIRouter(dependencies=[Depends(require_admin)])  # whole analytics area is admin only


@router.get("/summary", response_model=DashboardSummary, summary="Everything for the admin home screen in one call")
async def summary(db=Depends(get_db)):
    return await DashboardService(db).summary()


@router.get("/overview", response_model=OverviewResponse, summary="KPI cards: books, stock, revenue, today/7d/30d")
async def overview(db=Depends(get_db)):
    return await DashboardService(db).overview()


@router.get("/sales-trend", response_model=list[TrendPoint], summary="Sales per day (gaps filled with zero)")
async def sales_trend(days: int = Query(30, ge=1, le=365), db=Depends(get_db)):
    return await DashboardService(db).sales_trend(days)


@router.get("/top-books", response_model=list[TopBook], summary="Best sellers by units or revenue")
async def top_books(
    limit: int = Query(10, ge=1, le=50),
    by: Literal["units", "revenue"] = "units",
    days: int | None = Query(None, ge=1, le=365),
    db=Depends(get_db),
):
    return await DashboardService(db).top_books(limit, by, days)


@router.get("/categories", response_model=list[CategoryStat], summary="Titles, stock, units sold and revenue per category")
async def categories(db=Depends(get_db)):
    return await DashboardService(db).category_performance()


@router.get("/low-stock", response_model=list[LowStockBook], summary="Books that need restocking")
async def low_stock(
    threshold: int | None = Query(None, ge=0, le=10000), limit: int = Query(20, ge=1, le=100), db=Depends(get_db)
):
    return await DashboardService(db).low_stock(threshold, limit)


@router.get("/top-buyers", response_model=list[TopBuyer], summary="Repeat customers (mobile numbers masked)")
async def top_buyers(limit: int = Query(10, ge=1, le=50), db=Depends(get_db)):
    return await DashboardService(db).top_buyers(limit)


@router.get("/advertisements", response_model=AdsOverview, summary="Advertisement counts and duration mix")
async def ads(db=Depends(get_db)):
    return await DashboardService(db).ads_overview()

from datetime import datetime

from pydantic import BaseModel


class PeriodTotals(BaseModel):
    sales: int = 0
    units: int = 0
    revenue: float = 0.0


class OverviewResponse(BaseModel):
    totalBooks: int
    totalCategories: int
    totalStock: int
    inventoryValue: float
    outOfStock: int
    lowStock: int
    totalSoldUnits: int
    totalSales: int
    totalRevenue: float
    today: PeriodTotals
    last7Days: PeriodTotals
    last30Days: PeriodTotals
    totalViewers: int
    activeAdvertisements: int


class TrendPoint(BaseModel):
    date: str
    sales: int
    units: int
    revenue: float


class TopBook(BaseModel):
    bookId: str
    bookName: str
    units: int
    revenue: float


class CategoryStat(BaseModel):
    categoryId: str
    categoryName: str
    titles: int
    stock: int
    unitsSold: int
    revenue: float


class LowStockBook(BaseModel):
    id: str
    name: str
    author: str
    stock: int
    soldCount: int


class TopBuyer(BaseModel):
    buyerName: str
    buyerMobileMasked: str
    purchases: int
    units: int
    totalSpent: float
    lastPurchaseAt: datetime


class AdsOverview(BaseModel):
    total: int
    active: int
    expired: int
    activeByDuration: dict[str, int]


class DashboardSummary(BaseModel):
    overview: OverviewResponse
    salesTrend: list[TrendPoint]
    topBooks: list[TopBook]
    categories: list[CategoryStat]
    lowStock: list[LowStockBook]
    topBuyers: list[TopBuyer]
    advertisements: AdsOverview

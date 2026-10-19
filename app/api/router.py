from fastapi import APIRouter

from app.api.endpoints import advertisement, auth, book, category, dashboard, sale, upload, user

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(user.router, prefix="/users", tags=["Users"])
api_router.include_router(category.router, prefix="/categories", tags=["Categories"])
api_router.include_router(book.router, prefix="/books", tags=["Books"])
api_router.include_router(advertisement.router, prefix="/advertisements", tags=["Advertisements"])
api_router.include_router(sale.router, prefix="/sales", tags=["Sales (admin)"])
api_router.include_router(upload.router, prefix="/uploads", tags=["Uploads"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Analytics (admin)"])

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.db import MongoDB, close_db, connect_db
from app.core.exception import register_exception_handlers
from app.core.middleware import BodySizeLimitMiddleware, SecurityHeadersMiddleware, limiter
from app.services.userService import UserService

for sub in ("books", "categories", "advertisements"):
    (settings.UPLOAD_ROOT / sub).mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    await UserService(MongoDB.db).seed_admin()
    yield
    await close_db()


def create_app() -> FastAPI:
    prod = settings.is_production
    app = FastAPI(
        title=settings.PROJECT_NAME,
        lifespan=lifespan,
        # API docs reveal the whole attack surface - hidden in production
        docs_url=None if prod else "/docs",
        redoc_url=None if prod else "/redoc",
        openapi_url=None if prod else "/openapi.json",
    )

    app.state.limiter = limiter
    register_exception_handlers(app)

    # add_middleware: the LAST one added is the OUTERMOST
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=False,  # we use Authorization headers, not cookies
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts_list)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.MAX_REQUEST_BODY_MB * 1024 * 1024)
    app.add_middleware(SecurityHeadersMiddleware)

    app.include_router(api_router, prefix=settings.API_PREFIX)
    # Uploaded images live inside the project: app/static/uploads/<books|categories|advertisements>/
    app.mount("/static", StaticFiles(directory=settings.STATIC_ROOT), name="static")

    @app.get("/health", tags=["Health"])
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
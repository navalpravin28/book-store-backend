from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

import logging

logger = logging.getLogger("bookstore")


class AppException(Exception):
    def __init__(self, message: str, status_code: int = 400, headers: dict | None = None):
        self.message = message
        self.status_code = status_code
        self.headers = headers
        super().__init__(message)


class BadRequestException(AppException):
    def __init__(self, message: str = "Bad request"):
        super().__init__(message, 400)


class UnauthorizedException(AppException):
    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, 401, headers={"WWW-Authenticate": "Bearer"})


class ForbiddenException(AppException):
    def __init__(self, message: str = "You do not have permission to perform this action"):
        super().__init__(message, 403)


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, 404)


class ConflictException(AppException):
    def __init__(self, message: str = "Resource already exists"):
        super().__init__(message, 409)


class PayloadTooLargeException(AppException):
    def __init__(self, message: str = "Payload too large"):
        super().__init__(message, 413)


class TooManyRequestsException(AppException):
    def __init__(self, message: str = "Too many requests"):
        super().__init__(message, 429)


def _body(message: str, **extra) -> dict:
    return {"success": False, "message": message, **extra}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exc(request: Request, exc: AppException):
        return JSONResponse(_body(exc.message), status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_exc(request: Request, exc: RequestValidationError):
        # Never echo the submitted input back (it may contain passwords / PII)
        errors = [
            {
                "field": ".".join(str(p) for p in err["loc"] if p not in ("body", "query", "path")),
                "message": err["msg"],
            }
            for err in exc.errors()
        ]
        return JSONResponse(_body("Validation failed", errors=errors), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def http_exc(request: Request, exc: StarletteHTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse(_body(message), status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RateLimitExceeded)
    async def rate_exc(request: Request, exc: RateLimitExceeded):
        return JSONResponse(_body("Too many requests. Please slow down."), status_code=429)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(_body("Internal server error"), status_code=500)

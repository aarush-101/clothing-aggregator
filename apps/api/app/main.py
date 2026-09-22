"""FastAPI application entry point."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import (
    routes_account,
    routes_clicks,
    routes_health,
    routes_retailers,
    routes_search,
)
from app.config import get_settings
from app.deps import AppContext
from app.logging_config import configure_logging, get_logger, new_request_id, request_id_var
from app.services.ratelimit import rate_limit_headers

log = get_logger(__name__)

DESCRIPTION = """
On-demand menswear search across multiple retailers.

Retailer data is fetched **only** when a user searches - there is no scheduled
crawler and no preloaded product catalogue. Results are cached briefly in Redis
and served progressively over Server-Sent Events.
"""

# Paths that must not consume the general request budget.
RATE_LIMIT_EXEMPT_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    context = AppContext.create(settings)
    app.state.context = context
    log.info(
        "app.started",
        environment=settings.app_env,
        connectors=len(context.registry.all()),
        cache="redis" if settings.redis_url else "memory",
        database="postgres" if settings.database_url else "disabled",
        query_parser="anthropic" if settings.anthropic_enabled else "deterministic",
    )
    try:
        yield
    finally:
        await context.shutdown()
        log.info("app.stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Clothing Aggregator API",
        description=DESCRIPTION,
        version=routes_health.VERSION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Last-Event-ID"],
        expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
        max_age=600,
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or new_request_id()
        request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("http.unhandled_error", method=request.method, path=request.url.path)
            raise
        duration_ms = int((time.perf_counter() - started) * 1000)
        response.headers["X-Request-ID"] = request_id
        if not request.url.path.startswith("/health"):
            log.info(
                "http.request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=duration_ms,
            )
        return response

    @app.middleware("http")
    async def global_rate_limit(request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path.startswith(RATE_LIMIT_EXEMPT_PREFIXES):
            return await call_next(request)
        context: AppContext = getattr(request.app.state, "context", None)
        if context is None:
            return await call_next(request)
        result = await context.rate_limiter.check_request(request)
        if not result.allowed:
            log.warning("http.rate_limited", path=request.url.path)
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"error": "rate_limited", "detail": "Too many requests."},
                headers=rate_limit_headers(result),
            )
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "invalid_request",
                "detail": "The request body was not valid.",
                "fields": [
                    {
                        "field": ".".join(str(p) for p in err.get("loc", [])[1:]),
                        "message": err.get("msg", ""),
                    }
                    for err in exc.errors()[:10]
                ],
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": _error_code(exc.status_code), "detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        # Never leak internals to the client; the detail is in the structured log.
        log.exception("http.internal_error", path=request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "internal_error", "detail": "Something went wrong."},
        )

    app.include_router(routes_health.router)
    app.include_router(routes_search.router)
    app.include_router(routes_clicks.router)
    app.include_router(routes_account.router)
    app.include_router(routes_retailers.router)

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {
            "name": "Clothing Aggregator API",
            "version": routes_health.VERSION,
            "docs": "/docs",
            "health": "/health",
        }

    return app


def _error_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        422: "invalid_request",
        429: "rate_limited",
        501: "not_implemented",
        503: "unavailable",
    }.get(status_code, "error")


app = create_app()

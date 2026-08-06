"""StockLens FastAPI application."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api import auth, companies, indices, meta, screener, superadmin, users, workspace
from app.api._translate import install as install_error_handler
from app.auth.models import create_auth
from app.auth.security import jwt_secret_problem
from app.config import get_settings
from app.db.engine import get_engine, get_raw_engine
from app.db.layer2 import create_layer2
from app.db.models import create_all
from app.ingest.materialise import create_snapshot
from app.logging_setup import configure_logging
from app.security.middleware import (
    BodySizeLimitMiddleware,
    RateLimitIdentityMiddleware,
    SecurityHeadersMiddleware,
)

logger = logging.getLogger("stocklens")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging()
    create_all(get_engine(), get_raw_engine())
    create_layer2(get_engine())
    create_auth(get_engine())
    # Without this a fresh install answers the screener with a 500 rather
    # than an empty result, because nothing has run materialisation yet.
    create_snapshot(get_engine())
    logger.info("StockLens starting in %s mode", settings.environment)
    if not settings.has_finedge_key:
        logger.warning("FINEDGE_API_KEY is not configured; ingestion will fail")

    # A weak signing secret means sessions can be forged. Refuse to start with
    # one anywhere that is not plain-HTTP development.
    secret_problem = jwt_secret_problem()
    if secret_problem:
        if settings.session_cookie_secure:
            raise RuntimeError(f"Refusing to start: {secret_problem}")
        logger.warning("%s. Acceptable for local development only.", secret_problem)
    yield
    logger.info("StockLens shutting down")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="StockLens",
        description="Stock analysis and screening platform for Indian equities",
        version="0.1.0",
        lifespan=lifespan,
    )
    # Middleware runs bottom-up, so the last added is the outermost. Host and
    # body checks go outermost so a bad request is rejected before anything
    # touches it.
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(RateLimitIdentityMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        # Only the methods and headers this API actually uses.
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
        max_age=600,
    )
    app.add_middleware(BodySizeLimitMiddleware)
    if settings.allowed_host_list:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_host_list)
    app.include_router(meta.router)
    app.include_router(companies.router)
    app.include_router(screener.router)
    app.include_router(auth.router)
    app.include_router(workspace.router)
    app.include_router(indices.router)
    app.include_router(superadmin.router)
    app.include_router(users.router)
    # Domain errors become status codes in one place, so no route needs a
    # try block around a service call.
    install_error_handler(app)

    @app.get("/", tags=["meta"])
    def root() -> dict[str, str]:
        return {"name": "StockLens", "version": "0.1.0", "docs": "/docs"}

    return app


app = create_app()

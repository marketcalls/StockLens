"""StockLens FastAPI application."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import companies, meta, screener
from app.config import get_settings
from app.db.engine import get_engine, get_raw_engine
from app.db.models import create_all
from app.logging_setup import configure_logging

logger = logging.getLogger("stocklens")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging()
    create_all(get_engine(), get_raw_engine())
    logger.info("StockLens starting in %s mode", settings.environment)
    if not settings.has_finedge_key:
        logger.warning("FINEDGE_API_KEY is not configured; ingestion will fail")
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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(meta.router)
    app.include_router(companies.router)
    app.include_router(screener.router)

    @app.get("/", tags=["meta"])
    def root() -> dict[str, str]:
        return {"name": "StockLens", "version": "0.1.0", "docs": "/docs"}

    return app


app = create_app()

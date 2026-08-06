"""Meta endpoints: health and data freshness."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.config import get_settings
from app.db.engine import get_engine, get_raw_engine
from app.db.layer2 import create_layer2
from app.db.models import create_all
from app.finedge.client import FinEdgeClient
from app.ingest.layer2_store import counts as layer2_counts
from app.ingest.quality import summary as quality_summary
from app.ingest.store import raw_summary, run_summary

logger = logging.getLogger("stocklens.api.meta")

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/health")
async def health(response: Response, finedge: bool = False) -> dict[str, Any]:
    """Is this instance able to serve requests?

    Checks the database, because that is the dependency whose loss makes every
    read fail. Reporting "ok" while SQLite is unreachable would make a container
    healthcheck useless exactly when it matters.

    FinEdge is *not* probed by default. It is an outbound call to a third party,
    and a healthcheck polled every few seconds would hammer it - while its being
    down does not stop us serving data we already hold. Pass `?finedge=true` when
    you actually want to know. The key itself is never returned, only whether one
    is configured.
    """
    settings = get_settings()

    database_up = True
    database_error: str | None = None
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - a healthcheck reports faults, never raises
        database_up = False
        database_error = str(exc)
        logger.exception("health check could not reach the database")

    payload: dict[str, Any] = {
        "status": "ok" if database_up else "degraded",
        "environment": settings.environment,
        "database": {"reachable": database_up, "error": database_error},
    }

    if finedge:
        client = FinEdgeClient(settings)
        try:
            reachable = await client.healthcheck()
        finally:
            await client.aclose()
        payload["finedge"] = {
            "reachable": reachable,
            "key_configured": settings.has_finedge_key,
            "base_url": settings.finedge_base_url,
        }
    else:
        payload["finedge"] = {"key_configured": settings.has_finedge_key, "checked": False}

    # 503 so an orchestrator can act on the status line alone.
    if not database_up:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return payload


@router.get("/freshness")
def freshness() -> dict[str, Any]:
    """What data we hold and when it was last fetched."""
    core_engine = get_engine()
    raw_engine = get_raw_engine()
    create_all(core_engine, raw_engine)
    return {
        "raw": raw_summary(raw_engine),
        "recent_runs": run_summary(core_engine),
    }


@router.get("/quality")
def quality() -> dict[str, Any]:
    """Data quality checks over the normalised tables."""
    core_engine = get_engine()
    create_layer2(core_engine)
    return quality_summary(core_engine)


@router.get("/counts")
def row_counts() -> dict[str, Any]:
    """Row counts per normalised table."""
    core_engine = get_engine()
    create_layer2(core_engine)
    return layer2_counts(core_engine)

"""Meta endpoints: health and data freshness."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.config import get_settings
from app.db.engine import get_engine, get_raw_engine
from app.db.layer2 import create_layer2
from app.db.models import create_all
from app.finedge.client import FinEdgeClient
from app.ingest.layer2_store import counts as layer2_counts
from app.ingest.quality import summary as quality_summary
from app.ingest.store import raw_summary, run_summary

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/health")
async def health() -> dict[str, Any]:
    """Liveness plus FinEdge connectivity.

    The key itself is never returned, only whether one is configured.
    """
    settings = get_settings()
    client = FinEdgeClient(settings)
    try:
        finedge_up = await client.healthcheck()
    finally:
        await client.aclose()

    return {
        "status": "ok",
        "environment": settings.environment,
        "finedge": {
            "reachable": finedge_up,
            "key_configured": settings.has_finedge_key,
            "base_url": settings.finedge_base_url,
        },
    }


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

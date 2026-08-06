"""The data platform console. Super Admin only.

Every route here is a thin wrapper over app/services/ingest, so the same
operations are available to a script or an agent without going through HTTP.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.deps import require_super_admin
from app.auth.models import Role
from app.auth.service import public_user, record_audit
from app.db.engine import get_engine
from app.services import ingest

router = APIRouter(
    prefix="/api/superadmin",
    tags=["superadmin"],
    dependencies=[Depends(require_super_admin)],
)


class BackfillRequest(BaseModel):
    """How much to download.

    `limit` takes the top N in priority order - index constituents first, then
    by market cap - so a partial run still covers the companies people search
    for. `symbols` overrides that with an explicit list.
    """

    limit: int | None = Field(default=None, ge=1, le=10_000)
    symbols: list[str] | None = None
    call_budget: int | None = Field(default=None, ge=1)


@router.get("/status")
def status() -> dict[str, Any]:
    """What is running now and what ran recently."""
    return ingest.status()


@router.get("/runs/{run_id}")
def run_detail(run_id: str) -> dict[str, Any]:
    return ingest.run_detail(run_id)


@router.post("/plan")
def plan(request: BackfillRequest) -> dict[str, Any]:
    """Cost of a backfill without spending it."""
    return ingest.plan(limit=request.limit)


@router.post("/universe")
def universe(user: dict = Depends(require_super_admin)) -> dict[str, Any]:
    """Symbol master, every index with constituents, index quotes and returns."""
    result = ingest.start_universe_sync()
    record_audit(get_engine(), actor_id=user["id"], action="ingest.universe")
    return result


@router.post("/prices")
def prices(user: dict = Depends(require_super_admin)) -> dict[str, Any]:
    """Every company's quote, in a single call to FinEdge."""
    result = ingest.start_price_refresh()
    record_audit(get_engine(), actor_id=user["id"], action="ingest.prices")
    return result


@router.post("/backfill")
def backfill(request: BackfillRequest, user: dict = Depends(require_super_admin)) -> dict[str, Any]:
    """Start a background backfill. Returns immediately with a run id."""
    result = ingest.start_backfill(
        limit=request.limit,
        symbols=request.symbols,
        call_budget=request.call_budget,
    )
    record_audit(
        get_engine(),
        actor_id=user["id"],
        action="ingest.backfill",
        target=result["run_id"],
        detail={"symbols": result["symbols"]},
    )
    return result


@router.post("/materialise")
def rebuild(user: dict = Depends(require_super_admin)) -> dict[str, Any]:
    """Rebuild the screener table from the normalised tables."""
    result = ingest.rebuild_snapshot()
    record_audit(get_engine(), actor_id=user["id"], action="ingest.materialise")
    return result


@router.post("/runs/{run_id}/release")
def release(run_id: str, user: dict = Depends(require_super_admin)) -> dict[str, Any]:
    """Clear a run that says it is still going but whose process has died.

    This does not stop a live job - nothing here can reach into another process.
    It is the operator stating that the job is gone, so the next one may start.
    """
    result = ingest.release_stuck_run(run_id)
    record_audit(get_engine(), actor_id=user["id"], action="ingest.release", target=run_id)
    return result


@router.post("/repair")
def repair(user: dict = Depends(require_super_admin)) -> dict[str, Any]:
    """Re-apply the normalisation rules to data already stored. No FinEdge calls."""
    result = ingest.repair()
    record_audit(get_engine(), actor_id=user["id"], action="ingest.repair", detail=result)
    return result


@router.get("/quality")
def quality() -> dict[str, Any]:
    return ingest.quality()


@router.get("/me")
def whoami(user: dict = Depends(require_super_admin)) -> dict[str, Any]:
    return {"user": public_user(user), "role": Role(user["role"]).label}

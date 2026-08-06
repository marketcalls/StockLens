"""Logs and diagnostics. Super Admin only."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.auth.deps import require_super_admin
from app.services import diagnostics

router = APIRouter(
    prefix="/api/diagnostics", tags=["diagnostics"], dependencies=[Depends(require_super_admin)]
)


@router.get("/health")
def health() -> dict[str, Any]:
    """Everything needed to decide whether something is wrong."""
    return diagnostics.health()


@router.get("/logs")
def logs(level: str | None = None, logger: str | None = None, limit: int = 100) -> dict[str, Any]:
    return diagnostics.logs(level=level, logger=logger, limit=limit)


@router.get("/logs/{log_id}")
def entry(log_id: int) -> dict[str, Any]:
    """One record, with its traceback."""
    return diagnostics.entry(log_id)

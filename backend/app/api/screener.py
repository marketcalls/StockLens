"""Screener endpoints. Public, with a role-aware row cap.

Thin wrappers over app/services/screener.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.deps import current_role, row_cap_for
from app.auth.models import Role
from app.security.ratelimit import READ, SCREENER, limit
from app.services import screener as screener_service

router = APIRouter(prefix="/api/screener", tags=["screener"])


class ScreenRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    columns: list[str] | None = None
    sort_by: str | None = None
    descending: bool = True
    page: int = 1
    page_size: int = 50


@router.get("/columns", dependencies=[Depends(limit(READ))])
def columns() -> dict[str, Any]:
    """The column catalog, for autocomplete, the query builder and agents."""
    return screener_service.columns()


@router.get("/presets", dependencies=[Depends(limit(READ))])
def presets() -> dict[str, Any]:
    return screener_service.presets()


@router.post("/validate", dependencies=[Depends(limit(READ))])
def validate(request: ScreenRequest) -> dict[str, Any]:
    """Parse without running. Cheap enough to call on every keystroke."""
    return screener_service.validate(request.query)


@router.post("/run", dependencies=[Depends(limit(SCREENER))])
def run(request: ScreenRequest, role: Role = Depends(current_role)) -> dict[str, Any]:
    """Run a query.

    The row cap comes from the caller's role and is applied in the query layer.
    A modified client request cannot retrieve row 26: the LIMIT is computed
    server-side from the cap, never taken from the request.
    """
    return screener_service.run(
        request.query,
        display_columns=request.columns,
        sort_by=request.sort_by,
        descending=request.descending,
        page=request.page,
        page_size=request.page_size,
        row_cap=row_cap_for(role),
    )


@router.post("/presets/{slug}/run", dependencies=[Depends(limit(SCREENER))])
def run_preset(slug: str, page: int = 1, role: Role = Depends(current_role)) -> dict[str, Any]:
    return screener_service.run_preset(slug, page=page, row_cap=row_cap_for(role))

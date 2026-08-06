"""Index endpoints. Public."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.security.ratelimit import READ, limit
from app.services import index as index_service

router = APIRouter(prefix="/api/indices", tags=["indices"], dependencies=[Depends(limit(READ))])


@router.get("")
def list_indices(
    index_type: str | None = None, limit_: int = Query(300, alias="limit", le=500)
) -> dict[str, Any]:
    """Every index, ordered so recognisable ones come first."""
    return index_service.listing(index_type=index_type, limit=limit_)


@router.get("/movers")
def movers(limit_: int = Query(10, alias="limit", le=50)) -> dict[str, Any]:
    """Best and worst index performance today."""
    return index_service.movers(limit=limit_)


@router.get("/{index_symbol}")
def index_detail(index_symbol: str) -> dict[str, Any]:
    """One index with its constituents, returns and median valuation."""
    return index_service.detail(index_symbol)

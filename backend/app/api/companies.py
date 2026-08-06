"""Company endpoints. All public.

Thin wrappers over app/services/company, which holds the logic and is callable
without HTTP.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.security.ratelimit import READ, limit
from app.services import company as company_service

router = APIRouter(prefix="/api", tags=["companies"], dependencies=[Depends(limit(READ))])


@router.get("/search")
def search(q: str = Query(min_length=1), limit_: int = Query(10, alias="limit", le=50)):
    return {"query": q, "results": company_service.search(q, limit_)}


@router.get("/companies")
def company_list(limit_: int = Query(50, alias="limit", le=500)) -> dict[str, Any]:
    return company_service.largest(limit_)


@router.get("/companies/{symbol}")
def company_detail(symbol: str) -> dict[str, Any]:
    return company_service.profile(symbol)


@router.get("/companies/{symbol}/statements")
def statements(
    symbol: str,
    code: str = Query("pl", pattern="^(pl|bs|cf)$"),
    period: str = Query("annual", pattern="^(annual|quarterly|ttm)$"),
    statement_type: str = Query("c", pattern="^(c|s)$"),
) -> dict[str, Any]:
    return company_service.statements(symbol, code, period, statement_type)  # type: ignore[arg-type]


@router.get("/companies/{symbol}/ratios")
def company_ratios(
    symbol: str,
    family: str = Query("ef", pattern="^(pr|le|li|ef)$"),
    statement_type: str = Query("c", pattern="^(c|s)$"),
) -> dict[str, Any]:
    return company_service.ratios(symbol, family, statement_type)  # type: ignore[arg-type]


@router.get("/companies/{symbol}/shareholding")
def company_shareholding(symbol: str) -> dict[str, Any]:
    return company_service.shareholding_pattern(symbol)


@router.get("/companies/{symbol}/peers")
def company_peers(symbol: str, limit_: int = Query(10, alias="limit", le=50)) -> dict[str, Any]:
    return company_service.peers(symbol, limit_)


@router.get("/companies/{symbol}/prices")
def company_prices(
    symbol: str, limit_: int = Query(2000, alias="limit", le=5000)
) -> dict[str, Any]:
    return company_service.prices(symbol, limit_)


@router.get("/companies/{symbol}/corporate-actions")
def company_corporate_actions(symbol: str) -> dict[str, Any]:
    return company_service.corporate_actions(symbol)

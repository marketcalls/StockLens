"""Screener endpoints. Public, with a server-enforced row cap."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db.engine import get_engine
from app.screener.catalog import COLUMNS, screenable
from app.screener.execute import PUBLIC_ROW_CAP, run_screen
from app.screener.parser import QueryError
from app.screener.presets import PRESETS, PRESETS_BY_SLUG

router = APIRouter(prefix="/api/screener", tags=["screener"])


class ScreenRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    columns: list[str] | None = None
    sort_by: str | None = None
    descending: bool = True
    page: int = 1
    page_size: int = 50


@router.get("/columns")
def columns() -> dict[str, Any]:
    """The column catalog, for autocomplete and the query builder."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for column in COLUMNS:
        groups.setdefault(column.source, []).append(
            {
                "key": column.key,
                "label": column.label,
                "unit": column.unit,
                "aliases": list(column.aliases),
                "description": column.description,
                "screenable": column.unit != "text",
            }
        )
    return {
        "total": len(COLUMNS),
        "screenable": len(screenable()),
        "groups": groups,
    }


@router.get("/presets")
def presets() -> dict[str, Any]:
    return {
        "presets": [
            {
                "slug": p.slug,
                "name": p.name,
                "description": p.description,
                "query": p.query,
                "columns": list(p.columns),
            }
            for p in PRESETS
        ]
    }


@router.post("/run")
def run(request: ScreenRequest) -> dict[str, Any]:
    """Run a query.

    The public row cap is applied here, in the query layer. A modified client
    request cannot retrieve row 26 - the LIMIT is computed server-side from the
    cap, not passed in.
    """
    try:
        result = run_screen(
            get_engine(),
            request.query,
            display_columns=request.columns,
            sort_by=request.sort_by,
            descending=request.descending,
            page=request.page,
            page_size=request.page_size,
            row_cap=PUBLIC_ROW_CAP,
        )
    except QueryError as exc:
        raise HTTPException(
            status_code=400,
            detail={"message": exc.message, "position": exc.position},
        ) from exc

    payload = result.as_dict()
    # The SQL is useful when developing but is not part of the public contract.
    payload.pop("sql", None)
    return payload


@router.post("/presets/{slug}/run")
def run_preset(slug: str, page: int = 1) -> dict[str, Any]:
    preset = PRESETS_BY_SLUG.get(slug)
    if preset is None:
        raise HTTPException(status_code=404, detail=f"Unknown preset: {slug}")
    result = run_screen(
        get_engine(),
        preset.query,
        display_columns=list(preset.columns) or None,
        page=page,
        row_cap=PUBLIC_ROW_CAP,
    )
    payload = result.as_dict()
    payload.pop("sql", None)
    payload["preset"] = {
        "slug": preset.slug,
        "name": preset.name,
        "description": preset.description,
    }
    return payload

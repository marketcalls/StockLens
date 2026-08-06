"""Screening.

The query language over company_snapshot. See app/screener for the parser,
compiler and column catalog.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine

from app.db.engine import get_engine
from app.screener.catalog import COLUMNS, resolve, screenable
from app.screener.execute import run_screen
from app.screener.parser import QueryError
from app.screener.parser import parse as parse_query
from app.screener.presets import PRESETS, PRESETS_BY_SLUG
from app.services.errors import InvalidQuery, NotFound


def _engine(engine: Engine | None = None) -> Engine:
    return engine or get_engine()


def columns() -> dict[str, Any]:
    """The column catalog, grouped by where each column comes from.

    An agent should read this before writing a query: it is the authoritative
    list of what can be screened on, with the units each column expects.
    """
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
    return {"total": len(COLUMNS), "screenable": len(screenable()), "groups": groups}


def validate(query: str) -> dict[str, Any]:
    """Parse without executing. Useful before saving or scheduling a screen."""
    try:
        parse_query(query)
    except QueryError as exc:
        return {"valid": False, "message": exc.message, "position": exc.position}
    return {"valid": True, "message": None, "position": None}


def run(
    query: str,
    *,
    display_columns: list[str] | None = None,
    sort_by: str | None = None,
    descending: bool = True,
    page: int = 1,
    page_size: int = 50,
    row_cap: int | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Run a query.

    `row_cap` is the caller's role limit. Passing None means uncapped, which is
    correct for an agent or a script running server-side; the HTTP layer passes
    the limit for the caller's role.
    """
    try:
        result = run_screen(
            _engine(engine),
            query,
            display_columns=display_columns,
            sort_by=sort_by,
            descending=descending,
            page=page,
            page_size=page_size,
            row_cap=row_cap,
        )
    except QueryError as exc:
        raise InvalidQuery(exc.message, exc.position) from exc

    payload = result.as_dict()
    payload.pop("sql", None)
    return payload


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


def run_preset(
    slug: str,
    *,
    page: int = 1,
    row_cap: int | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    preset = PRESETS_BY_SLUG.get(slug)
    if preset is None:
        raise NotFound(f"No preset called {slug}", slug=slug)
    payload = run(
        preset.query,
        display_columns=list(preset.columns) or None,
        page=page,
        row_cap=row_cap,
        engine=engine,
    )
    payload["preset"] = {
        "slug": preset.slug,
        "name": preset.name,
        "description": preset.description,
    }
    return payload


def resolve_column(name: str) -> dict[str, Any] | None:
    """Look a column up by label, key or alias. Case and spacing tolerant."""
    column = resolve(name)
    if column is None:
        return None
    return {
        "key": column.key,
        "label": column.label,
        "unit": column.unit,
        "aliases": list(column.aliases),
        "description": column.description,
    }

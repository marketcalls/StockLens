"""Run a compiled screen against company_snapshot."""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Engine, text

from app.screener.catalog import Column, resolve
from app.screener.compiler import compile_query
from app.screener.parser import QueryError, parse

# What a public visitor sees before the total is disclosed and they are asked to
# sign up. Configurable rather than a constant - see open question Q9.
PUBLIC_ROW_CAP = 25
MAX_PAGE = 100

DEFAULT_COLUMNS = (
    "name",
    "current_price",
    "market_cap",
    "pe",
    "book_value",
    "dividend_yield",
    "returnoncapital",
    "returnonequity",
)

# Companies with no market cap are not screenable in any useful sense: they are
# suspended, delisted or never traded. Excluded by default so a screen does not
# return thousands of blank rows.
BASE_PREDICATE = "market_cap IS NOT NULL"


@dataclass
class ScreenResult:
    query: str
    sql: str
    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    returned: int = 0
    capped: bool = False
    cap: int | None = None
    elapsed_ms: float = 0.0
    page: int = 1
    page_size: int = MAX_PAGE

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "columns": self.columns,
            "rows": self.rows,
            "total": self.total,
            "returned": self.returned,
            "capped": self.capped,
            "cap": self.cap,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "page": self.page,
            "page_size": self.page_size,
        }


def normalise_query(query: str) -> str:
    """Whitespace-and-case normal form, for cache keys."""
    return re.sub(r"\s+", " ", query.strip()).lower()


def query_hash(query: str) -> str:
    return hashlib.sha256(normalise_query(query).encode()).hexdigest()[:16]


def resolve_columns(names: list[str] | None) -> list[Column]:
    if not names:
        names = list(DEFAULT_COLUMNS)
    out: list[Column] = []
    seen: set[str] = set()
    for name in names:
        column = resolve(name)
        if column is None:
            raise QueryError(f'Unknown column: "{name}"')
        if column.key not in seen:
            seen.add(column.key)
            out.append(column)
    return out


def run_screen(
    engine: Engine,
    query: str,
    *,
    display_columns: list[str] | None = None,
    sort_by: str | None = None,
    descending: bool = True,
    page: int = 1,
    page_size: int = MAX_PAGE,
    row_cap: int | None = None,
) -> ScreenResult:
    """Parse, compile and execute. `row_cap` applies the public limit.

    The true total is always computed and disclosed even when the rows are
    capped: telling a visitor there are 340 matches and showing 25 is honest,
    silently showing 25 of 340 is not.
    """
    started = time.perf_counter()
    compiled = compile_query(parse(query))

    columns = resolve_columns(display_columns)
    select_keys = ["symbol", *[c.key for c in columns]]
    # Identifiers all originate in the catalog.
    select_list = ", ".join(select_keys)

    where = f"({BASE_PREDICATE}) AND ({compiled.where})"

    order_column = resolve(sort_by) if sort_by else None
    order_key = order_column.key if order_column else "market_cap"
    direction = "DESC" if descending else "ASC"

    with engine.connect() as conn:
        total = conn.execute(
            text(f"SELECT COUNT(*) FROM company_snapshot WHERE {where}"), compiled.params
        ).scalar_one()

        page = max(1, page)
        page_size = max(1, min(page_size, MAX_PAGE))
        limit = page_size
        offset = (page - 1) * page_size
        capped = False
        if row_cap is not None:
            capped = total > row_cap
            limit = max(0, min(limit, row_cap - offset))

        rows: list[dict[str, Any]] = []
        if limit > 0:
            sql = (
                f"SELECT {select_list} FROM company_snapshot WHERE {where} "
                f"ORDER BY {order_key} IS NULL, {order_key} {direction} "
                f"LIMIT :__limit OFFSET :__offset"
            )
            result = conn.execute(
                text(sql), {**compiled.params, "__limit": limit, "__offset": offset}
            ).mappings()
            rows = [dict(r) for r in result]
        else:
            sql = ""

    return ScreenResult(
        query=query,
        sql=sql,
        columns=[{"key": c.key, "label": c.label, "unit": c.unit} for c in columns],
        rows=rows,
        total=total,
        returned=len(rows),
        capped=capped,
        cap=row_cap,
        elapsed_ms=(time.perf_counter() - started) * 1000,
        page=page,
        page_size=page_size,
    )

"""Company page endpoints. All public - no authentication.

Everything is served from SQLite. No request here touches FinEdge.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine, func, select, text

from app.api.presentation import render, template_for
from app.db.engine import get_engine
from app.db.layer2 import (
    basic_financial,
    company,
    corporate_action,
    index_constituent,
    index_master,
    price_daily,
    quote,
    ratio,
    shareholding,
    statement_line,
    statement_period,
)
from app.security.ratelimit import READ, limit

router = APIRouter(prefix="/api", tags=["companies"], dependencies=[Depends(limit(READ))])

PERIOD_LIMIT = 16


def _engine() -> Engine:
    return get_engine()


@router.get("/search")
def search(q: str = Query(min_length=1), limit: int = Query(10, le=50)) -> dict[str, Any]:
    """Company autocomplete.

    Ranking: exact symbol, then symbol prefix, then name prefix, then anywhere
    in the name. Ties broken by market cap so the company someone actually meant
    comes first - typing "rel" should surface Reliance Industries above Relic
    Technologies.
    """
    term = q.strip().upper()
    if not term:
        return {"query": q, "results": []}

    like = f"{term}%"
    contains = f"%{term}%"
    sql = text(
        """
        SELECT c.symbol, c.name, c.sector, q.current_price, q.market_cap,
               CASE
                 WHEN UPPER(c.symbol) = :term THEN 0
                 WHEN UPPER(c.symbol) LIKE :like THEN 1
                 WHEN UPPER(c.name) LIKE :like THEN 2
                 ELSE 3
               END AS rank
        FROM company c
        LEFT JOIN quote q ON q.symbol = c.symbol
        WHERE UPPER(c.symbol) LIKE :contains OR UPPER(c.name) LIKE :contains
        ORDER BY rank ASC, COALESCE(q.market_cap, 0) DESC
        LIMIT :limit
        """
    )
    with _engine().connect() as conn:
        rows = (
            conn.execute(sql, {"term": term, "like": like, "contains": contains, "limit": limit})
            .mappings()
            .all()
        )

    return {
        "query": q,
        "results": [
            {
                "symbol": r["symbol"],
                "name": r["name"],
                "sector": r["sector"],
                "current_price": r["current_price"],
                "market_cap": r["market_cap"],
            }
            for r in rows
        ],
    }


def _company_row(conn, symbol: str) -> dict[str, Any]:
    row = conn.execute(select(company).where(company.c.symbol == symbol)).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}")
    return dict(row)


@router.get("/companies/{symbol}")
def company_detail(symbol: str) -> dict[str, Any]:
    """Header block: identity, quote, classification, index membership."""
    symbol = symbol.upper()
    with _engine().connect() as conn:
        info = _company_row(conn, symbol)
        quote_row = conn.execute(select(quote).where(quote.c.symbol == symbol)).mappings().first()
        memberships = (
            conn.execute(
                select(index_master.c.index_symbol, index_master.c.index_name)
                .select_from(
                    index_constituent.join(
                        index_master,
                        index_master.c.index_symbol == index_constituent.c.index_symbol,
                    )
                )
                .where(index_constituent.c.symbol == symbol)
                .order_by(index_master.c.market_cap.desc())
            )
            .mappings()
            .all()
        )
        snapshot = (
            conn.execute(text("SELECT * FROM company_snapshot WHERE symbol = :s"), {"s": symbol})
            .mappings()
            .first()
        )

    key_ratios: dict[str, Any] = {}
    if snapshot:
        for key in (
            "pe",
            "pb",
            "ps",
            "book_value",
            "returnonequity",
            "returncapital",
            "returnoncapital",
            "dividend_yield",
            "totaldebttoequity",
            "ev_ebitda",
            "roe3yearsavg",
            "roce3yearsavg",
            "eps",
            "sales",
            "net_profit",
            "price_cagr_1y",
            "price_cagr_3y",
            "price_cagr_5y",
            "price_cagr_10y",
            "promoter_holding",
            "promoter_pledge",
        ):
            if key in snapshot:
                key_ratios[key] = snapshot[key]

    return {
        "symbol": symbol,
        "name": info["name"],
        "nse_code": info["nse_code"],
        "bse_code": info["bse_code"],
        "website": info["website"],
        "description": info["description"],
        "schema_kind": info["schema_kind"],
        "classification": {
            "macro_sector": info["macro_sector"],
            "industry": info["industry"],
            "sector": info["sector"],
            "sub_industry": info["sub_industry"],
        },
        "quote": dict(quote_row) if quote_row else None,
        "indices": [{"symbol": m["index_symbol"], "name": m["index_name"]} for m in memberships],
        "key_ratios": key_ratios,
    }


@router.get("/companies/{symbol}/statements")
def statements(
    symbol: str,
    code: str = Query("pl", pattern="^(pl|bs|cf)$"),
    period: str = Query("annual", pattern="^(annual|quarterly|ttm)$"),
    statement_type: str = Query("c", pattern="^(c|s)$"),
) -> dict[str, Any]:
    """A statement table, rendered with the row template for this company's schema.

    A bank gets interest earned, net interest income and gross NPA. An ordinary
    company gets sales, operating profit and OPM. Same endpoint, same component.
    """
    symbol = symbol.upper()
    with _engine().connect() as conn:
        info = _company_row(conn, symbol)

        periods = (
            conn.execute(
                select(statement_period)
                .where(
                    statement_period.c.symbol == symbol,
                    statement_period.c.statement_code == code,
                    statement_period.c.period_kind == period,
                    statement_period.c.statement_type == statement_type,
                )
                .order_by(statement_period.c.period_end.asc().nulls_last())
            )
            .mappings()
            .all()
        )

        if not periods:
            # Fall back to the other statement type rather than an empty table:
            # only 2,510 of 5,630 companies have consolidated statements.
            other = "s" if statement_type == "c" else "c"
            periods = (
                conn.execute(
                    select(statement_period)
                    .where(
                        statement_period.c.symbol == symbol,
                        statement_period.c.statement_code == code,
                        statement_period.c.period_kind == period,
                        statement_period.c.statement_type == other,
                    )
                    .order_by(statement_period.c.period_end.asc().nulls_last())
                )
                .mappings()
                .all()
            )
            if periods:
                statement_type = other

        periods = periods[-PERIOD_LIMIT:]
        if not periods:
            return {
                "symbol": symbol,
                "statement_code": code,
                "period_kind": period,
                "statement_type": statement_type,
                "available": False,
                "reason": "No data for this statement, period and type.",
                "headers": [],
                "rows": [],
            }

        ids = [p["id"] for p in periods]
        lines = (
            conn.execute(select(statement_line).where(statement_line.c.period_id.in_(ids)))
            .mappings()
            .all()
        )

    by_period: dict[int, dict[str, float | None]] = defaultdict(dict)
    for line in lines:
        by_period[line["period_id"]][line["field_name"]] = line["value"]

    # basic_financial carries FinEdge's derived aggregates, but only as an
    # annual and TTM series. Its headers look like "Mar 2023", which also names
    # a quarter, so merging it into a quarterly statement silently placed annual
    # figures in quarterly columns. Merge for annual and TTM only.
    headers = [p["header"] for p in periods] if period in ("annual", "ttm") else []
    with _engine().connect() as conn:
        derived_rows = (
            conn.execute(
                select(basic_financial).where(
                    basic_financial.c.symbol == symbol,
                    basic_financial.c.statement_code == code,
                    basic_financial.c.statement_type == statement_type,
                    basic_financial.c.header.in_(headers),
                )
            )
            .mappings()
            .all()
        )
    header_to_id = {p["header"]: p["id"] for p in periods}
    for row in derived_rows:
        period_id = header_to_id.get(row["header"])
        if period_id is not None:
            by_period[period_id].setdefault(row["field_name"], row["value"])

    # Only the P&L carries family markers, so bs and cf periods are stored as
    # "unknown". Fall back to the family decided from the company's P&L.
    period_kind_value = periods[0]["schema_kind"]
    if period_kind_value in (None, "", "unknown"):
        period_kind_value = info["schema_kind"]
    schema_kind = period_kind_value
    rows = render(
        template_for(schema_kind, code),
        [dict(p) for p in periods],
        [by_period[p["id"]] for p in periods],
    )

    return {
        "symbol": symbol,
        "statement_code": code,
        "period_kind": period,
        "statement_type": statement_type,
        "schema_kind": schema_kind,
        "available": True,
        "headers": [p["header"] for p in periods],
        "result_dates": [p["result_date"] for p in periods],
        "rows": rows,
        "unit_note": "Figures in Rs. Crore unless stated otherwise",
    }


@router.get("/companies/{symbol}/ratios")
def company_ratios(
    symbol: str,
    family: str = Query("ef", pattern="^(pr|le|li|ef)$"),
    statement_type: str = Query("c", pattern="^(c|s)$"),
) -> dict[str, Any]:
    """A ratio family as a time series, newest last."""
    symbol = symbol.upper()
    with _engine().connect() as conn:
        rows = (
            conn.execute(
                select(ratio)
                .where(
                    ratio.c.symbol == symbol,
                    ratio.c.family == family,
                    ratio.c.statement_type == statement_type,
                )
                .order_by(ratio.c.year.asc())
            )
            .mappings()
            .all()
        )

    if not rows:
        return {"symbol": symbol, "family": family, "available": False, "headers": [], "rows": []}

    headers: list[str] = []
    for r in rows:
        if r["header"] not in headers:
            headers.append(r["header"])
    # "TTM" belongs at the end, not wherever the year sort put it.
    if "TTM" in headers:
        headers = [h for h in headers if h != "TTM"] + ["TTM"]

    by_field: dict[str, dict[str, float | None]] = defaultdict(dict)
    for r in rows:
        by_field[r["field_name"]][r["header"]] = r["value"]

    # Profitability ratios arrive as fractions and must read as percentages.
    scale = 100.0 if family == "pr" else 1.0
    out_rows = [
        {
            "label": name,
            "unit": "percent" if family == "pr" else "ratio",
            "values": [
                None if values.get(h) is None else round(values[h] * scale, 2) for h in headers
            ],
        }
        for name, values in sorted(by_field.items())
    ]

    return {
        "symbol": symbol,
        "family": family,
        "statement_type": statement_type,
        "available": True,
        "headers": headers,
        "rows": out_rows,
    }


@router.get("/companies/{symbol}/shareholding")
def company_shareholding(symbol: str) -> dict[str, Any]:
    """Holding by group across quarters, newest last."""
    symbol = symbol.upper()
    with _engine().connect() as conn:
        rows = (
            conn.execute(select(shareholding).where(shareholding.c.symbol == symbol))
            .mappings()
            .all()
        )

    if not rows:
        return {"symbol": symbol, "available": False, "headers": [], "rows": []}

    months = {
        m: i
        for i, m in enumerate(
            ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1
        )
    }

    def key(label: str) -> tuple[int, int]:
        parts = label.split()
        if len(parts) == 2 and parts[0] in months:
            return (int(parts[1]), months[parts[0]])
        return (0, 0)

    headers = sorted({r["period_label"] for r in rows}, key=key)
    by_group: dict[str, dict[str, Any]] = defaultdict(dict)
    # Shareholder counts are per group and must be summed. Taking whichever
    # group happened to carry one reported Reliance as having 47 shareholders -
    # that is the promoter count, against roughly 4.6 million public holders.
    holders: dict[str, float] = defaultdict(float)
    for r in rows:
        by_group[r["group_name"]][r["period_label"]] = r["shareholding_pct"]
        if r["total_shareholders"]:
            holders[r["period_label"]] += r["total_shareholders"]

    labels = {
        "promoterAndPromoterGroup": "Promoters",
        "publicShareholding": "Public",
        "nonPromoterNonPublic": "Non-promoter non-public",
    }
    out = [
        {
            "label": labels.get(group, group),
            "unit": "percent",
            "values": [values.get(h) for h in headers],
        }
        for group, values in sorted(by_group.items())
    ]
    if holders:
        out.append(
            {
                "label": "No. of Shareholders",
                "unit": "count",
                "values": [holders.get(h) for h in headers],
            }
        )

    return {"symbol": symbol, "available": True, "headers": headers, "rows": out}


@router.get("/companies/{symbol}/peers")
def company_peers(symbol: str, limit: int = Query(10, le=50)) -> dict[str, Any]:
    """Peers built from our own classification, not FinEdge's peers endpoint.

    That endpoint returned four entries for ITC, some obscure. Sub-industry plus
    a market-cap band gives a set that matches what a reader expects. See
    docs/prd/02-data-source-inventory.md section 8.
    """
    symbol = symbol.upper()
    with _engine().connect() as conn:
        info = _company_row(conn, symbol)
        group = info["sub_industry"] or info["sector"] or info["industry"]
        if not group:
            return {"symbol": symbol, "group": None, "peers": []}

        rows = (
            conn.execute(
                text(
                    """
                SELECT s.symbol, s.name, s.current_price, s.pe, s.market_cap,
                       s.dividend_yield, s.net_profit, s.sales, s.returnoncapital,
                       s.returnonequity
                FROM company_snapshot s
                JOIN company c ON c.symbol = s.symbol
                WHERE COALESCE(c.sub_industry, c.sector, c.industry) = :group
                ORDER BY COALESCE(s.market_cap, 0) DESC
                LIMIT :limit
                """
                ),
                {"group": group, "limit": limit},
            )
            .mappings()
            .all()
        )

    peers = [dict(r) for r in rows]
    medians: dict[str, float | None] = {}
    for column in ("pe", "market_cap", "dividend_yield", "returnonequity", "returnoncapital"):
        values = sorted(p[column] for p in peers if p.get(column) is not None)
        medians[column] = values[len(values) // 2] if values else None

    return {
        "symbol": symbol,
        "group": group,
        "classification": {
            "macro_sector": info["macro_sector"],
            "industry": info["industry"],
            "sector": info["sector"],
            "sub_industry": info["sub_industry"],
        },
        "peers": peers,
        "median": medians,
        "count": len(peers),
    }


@router.get("/companies/{symbol}/prices")
def company_prices(symbol: str, limit: int = Query(2000, le=5000)) -> dict[str, Any]:
    """Daily OHLCV, oldest first."""
    symbol = symbol.upper()
    with _engine().connect() as conn:
        rows = (
            conn.execute(
                select(price_daily)
                .where(price_daily.c.symbol == symbol)
                .order_by(price_daily.c.quote_date.desc())
                .limit(limit)
            )
            .mappings()
            .all()
        )
    return {
        "symbol": symbol,
        "count": len(rows),
        "prices": [dict(r) for r in reversed(rows)],
    }


@router.get("/companies/{symbol}/corporate-actions")
def company_corporate_actions(symbol: str) -> dict[str, Any]:
    symbol = symbol.upper()
    with _engine().connect() as conn:
        rows = (
            conn.execute(
                select(corporate_action)
                .where(corporate_action.c.symbol == symbol)
                .order_by(corporate_action.c.ex_date.desc())
            )
            .mappings()
            .all()
        )
    grouped: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        grouped[r["action"]].append(dict(r))
    return {"symbol": symbol, "actions": grouped}


@router.get("/companies")
def company_list(limit: int = Query(50, le=500)) -> dict[str, Any]:
    """Largest companies, for landing-page suggestions."""
    with _engine().connect() as conn:
        rows = (
            conn.execute(
                select(company.c.symbol, company.c.name, quote.c.market_cap)
                .select_from(company.join(quote, quote.c.symbol == company.c.symbol))
                .order_by(quote.c.market_cap.desc().nulls_last())
                .limit(limit)
            )
            .mappings()
            .all()
        )
        total = conn.execute(select(func.count()).select_from(company)).scalar_one()
    return {"total": total, "companies": [dict(r) for r in rows]}

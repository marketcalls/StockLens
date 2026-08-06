"""Company data.

Everything a company page needs, as plain functions. No HTTP.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal

from sqlalchemy import Engine, func, select, text

from app.api.presentation import render, template_for
from app.db.engine import get_engine
from app.db.layer2 import (
    basic_financial,
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
from app.db.layer2 import (
    company as company_table,
)
from app.services.errors import NotFound

StatementCode = Literal["pl", "bs", "cf"]
PeriodKind = Literal["annual", "quarterly", "ttm"]
StatementType = Literal["c", "s"]

PERIOD_LIMIT = 16

UNIT_NOTE = "Figures in Rs. Crore unless stated otherwise"

KEY_RATIO_COLUMNS = (
    "pe",
    "pb",
    "ps",
    "book_value",
    "returnonequity",
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
)


def _engine(engine: Engine | None = None) -> Engine:
    return engine or get_engine()


def search(term: str, limit: int = 10, *, engine: Engine | None = None) -> list[dict[str, Any]]:
    """Company autocomplete.

    Ranked by exact symbol, then symbol prefix, then name prefix, then anywhere
    in the name, with market cap breaking ties so "rel" surfaces Reliance rather
    than an obscure small cap.
    """
    needle = term.strip().upper()
    if not needle:
        return []

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
    with _engine(engine).connect() as conn:
        rows = (
            conn.execute(
                sql,
                {
                    "term": needle,
                    "like": f"{needle}%",
                    "contains": f"%{needle}%",
                    "limit": limit,
                },
            )
            .mappings()
            .all()
        )
    return [
        {
            "symbol": r["symbol"],
            "name": r["name"],
            "sector": r["sector"],
            "current_price": r["current_price"],
            "market_cap": r["market_cap"],
        }
        for r in rows
    ]


def _row(conn, symbol: str) -> dict[str, Any]:
    row = (
        conn.execute(select(company_table).where(company_table.c.symbol == symbol))
        .mappings()
        .first()
    )
    if row is None:
        raise NotFound(f"No company with the symbol {symbol}", symbol=symbol)
    return dict(row)


def profile(symbol: str, *, engine: Engine | None = None) -> dict[str, Any]:
    """Identity, classification, latest quote, index membership, key ratios."""
    symbol = symbol.upper()
    with _engine(engine).connect() as conn:
        info = _row(conn, symbol)
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

    key_ratios = {k: snapshot[k] for k in KEY_RATIO_COLUMNS if k in snapshot} if snapshot else {}

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


def statements(
    symbol: str,
    code: StatementCode = "pl",
    period: PeriodKind = "annual",
    statement_type: StatementType = "c",
    *,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """A statement table, rendered with the row template for the company's schema.

    Falls back to the other statement type when the requested one is absent -
    only 2,510 of 5,630 companies file consolidated statements - and reports
    which was actually used.
    """
    symbol = symbol.upper()
    db = _engine(engine)

    with db.connect() as conn:
        info = _row(conn, symbol)

        def fetch(kind: str):
            return (
                conn.execute(
                    select(statement_period)
                    .where(
                        statement_period.c.symbol == symbol,
                        statement_period.c.statement_code == code,
                        statement_period.c.period_kind == period,
                        statement_period.c.statement_type == kind,
                    )
                    .order_by(statement_period.c.period_end.asc().nulls_last())
                )
                .mappings()
                .all()
            )

        periods = fetch(statement_type)
        if not periods:
            other = "s" if statement_type == "c" else "c"
            periods = fetch(other)
            if periods:
                statement_type = other  # type: ignore[assignment]

        periods = periods[-PERIOD_LIMIT:]
        if not periods:
            # Same keys as the available branch. A caller reading schema_kind
            # should not get a KeyError for a company that happens to have no
            # statements yet - the shape of a response must not depend on
            # whether there is data in it.
            return {
                "symbol": symbol,
                "statement_code": code,
                "period_kind": period,
                "statement_type": statement_type,
                "schema_kind": None,
                "available": False,
                "reason": "No data for this statement, period and type.",
                "headers": [],
                "result_dates": [],
                "rows": [],
                "unit_note": UNIT_NOTE,
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
        # annual and TTM series. Its headers look like "Mar 2023", which also
        # names a quarter, so merging it into a quarterly statement would place
        # annual figures in quarterly columns. Merge for annual and TTM only.
        headers = [p["header"] for p in periods] if period in ("annual", "ttm") else []
        if headers:
            derived = (
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
            for row in derived:
                period_id = header_to_id.get(row["header"])
                if period_id is not None:
                    by_period[period_id].setdefault(row["field_name"], row["value"])

    # Only the P&L carries family markers, so bs and cf periods are stored as
    # "unknown". Fall back to the family decided from the company's P&L.
    schema_kind = periods[0]["schema_kind"]
    if schema_kind in (None, "", "unknown"):
        schema_kind = info["schema_kind"]

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
        "unit_note": UNIT_NOTE,
    }


# FinEdge names the ratio families with two-letter codes. Nobody guesses "le"
# for leverage, so the readable name works too and is what the docs use.
RATIO_FAMILIES: dict[str, str] = {
    "pr": "profitability",
    "le": "leverage",
    "li": "liquidity",
    "ef": "efficiency",
}
_RATIO_ALIASES: dict[str, str] = {
    **{code: code for code in RATIO_FAMILIES},
    **{name: code for code, name in RATIO_FAMILIES.items()},
    "solvency": "le",  # what the leverage ratios are usually called
}


def ratios(
    symbol: str,
    family: str = "ef",
    statement_type: StatementType = "c",
    *,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """A ratio family as a time series, newest last.

    `family` takes either FinEdge's code or the readable name: "pr" or
    "profitability", "le"/"leverage"/"solvency", "li"/"liquidity",
    "ef"/"efficiency".
    """
    symbol = symbol.upper()
    requested = family
    family = _RATIO_ALIASES.get(family.strip().lower(), "")
    if not family:
        # Returning "available: false" here would claim the company has no such
        # ratios, when in fact the name does not exist. A caller cannot tell
        # those apart, and would go looking at the data.
        raise NotFound(
            f"No ratio family called {requested!r}. Use one of: "
            + ", ".join(sorted(RATIO_FAMILIES.values())),
            family=requested,
            known=sorted(RATIO_FAMILIES.values()),
        )
    with _engine(engine).connect() as conn:
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
    if "TTM" in headers:
        headers = [h for h in headers if h != "TTM"] + ["TTM"]

    by_field: dict[str, dict[str, float | None]] = defaultdict(dict)
    for r in rows:
        by_field[r["field_name"]][r["header"]] = r["value"]

    # Profitability ratios arrive as fractions and must read as percentages.
    scale = 100.0 if family == "pr" else 1.0
    return {
        "symbol": symbol,
        "family": family,
        "statement_type": statement_type,
        "available": True,
        "headers": headers,
        "rows": [
            {
                "label": name,
                "unit": "percent" if family == "pr" else "ratio",
                "values": [
                    None if values.get(h) is None else round(values[h] * scale, 2) for h in headers
                ],
            }
            for name, values in sorted(by_field.items())
        ],
    }


_MONTHS = {
    m: i
    for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        start=1,
    )
}


def _quarter_key(label: str) -> tuple[int, int]:
    """Order "Jun 2026" after "Mar 2026". Text order would not."""
    parts = label.split()
    if len(parts) == 2 and parts[0] in _MONTHS:
        return (int(parts[1]), _MONTHS[parts[0]])
    return (0, 0)


def shareholding_pattern(symbol: str, *, engine: Engine | None = None) -> dict[str, Any]:
    """Holding by group across quarters, newest last."""
    symbol = symbol.upper()
    with _engine(engine).connect() as conn:
        rows = (
            conn.execute(select(shareholding).where(shareholding.c.symbol == symbol))
            .mappings()
            .all()
        )

    if not rows:
        return {"symbol": symbol, "available": False, "headers": [], "rows": []}

    # Reliance carries 41 quarters back to 2016. Statements cap at PERIOD_LIMIT
    # and shareholding should read the same way; nobody scrolls ten years of it,
    # and the extra columns only push the recent ones off the page.
    headers = sorted({r["period_label"] for r in rows}, key=_quarter_key)[-PERIOD_LIMIT:]
    shown = set(headers)
    rows = [r for r in rows if r["period_label"] in shown]

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
    # A group with nothing across every quarter shown is a row of dashes.
    # "Non-promoter non-public" - employee trusts, depository receipts - is
    # absent for close to half of companies, and Reliance last reported it in
    # 2016. A blank row reads as neither zero nor unreported, so drop it rather
    # than make the reader guess which.
    out = [row for row in out if any(v is not None for v in row["values"])]
    if holders:
        out.append(
            {
                "label": "No. of Shareholders",
                "unit": "count",
                "values": [holders.get(h) for h in headers],
            }
        )

    return {"symbol": symbol, "available": True, "headers": headers, "rows": out}


def peers(symbol: str, limit: int = 10, *, engine: Engine | None = None) -> dict[str, Any]:
    """Peers built from our own classification.

    FinEdge's peers endpoint returned four entries for ITC, some obscure. Sub
    industry plus market cap ordering gives a set a reader recognises.
    """
    symbol = symbol.upper()
    db = _engine(engine)
    with db.connect() as conn:
        info = _row(conn, symbol)
        group = info["sub_industry"] or info["sector"] or info["industry"]
        if not group:
            return {"symbol": symbol, "group": None, "peers": [], "median": {}, "count": 0}

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

    rows = [dict(r) for r in rows]
    medians: dict[str, float | None] = {}
    for column in ("pe", "market_cap", "dividend_yield", "returnonequity", "returnoncapital"):
        values = sorted(p[column] for p in rows if p.get(column) is not None)
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
        "peers": rows,
        "median": medians,
        "count": len(rows),
    }


def prices(symbol: str, limit: int = 2000, *, engine: Engine | None = None) -> dict[str, Any]:
    """Daily OHLCV, oldest first."""
    symbol = symbol.upper()
    with _engine(engine).connect() as conn:
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
    return {"symbol": symbol, "count": len(rows), "prices": [dict(r) for r in reversed(rows)]}


def corporate_actions(symbol: str, *, engine: Engine | None = None) -> dict[str, Any]:
    symbol = symbol.upper()
    with _engine(engine).connect() as conn:
        rows = (
            conn.execute(
                select(corporate_action)
                .where(corporate_action.c.symbol == symbol)
                .order_by(corporate_action.c.ex_date.desc())
            )
            .mappings()
            .all()
        )
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        grouped[r["action"]].append(dict(r))
    return {"symbol": symbol, "actions": grouped}


def largest(limit: int = 50, *, engine: Engine | None = None) -> dict[str, Any]:
    """Largest companies by market cap, for landing-page suggestions."""
    with _engine(engine).connect() as conn:
        rows = (
            conn.execute(
                select(company_table.c.symbol, company_table.c.name, quote.c.market_cap)
                .select_from(company_table.join(quote, quote.c.symbol == company_table.c.symbol))
                .order_by(quote.c.market_cap.desc().nulls_last())
                .limit(limit)
            )
            .mappings()
            .all()
        )
        total = conn.execute(select(func.count()).select_from(company_table)).scalar_one()
    return {"total": total, "companies": [dict(r) for r in rows]}

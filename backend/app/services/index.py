"""Market indices.

FinEdge publishes 239 indices with their constituent lists, which is what makes
index pages and index-scoped screening possible at all.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, func, select, text

from app.db.engine import get_engine
from app.db.layer2 import (
    index_constituent,
    index_master,
    index_quote_daily,
    index_return,
)
from app.services.errors import NotFound

HORIZONS = ("1M", "3M", "6M", "1Y", "3Y", "5Y", "7Y", "10Y")

# Indices a reader is likely to recognise, in the order they should appear.
# FinEdge orders by its own market cap figure, which surfaces things like
# "BSE 1000 MULTICAP EQUAL SIZE WEIGHTED (25%)" ahead of the Nifty 50.
WELL_KNOWN = (
    "NIF50",
    "NIFTY50",
    "SENSEX",
    "BSESN",
    "NIF100",
    "NIF200",
    "NIF500",
    "BSE100",
    "BSE200",
    "BSE500",
    "NIFTYNEXT50",
    "NIFMIDCAP100",
    "NIFSMLCAP100",
    "NIFBANK",
    "NIFTYIT",
    "SNSXLRGCAP",
)


def _engine(engine: Engine | None = None) -> Engine:
    return engine or get_engine()


def _rank(index_symbol: str, name: str) -> tuple[int, str]:
    """Sort key putting recognisable indices first."""
    try:
        return (WELL_KNOWN.index(index_symbol), name)
    except ValueError:
        return (len(WELL_KNOWN), name)


def listing(
    *, index_type: str | None = None, limit: int = 300, engine: Engine | None = None
) -> dict[str, Any]:
    """Every index, with its latest quote, returns and constituent count."""
    db = _engine(engine)
    with db.connect() as conn:
        query = select(index_master)
        if index_type:
            query = query.where(index_master.c.index_type == index_type)
        indices = conn.execute(query).mappings().all()

        counts = dict(
            conn.execute(
                select(index_constituent.c.index_symbol, func.count()).group_by(
                    index_constituent.c.index_symbol
                )
            ).all()
        )
        quotes = {
            r["index_symbol"]: dict(r) for r in conn.execute(select(index_quote_daily)).mappings()
        }
        returns: dict[str, dict[str, float]] = {}
        for r in conn.execute(select(index_return)).mappings():
            returns.setdefault(r["index_symbol"], {})[r["horizon"]] = r["return_pct"]

    rows = []
    for row in indices:
        symbol = row["index_symbol"]
        quote = quotes.get(symbol, {})
        rows.append(
            {
                "index_symbol": symbol,
                "index_name": row["index_name"],
                "exchange": row["exchange"],
                "index_type": row["index_type"],
                "index_sub_type": row["index_sub_type"],
                "market_cap": row["market_cap"],
                "constituents": counts.get(symbol, 0),
                "close_price": quote.get("close_price"),
                "change_pct": quote.get("change_pct"),
                "pe": quote.get("pe"),
                "pb": quote.get("pb"),
                "div_yield": quote.get("div_yield"),
                "returns": returns.get(symbol, {}),
            }
        )

    rows.sort(key=lambda r: _rank(r["index_symbol"], r["index_name"]))
    return {"total": len(rows), "indices": rows[:limit]}


def detail(index_symbol: str, *, engine: Engine | None = None) -> dict[str, Any]:
    """One index: its quote, returns, and every constituent with fundamentals."""
    index_symbol = index_symbol.upper()
    db = _engine(engine)

    with db.connect() as conn:
        row = (
            conn.execute(
                select(index_master).where(func.upper(index_master.c.index_symbol) == index_symbol)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise NotFound(f"No index with the symbol {index_symbol}", index=index_symbol)

        actual = row["index_symbol"]
        quote = (
            conn.execute(
                select(index_quote_daily).where(index_quote_daily.c.index_symbol == actual)
            )
            .mappings()
            .first()
        )
        returns = {
            r["horizon"]: r["return_pct"]
            for r in conn.execute(
                select(index_return).where(index_return.c.index_symbol == actual)
            ).mappings()
        }

        # Constituents joined to the screener snapshot, so an index page shows
        # the same figures a screen would.
        members = (
            conn.execute(
                text(
                    """
                    SELECT m.symbol,
                           COALESCE(s.name, c.name) AS name,
                           c.symbol IS NOT NULL AS in_universe,
                           s.current_price, s.market_cap, s.pe, s.pb,
                           s.dividend_yield, s.returnonequity, s.returnoncapital,
                           s.net_profit, s.sales, s.change_pct,
                           c.sector
                    FROM index_constituent m
                    LEFT JOIN company_snapshot s ON s.symbol = m.symbol
                    LEFT JOIN company c ON c.symbol = m.symbol
                    WHERE m.index_symbol = :idx
                    ORDER BY COALESCE(s.market_cap, 0) DESC
                    """
                ),
                {"idx": actual},
            )
            .mappings()
            .all()
        )

    constituents = [dict(m) for m in members]
    for member in constituents:
        # SQLite has no boolean type, so the column arrives as 0/1.
        member["in_universe"] = bool(member["in_universe"])

    # Some index members are not equities at all - the BSE REIT & InvIT index is
    # entirely REITs and InvITs, and the SME IPO index is SME listings. They are
    # identified by scrip code and never appear in the equity symbol master, so
    # there is no company page to link to and no fundamentals to show. They are
    # still genuine constituents, so dropping them would misstate the index.
    outside = [c for c in constituents if not c["in_universe"]]

    # Market cap comes from the daily quote, which every listed company has, so
    # it says nothing about whether the statements were downloaded. Net profit
    # only exists after a backfill, which is the question being asked.
    with_data = [c for c in constituents if c.get("net_profit") is not None]

    def median(column: str) -> float | None:
        values = sorted(c[column] for c in with_data if c.get(column) is not None)
        return values[len(values) // 2] if values else None

    return {
        "index_symbol": actual,
        "index_name": row["index_name"],
        "exchange": row["exchange"],
        "index_type": row["index_type"],
        "index_sub_type": row["index_sub_type"],
        "market_cap": row["market_cap"],
        "quote": dict(quote) if quote else None,
        "returns": returns,
        "horizons": [h for h in HORIZONS if h in returns],
        "constituents": constituents,
        "count": len(constituents),
        # Only companies that have been backfilled carry fundamentals, so say
        # how many rather than implying the whole index is loaded.
        "with_fundamentals": len(with_data),
        # Members that are not equities, and so can never have either.
        "outside_universe": len(outside),
        "median": {
            "pe": median("pe"),
            "pb": median("pb"),
            "dividend_yield": median("dividend_yield"),
            "returnonequity": median("returnonequity"),
        },
    }


def movers(limit: int = 10, *, engine: Engine | None = None) -> dict[str, Any]:
    """Best and worst index performance today."""
    with _engine(engine).connect() as conn:
        rows = (
            conn.execute(
                select(
                    index_quote_daily.c.index_symbol,
                    index_master.c.index_name,
                    index_quote_daily.c.close_price,
                    index_quote_daily.c.change_pct,
                )
                .select_from(
                    index_quote_daily.join(
                        index_master,
                        index_master.c.index_symbol == index_quote_daily.c.index_symbol,
                    )
                )
                .where(index_quote_daily.c.change_pct.isnot(None))
            )
            .mappings()
            .all()
        )
    ordered = sorted(rows, key=lambda r: r["change_pct"], reverse=True)
    return {
        "gainers": [dict(r) for r in ordered[:limit]],
        "losers": [dict(r) for r in reversed(ordered[-limit:])],
    }

"""Layer 2 -> Layer 3: build `company_snapshot`.

One row per company, one column per screenable field, generated from the column
catalog. It is a cache and can always be rebuilt from Layer 2.

Two rules govern which period feeds a column:

- Prefer **consolidated** figures, falling back to standalone. Only 2,510 of
  5,630 companies have consolidated statements, and the reference product shows
  consolidated by default where it exists.
- Prefer the **TTM** period, falling back to the latest annual. TTM is the more
  current view and is what a valuation ratio should be read against.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from sqlalchemy import Engine, select, text

from app.db.layer2 import (
    basic_financial,
    company,
    corporate_action,
    index_constituent,
    metric,
    price_daily,
    price_ratio_daily,
    quote,
    ratio,
    shareholding,
    statement_line,
    statement_period,
)
from app.ingest.normalise import utcnow
from app.screener.catalog import Column, snapshot_ddl, stored

logger = logging.getLogger("stocklens.materialise")

# Rs. Crore. Below this an EV/EBITDA multiple is division by noise rather than
# a valuation.
MIN_EBITDA_FOR_MULTIPLE = 1.0

MEMBERSHIP_DDL = """
CREATE TABLE IF NOT EXISTS snapshot_index_membership (
  symbol TEXT NOT NULL,
  index_symbol TEXT NOT NULL,
  PRIMARY KEY (symbol, index_symbol)
)
"""

TRADING_DAYS_PER_YEAR = 248


def create_snapshot(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(snapshot_ddl()))
        conn.execute(text(MEMBERSHIP_DDL))
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS idx_snapshot_mcap ON company_snapshot(market_cap)")
        )
        for key in ("pe", "pb", "returnonequity", "totaldebttoequity", "sector"):
            conn.execute(
                text(f"CREATE INDEX IF NOT EXISTS idx_snapshot_{key} ON company_snapshot({key})")
            )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_membership_index "
                "ON snapshot_index_membership(index_symbol)"
            )
        )


def _best(values: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """First non-null value across a preference order."""
    for key in keys:
        value = values.get(key)
        if value is not None:
            return value
    return None


def _load_statement_values(engine: Engine) -> dict[str, dict[tuple[str, str], float]]:
    """Latest statement figure per (symbol, statement_code, field).

    Consolidated beats standalone; TTM beats the latest annual.
    """
    ranked: dict[str, dict[tuple[str, str], tuple[int, float]]] = defaultdict(dict)
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                statement_period.c.symbol,
                statement_period.c.statement_type,
                statement_period.c.statement_code,
                statement_period.c.period_kind,
                statement_period.c.year,
                statement_line.c.field_name,
                statement_line.c.value,
            )
            .select_from(
                statement_period.join(
                    statement_line, statement_line.c.period_id == statement_period.c.id
                )
            )
            .where(statement_period.c.period_kind.in_(("ttm", "annual")))
        )
        for row in rows:
            if row.value is None:
                continue
            # Higher rank wins. Consolidated +100, TTM +50, then recency.
            rank = 100 if row.statement_type == "c" else 0
            rank += 50 if row.period_kind == "ttm" else 0
            rank += row.year or 0
            slot = (row.statement_code, row.field_name)
            current = ranked[row.symbol].get(slot)
            if current is None or rank > current[0]:
                ranked[row.symbol][slot] = (rank, row.value)

    return {sym: {k: v for k, (_r, v) in slots.items()} for sym, slots in ranked.items()}


def _load_series(engine: Engine, table, family_col: str) -> dict[str, dict[tuple[str, str], float]]:
    """Latest value per (symbol, family, field) for a header-based series."""
    ranked: dict[str, dict[tuple[str, str], tuple[int, float]]] = defaultdict(dict)
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                table.c.symbol,
                table.c.statement_type,
                getattr(table.c, family_col),
                table.c.header,
                table.c.year,
                table.c.field_name,
                table.c.value,
            )
        )
        for row in rows:
            if row.value is None:
                continue
            rank = 100 if row.statement_type == "c" else 0
            rank += 50 if row.header == "TTM" else 0
            rank += row.year or 0
            slot = (row[2], row.field_name)
            current = ranked[row.symbol].get(slot)
            if current is None or rank > current[0]:
                ranked[row.symbol][slot] = (rank, row.value)
    return {sym: {k: v for k, (_r, v) in slots.items()} for sym, slots in ranked.items()}


def _load_metrics(engine: Engine) -> dict[str, dict[tuple[str, str], float]]:
    out: dict[str, dict[tuple[str, str], float]] = defaultdict(dict)
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                metric.c.symbol,
                metric.c.statement_type,
                metric.c.family,
                metric.c.field_name,
                metric.c.value,
            )
        )
        for row in rows:
            if row.value is None:
                continue
            slot = (row.family, row.field_name)
            # Consolidated wins; standalone only fills a gap.
            if slot not in out[row.symbol] or row.statement_type == "c":
                out[row.symbol][slot] = row.value
    return out


def _load_prices(engine: Engine) -> dict[str, dict[str, float]]:
    """Price-derived columns: CAGRs, moving averages, traded value."""
    series: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                price_daily.c.symbol,
                price_daily.c.quote_date,
                price_daily.c.close,
                price_daily.c.volume,
            ).order_by(price_daily.c.symbol, price_daily.c.quote_date)
        )
        for row in rows:
            if row.close is not None:
                series[row.symbol].append((row.quote_date, row.close, row.volume or 0.0))

    out: dict[str, dict[str, float]] = {}
    for symbol, points in series.items():
        closes = [p[1] for p in points]
        latest = closes[-1]
        values: dict[str, float] = {}

        for years, key in (
            (1, "price_cagr_1y"),
            (3, "price_cagr_3y"),
            (5, "price_cagr_5y"),
            (10, "price_cagr_10y"),
        ):
            offset = years * TRADING_DAYS_PER_YEAR
            if len(closes) > offset:
                past = closes[-offset - 1]
                if past > 0:
                    # Annualised, so 3Y and 5Y are comparable to 1Y.
                    values[key] = ((latest / past) ** (1 / years) - 1) * 100

        if len(closes) >= 50:
            values["dma_50"] = sum(closes[-50:]) / 50
        if len(closes) >= 200:
            dma200 = sum(closes[-200:]) / 200
            values["dma_200"] = dma200
            if dma200 > 0:
                values["price_to_dma200"] = latest / dma200

        recent = points[-30:]
        if recent:
            # Rupees -> Rs Crore.
            values["avg_traded_value_30d"] = (
                sum(close * vol for _d, close, vol in recent) / len(recent) * 1e-7
            )
        out[symbol] = values
    return out


def _load_valuation(engine: Engine) -> dict[str, dict[str, float]]:
    """Most recent daily valuation ratios, consolidated preferred.

    Consolidated must be ranked explicitly. Comparing a (date, statement_type)
    tuple sorts "s" above "c", which silently picked standalone and reported
    RELIANCE at a P/E of 45.7 instead of 24.0 - standalone profit is a fraction
    of consolidated for a holding company.
    """
    out: dict[str, dict[str, float]] = {}
    best: dict[str, tuple[str, int]] = {}
    with engine.connect() as conn:
        rows = conn.execute(select(price_ratio_daily)).mappings()
        for row in rows:
            symbol = row["symbol"]
            marker = (row["quote_date"], 1 if row["statement_type"] == "c" else 0)
            if symbol in best and marker <= best[symbol]:
                continue
            best[symbol] = marker
            out[symbol] = {
                k: row[k] for k in ("pe", "pb", "ptb", "ps", "pfcf") if row[k] is not None
            }
    return out


def _load_shareholding(engine: Engine) -> dict[str, dict[str, float]]:
    latest: dict[str, str] = {}
    rows_by_symbol: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
    with engine.connect() as conn:
        for row in conn.execute(select(shareholding)).mappings():
            symbol, label = row["symbol"], row["period_label"]
            # Labels are "Jun 2026"; compare by parsed order rather than text.
            if symbol not in latest or _label_key(label) > _label_key(latest[symbol]):
                latest[symbol] = label
            rows_by_symbol[symbol].setdefault(label, {})
            rows_by_symbol[symbol][label][row["group_name"]] = row  # type: ignore[assignment]

    out: dict[str, dict[str, float]] = {}
    for symbol, label in latest.items():
        groups = rows_by_symbol[symbol][label]
        promoter = groups.get("promoterAndPromoterGroup")
        public = groups.get("publicShareholding")
        values: dict[str, float] = {}
        if promoter:
            if promoter["shareholding_pct"] is not None:
                values["promoter_holding"] = promoter["shareholding_pct"]
            if promoter["pledged_pct"] is not None:
                values["promoter_pledge"] = promoter["pledged_pct"]
        if public and public["shareholding_pct"] is not None:
            values["public_holding"] = public["shareholding_pct"]
        out[symbol] = values
    return out


_MONTHS = {
    m: i
    for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1
    )
}


def _label_key(label: str) -> tuple[int, int]:
    parts = label.split()
    if len(parts) == 2 and parts[0] in _MONTHS:
        return (int(parts[1]), _MONTHS[parts[0]])
    return (0, 0)


def _load_dividends(engine: Engine) -> dict[str, float]:
    """Trailing 12 month dividend per share."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                corporate_action.c.symbol, corporate_action.c.ex_date, corporate_action.c.amount
            ).where(corporate_action.c.action == "dividend")
        ).all()
    latest_date = max((r.ex_date for r in rows if r.ex_date), default=None)
    if not latest_date:
        return {}
    cutoff = f"{int(latest_date[:4]) - 1}{latest_date[4:]}"
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        if row.amount and row.ex_date and row.ex_date > cutoff:
            totals[row.symbol] += row.amount
    return dict(totals)


def _compute(
    symbol: str,
    values: dict[str, Any],
    prices: dict[str, float],
    dividends: dict[str, float],
) -> None:
    """Fill the StockLens-computed columns from what is already resolved."""
    values.update(prices)

    price = values.get("current_price")
    mcap = values.get("market_cap")
    debt = values.get("total_debt")
    cash = values.get("total_cash")
    ebitda = values.get("ebitda")
    pe = values.get("pe")

    dividend = dividends.get(symbol)
    if dividend and price:
        values["dividend_yield"] = dividend / price * 100

    if mcap is not None:
        ev = mcap + (debt or 0.0) - (cash or 0.0)
        values["enterprise_value"] = ev
        # A denominator this small is noise, not a measurement. VAML reports
        # EBITDA of -0.03 Cr against an enterprise value of 187,894 Cr, which
        # divides out to -6,242,332 - a figure that sorts to the front of any
        # screen on EV/EBITDA and means nothing. A listed company with under a
        # crore of operating profit has no meaningful multiple.
        if ebitda is not None and abs(ebitda) >= MIN_EBITDA_FOR_MULTIPLE:
            values["ev_ebitda"] = ev / ebitda

    if pe and pe != 0:
        values["earnings_yield"] = 100 / pe

    high52, low52 = values.get("high52"), values.get("low52")
    if price and high52:
        values["down_from_52w_high"] = (high52 - price) / high52 * 100
    if price and low52 and low52 > 0:
        values["up_from_52w_low"] = (price - low52) / low52 * 100

    cfo, pat = values.get("cfo"), values.get("net_profit")
    if cfo is not None and pat:
        values["cfo_to_pat"] = cfo / pat


def _resolve_column(
    column: Column,
    symbol: str,
    company_row: dict[str, Any],
    quote_row: dict[str, Any],
    statements: dict[tuple[str, str], float],
    basics: dict[tuple[str, str], float],
    ratios: dict[tuple[str, str], float],
    metrics: dict[tuple[str, str], float],
    valuation: dict[str, float],
) -> Any:
    if column.source == "company":
        return company_row.get(column.path[0])
    if column.source == "quote":
        raw = quote_row.get(column.path[0])
        return raw * column.scale if isinstance(raw, int | float) else raw
    if column.source == "statement":
        # Try the primary field, then each schema-specific alternative. Banks and
        # insurers name their profit and revenue lines differently, and without
        # this they screen as having no profit at all.
        for field in (column.path[1], *column.fallbacks):
            raw = statements.get((column.path[0], field))
            if raw is not None:
                return raw * column.scale
        return None
    if column.source == "basic":
        for field in (column.path[1], *column.fallbacks):
            raw = basics.get((column.path[0], field))
            if raw is not None:
                return raw * column.scale
        return None
    if column.source == "ratio":
        raw = ratios.get((column.path[0], column.path[1]))
        return raw * column.scale if raw is not None else None
    if column.source == "metric":
        raw = metrics.get((column.path[0], column.path[1]))
        return raw * column.scale if raw is not None else None
    if column.source == "computed" and column.key in ("pe", "pb", "ps", "pfcf", "ptb"):
        return valuation.get(column.key)
    return None


def materialise(engine: Engine) -> dict[str, int]:
    """Rebuild company_snapshot from Layer 2. Returns counts."""
    create_snapshot(engine)

    statements = _load_statement_values(engine)
    basics = _load_series(engine, basic_financial, "statement_code")
    ratios = _load_series(engine, ratio, "family")
    metrics = _load_metrics(engine)
    prices = _load_prices(engine)
    valuation = _load_valuation(engine)
    holdings = _load_shareholding(engine)
    dividends = _load_dividends(engine)

    with engine.connect() as conn:
        companies = {r["symbol"]: dict(r) for r in conn.execute(select(company)).mappings()}
        quotes = {r["symbol"]: dict(r) for r in conn.execute(select(quote)).mappings()}
        memberships = conn.execute(select(index_constituent)).mappings().all()
        # The schema family is decided when a P&L is normalised, so it lives on
        # statement_period. Carry it onto the company so the renderer and the
        # screener can both see which statement shape a company reports in.
        for row in conn.execute(
            select(statement_period.c.symbol, statement_period.c.schema_kind)
            .where(
                statement_period.c.statement_code == "pl",
                statement_period.c.schema_kind.isnot(None),
                statement_period.c.schema_kind != "unknown",
            )
            .distinct()
        ):
            if row.symbol in companies:
                companies[row.symbol]["schema_kind"] = row.schema_kind

    # Persist it back onto the company row too. The company page reads the
    # family from there to pick a statement layout, and balance sheet and cash
    # flow periods are stored as "unknown" because only the P&L carries markers.
    with engine.begin() as conn:
        for symbol, row in companies.items():
            if row.get("schema_kind"):
                conn.execute(
                    company.update()
                    .where(company.c.symbol == symbol)
                    .values(schema_kind=row["schema_kind"])
                )

    rows: list[dict[str, Any]] = []
    populated = 0
    for symbol, company_row in companies.items():
        values: dict[str, Any] = {"symbol": symbol, "updated_at": utcnow()}
        for column in stored():
            values[column.key] = _resolve_column(
                column,
                symbol,
                company_row,
                quotes.get(symbol, {}),
                statements.get(symbol, {}),
                basics.get(symbol, {}),
                ratios.get(symbol, {}),
                metrics.get(symbol, {}),
                valuation.get(symbol, {}),
            )
        _compute(symbol, values, prices.get(symbol, {}), dividends)
        values.update(holdings.get(symbol, {}))
        if values.get("net_profit") is not None or values.get("sales") is not None:
            populated += 1
        rows.append(values)

    columns = ["symbol", "updated_at", *[c.key for c in stored()]]
    placeholders = ", ".join(f":{name}" for name in columns)
    sql = text(
        f"INSERT OR REPLACE INTO company_snapshot ({', '.join(columns)}) VALUES ({placeholders})"
    )
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM company_snapshot"))
        for start in range(0, len(rows), 200):
            conn.execute(sql, [{k: r.get(k) for k in columns} for r in rows[start : start + 200]])
        conn.execute(text("DELETE FROM snapshot_index_membership"))
        known = set(companies)
        links = [
            {"symbol": m["symbol"], "index_symbol": m["index_symbol"]}
            for m in memberships
            if m["symbol"] in known
        ]
        for start in range(0, len(links), 400):
            conn.execute(
                text(
                    "INSERT OR IGNORE INTO snapshot_index_membership (symbol, index_symbol) "
                    "VALUES (:symbol, :index_symbol)"
                ),
                links[start : start + 400],
            )

    logger.info("materialised %d companies, %d with fundamentals", len(rows), populated)
    return {
        "companies": len(rows),
        "with_fundamentals": populated,
        "index_links": len(links),
        "columns": len(stored()),
    }

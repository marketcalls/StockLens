"""Layer 1 raw payloads -> Layer 2 normalised rows.

Every function here is pure: raw payload in, list of row dicts out. Persistence
lives in store.py. That split keeps the awkward parts - schema classification,
the inverted sector hierarchy, FinEdge's several date formats - unit-testable
without a database.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.ingest.schemas import classify_statement_rows

# FinEdge returns dates in at least four shapes:
#   "2026-08-06"  "20260331"  "27-May-2026"  "2026-08-06 19:27:07"
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_COMPACT_DATE = re.compile(r"^\d{8}$")
_DMY_DATE = re.compile(r"^\d{1,2}-[A-Za-z]{3}-\d{4}$")
_ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}")

_MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"],
        start=1,
    )
}


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def parse_date(value: Any) -> str | None:
    """Normalise any FinEdge date to ISO `YYYY-MM-DD`.

    Returns None rather than guessing when the shape is unrecognised, so bad
    input surfaces as a gap on the data-quality report instead of a wrong date.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if _ISO_DATE.match(text):
        return text
    if _ISO_DATETIME.match(text):
        return text[:10]
    if _COMPACT_DATE.match(text):
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    if _DMY_DATE.match(text):
        day, mon, year = text.split("-")
        month = _MONTHS.get(mon.lower())
        if month:
            return f"{year}-{month:02d}-{int(day):02d}"
    return None


def parse_number(value: Any) -> float | None:
    """Coerce to float, treating blanks and non-numerics as missing, not zero."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text or text in {"-", "NA", "N/A", "null"}:
        return None
    if text.endswith("%"):
        text = text[:-1]
    try:
        return float(text)
    except ValueError:
        return None


def parse_percent_string(value: Any) -> float | None:
    """`change` arrives as a string like "0.28%" or "-0.75%"."""
    if value is None:
        return None
    return parse_number(str(value).replace("%", ""))


def normalise_symbols(payload: Any) -> list[dict[str, Any]]:
    """`/api/v1/stock-symbols` -> company rows (identity only)."""
    if not isinstance(payload, list):
        return []
    now = utcnow()
    rows = []
    for item in payload:
        symbol = (item.get("symbol") or "").strip()
        if not symbol:
            continue
        rows.append(
            {
                "symbol": symbol,
                "name": (item.get("name") or symbol).strip(),
                "nse_code": item.get("nse_code") or None,
                "bse_code": item.get("bse_code") or None,
                "consolidated_ind": bool(item.get("consolidated_ind")),
                "updated_at": now,
            }
        )
    return rows


def normalise_profile(symbol: str, payload: Any) -> dict[str, Any] | None:
    """`/api/v1/company-profile/{symbol}` -> classification fields.

    FinEdge's hierarchy is inverted relative to the conventional one. For
    RELIANCE it returns industry="Petroleum Products" and
    sector="Refineries & Marketing" - the `sector` value is narrower than the
    `industry` value. We keep both raw and expose a corrected broad-to-narrow
    order: macro_sector > industry > sector > sub_industry.
    See docs/prd/02-data-source-inventory.md section 8.
    """
    if not isinstance(payload, dict) or not payload:
        return None
    return {
        "symbol": symbol,
        "macro_sector_raw": payload.get("macro_sector"),
        "sector_raw": payload.get("sector"),
        "industry_raw": payload.get("industry"),
        "sub_industry_raw": payload.get("sub_industry"),
        "macro_sector": _clean(payload.get("macro_sector")),
        "industry": _clean(payload.get("industry")),
        "sector": _clean(payload.get("sector")),
        "sub_industry": _clean(payload.get("sub_industry")),
        "website": payload.get("website") or None,
        "description": payload.get("description") or None,
        "market_cap": parse_number(payload.get("market_cap")),
        "name": payload.get("name") or None,
        "updated_at": utcnow(),
    }


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalise_quotes(payload: Any) -> list[dict[str, Any]]:
    """`/api/v1/quote` with no symbol -> one row per company.

    This is the single call that refreshes the whole universe.
    """
    if not isinstance(payload, dict):
        return []
    now = utcnow()
    rows = []
    for symbol, data in payload.items():
        if not isinstance(data, dict) or not data:
            continue
        rows.append(
            {
                "symbol": symbol,
                "current_price": parse_number(data.get("current_price")),
                "open_price": parse_number(data.get("open_price")),
                "high_price": parse_number(data.get("high_price")),
                "low_price": parse_number(data.get("low_price")),
                "volume": parse_number(data.get("volume")),
                "change_pct": parse_percent_string(data.get("change")),
                "high52": parse_number(data.get("high52")),
                "low52": parse_number(data.get("low52")),
                "market_cap": parse_number(data.get("market_cap")),
                "shares": parse_number(data.get("shares")),
                "trade_time": data.get("tradetime"),
                "updated_at": now,
            }
        )
    return rows


def normalise_statements(
    symbol: str,
    statement_type: str,
    statement_code: str,
    period_kind: str,
    payload: Any,
) -> tuple[list[dict[str, Any]], list[list[dict[str, Any]]], str]:
    """`/api/v1/financials/{symbol}` -> (periods, lines per period, schema_kind).

    The schema family is classified once per statement from the union of all
    periods, then stamped on each period row.
    """
    rows = payload.get("financials") if isinstance(payload, dict) else None
    if not rows:
        return [], [], "unknown"

    classification = classify_statement_rows(rows) if statement_code == "pl" else None
    schema_kind = classification.kind if classification else "unknown"

    periods: list[dict[str, Any]] = []
    lines: list[list[dict[str, Any]]] = []

    for row in rows:
        header = row.get("header") or _derive_header(row)
        periods.append(
            {
                "symbol": symbol,
                "statement_type": statement_type,
                "statement_code": statement_code,
                "period_kind": period_kind,
                "header": header,
                "year": _as_int(row.get("year")),
                "period_start": parse_date(row.get("period_start")),
                "period_end": parse_date(row.get("period_end")),
                "result_date": parse_date(row.get("result_date")),
                "schema_kind": schema_kind,
            }
        )
        lines.append(
            [
                {"field_name": key, "value": parse_number(value)}
                for key, value in row.items()
                if key not in _NON_NUMERIC_KEYS
            ]
        )

    return periods, lines, schema_kind


_NON_NUMERIC_KEYS = frozenset({"header", "period_start", "period_end", "result_date", "year"})


def _derive_header(row: dict[str, Any]) -> str | None:
    """Some rows carry no `header`; build one from the period end."""
    end = parse_date(row.get("period_end"))
    if not end:
        return None
    year, month, _ = end.split("-")
    names = {
        "03": "Mar",
        "06": "Jun",
        "09": "Sep",
        "12": "Dec",
        "01": "Jan",
        "02": "Feb",
        "04": "Apr",
        "05": "May",
        "07": "Jul",
        "08": "Aug",
        "10": "Oct",
        "11": "Nov",
    }
    return f"{names.get(month, month)} {year}"


def _as_int(value: Any) -> int | None:
    number = parse_number(value)
    return int(number) if number is not None else None


def normalise_index_master(payload: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """`/api/v1/index/master` -> (indices, constituent links).

    The constituent lists are what make index membership badges and
    index-scoped screening possible.
    """
    if not isinstance(payload, list):
        return [], []
    now = utcnow()
    indices, constituents = [], []
    for item in payload:
        index_symbol = (item.get("index_symbol") or "").strip()
        if not index_symbol:
            continue
        indices.append(
            {
                "index_symbol": index_symbol,
                "index_name": item.get("index_name") or index_symbol,
                "exchange": item.get("exchange") or None,
                "index_type": item.get("index_type") or None,
                "index_sub_type": item.get("index_sub_type") or None,
                "market_cap": parse_number(item.get("market_cap")),
                "updated_at": now,
            }
        )
        for symbol in item.get("constituents") or []:
            if symbol:
                constituents.append({"index_symbol": index_symbol, "symbol": symbol})
    return indices, constituents


def normalise_index_quotes(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    rows = []
    for item in payload:
        index_symbol = (item.get("index_symbol") or "").strip()
        quote_date = parse_date(item.get("quote_date"))
        if not index_symbol or not quote_date:
            continue
        rows.append(
            {
                "index_symbol": index_symbol,
                "quote_date": quote_date,
                "close_price": parse_number(item.get("close_price")),
                "open_price": parse_number(item.get("open_price")),
                "high_price": parse_number(item.get("high_price")),
                "low_price": parse_number(item.get("low_price")),
                "change_pct": parse_number(item.get("change_pct")),
                "points_change": parse_number(item.get("points_change")),
                "pe": parse_number(item.get("pe")),
                "pb": parse_number(item.get("pb")),
                "div_yield": parse_number(item.get("div_yield")),
                "market_cap": parse_number(item.get("market_cap")),
                "turnover": parse_number(item.get("turnover")),
                "volume": parse_number(item.get("volume")),
            }
        )
    return rows


HORIZONS = ("1M", "3M", "6M", "1Y", "3Y", "5Y", "7Y", "10Y")


def normalise_index_returns(payload: Any) -> list[dict[str, Any]]:
    """`/api/v1/index/price-returns` -> one row per index per horizon.

    A zero return means the index did not exist that far back, not a flat
    return, so zeros are dropped rather than stored as real data.
    """
    if not isinstance(payload, list):
        return []
    rows = []
    for item in payload:
        index_symbol = (item.get("index_symbol") or "").strip()
        if not index_symbol:
            continue
        dates = item.get("dates") or {}
        for horizon in HORIZONS:
            value = parse_number(item.get(horizon))
            if value is None or value == 0:
                continue
            rows.append(
                {
                    "index_symbol": index_symbol,
                    "horizon": horizon,
                    "return_pct": value,
                    "as_of": parse_date(dates.get("last_date")),
                }
            )
    return rows


def normalise_prices(symbol: str, payload: Any) -> list[dict[str, Any]]:
    """`/api/v1/daily-quotes/{symbol}` -> OHLCV rows."""
    series = payload.get("price") if isinstance(payload, dict) else None
    if not series:
        return []
    rows = []
    for item in series:
        quote_date = parse_date(item.get("quote_date"))
        if not quote_date:
            continue
        values = {
            "open": parse_number(item.get("open_price")),
            "high": parse_number(item.get("high_price")),
            "low": parse_number(item.get("low_price")),
            "close": parse_number(item.get("close_price")),
            "volume": parse_number(item.get("volume")),
        }
        # An all-zero row means no trading happened, not that the share was
        # worth nothing. FinEdge emits these for Diwali Muhurat sessions and
        # special Saturday sittings. Stored literally they draw a vertical
        # spike to zero on every price chart.
        if all(v in (0, None) for v in values.values()):
            continue
        rows.append({"symbol": symbol, "quote_date": quote_date, **values})
    return rows


def _series_rows(
    payload: Any,
    container: str,
    key_fields: dict[str, Any],
) -> list[dict[str, Any]]:
    """Shared shape for `{container: [{header, year, <field>: value, ...}]}`.

    Used by basic-financials and ratios, which both return a time series of
    flat numeric maps tagged with a `header` such as "TTM" or "Mar 2026".
    """
    series = payload.get(container) if isinstance(payload, dict) else None
    if not series:
        return []
    rows = []
    for entry in series:
        header = entry.get("header")
        if not header:
            continue
        year = _as_int(entry.get("year"))
        for name, raw in entry.items():
            if name in ("header", "year"):
                continue
            rows.append(
                {
                    **key_fields,
                    "header": header,
                    "field_name": name,
                    "year": year,
                    "value": parse_number(raw),
                }
            )
    return rows


def normalise_basic_financials(
    symbol: str, statement_type: str, statement_code: str, payload: Any
) -> list[dict[str, Any]]:
    """`/api/v1/basic-financials/{symbol}` -> long rows.

    These are FinEdge's own derived aggregates (ebitda, fcf, book value and so
    on), so we store them rather than recompute and risk disagreeing with the
    figures shown elsewhere.
    """
    return _series_rows(
        payload,
        "ratios",
        {"symbol": symbol, "statement_type": statement_type, "statement_code": statement_code},
    )


def normalise_ratios(
    symbol: str, statement_type: str, family: str, payload: Any
) -> list[dict[str, Any]]:
    """`/api/v1/ratios/{symbol}` -> long rows, one per ratio per period."""
    return _series_rows(
        payload,
        "ratios",
        {"symbol": symbol, "statement_type": statement_type, "family": family},
    )


def normalise_metrics(
    symbol: str, statement_type: str, family: str, payload: Any
) -> list[dict[str, Any]]:
    """`/api/v1/financial-metrics/{symbol}` -> long rows.

    Unlike ratios these are point-in-time, not a series: one growth or average
    figure per field.
    """
    metrics = payload.get("financial_metrics") if isinstance(payload, dict) else None
    if not metrics:
        return []
    return [
        {
            "symbol": symbol,
            "statement_type": statement_type,
            "family": family,
            "field_name": name,
            "value": parse_number(raw),
        }
        for name, raw in metrics.items()
    ]


def normalise_price_ratios_daily(
    symbol: str, statement_type: str, payload: Any
) -> list[dict[str, Any]]:
    series = payload.get("price_ratios") if isinstance(payload, dict) else None
    if not series:
        return []
    rows = []
    for entry in series:
        quote_date = parse_date(entry.get("quote_date"))
        if not quote_date:
            continue
        rows.append(
            {
                "symbol": symbol,
                "statement_type": statement_type,
                "quote_date": quote_date,
                "pe": parse_number(entry.get("pe")),
                "pb": parse_number(entry.get("pb")),
                "ptb": parse_number(entry.get("ptb")),
                "ps": parse_number(entry.get("ps")),
                "pfcf": parse_number(entry.get("pfcf")),
            }
        )
    return rows


def normalise_price_ratios_annual(
    symbol: str, statement_type: str, payload: Any
) -> list[dict[str, Any]]:
    """Annual valuation series.

    A zero here means the ratio could not be computed for that year, not that
    the company traded at zero times book, so zeros become None.
    """
    series = payload.get("price_ratios") if isinstance(payload, dict) else None
    if not series:
        return []
    rows = []
    for entry in series:
        header = entry.get("header")
        if not header:
            continue
        rows.append(
            {
                "symbol": symbol,
                "statement_type": statement_type,
                "header": header,
                "year": _as_int(entry.get("year")),
                "average_price": parse_number(entry.get("average_price")),
                **{
                    name: _zero_to_none(parse_number(entry.get(name)))
                    for name in ("pe", "pb", "ptb", "ps", "pfcf")
                },
            }
        )
    return rows


def _zero_to_none(value: float | None) -> float | None:
    return None if value == 0 else value


def normalise_dividends(symbol: str, payload: Any) -> list[dict[str, Any]]:
    entries = payload.get("dividend") if isinstance(payload, dict) else None
    if not entries:
        return []
    rows = []
    for entry in entries:
        ex_date = parse_date(entry.get("date"))
        if not ex_date:
            continue
        rows.append(
            {
                "symbol": symbol,
                "action": "dividend",
                "ex_date": ex_date,
                "subject": entry.get("dividend_type") or "",
                "amount": parse_number(entry.get("amount")),
                "dividend_type": entry.get("dividend_type"),
            }
        )
    return rows


def normalise_corporate_action(symbol: str, action: str, payload: Any) -> list[dict[str, Any]]:
    entries = payload.get(action) if isinstance(payload, dict) else None
    if not entries:
        return []
    rows = []
    for entry in entries:
        ex_date = parse_date(entry.get("date"))
        if not ex_date:
            continue
        rows.append(
            {
                "symbol": symbol,
                "action": action,
                "ex_date": ex_date,
                "subject": entry.get("action") or "",
                "amount": parse_number(entry.get("amount")),
                "dividend_type": None,
            }
        )
    return rows


# Groups reported by the shareholding distribution endpoint.
SHAREHOLDING_GROUPS = (
    "promoterAndPromoterGroup",
    "publicShareholding",
    "nonPromoterNonPublic",
)


def normalise_shareholding(symbol: str, payload: Any) -> list[dict[str, Any]]:
    """`/api/v1/shareholdings/distribution/{symbol}` -> one row per group per quarter."""
    periods = payload.get("distributions") if isinstance(payload, dict) else None
    if not periods:
        return []
    rows = []
    for period in periods:
        label = period.get("date_header")
        if not label:
            continue
        for group in period.get("distributions") or []:
            name = group.get("group")
            data = group.get("data") or {}
            if not name:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "period_label": label,
                    "group_name": name,
                    "shareholding_pct": parse_number(data.get("shareholdingPct")),
                    "total_shares": parse_number(data.get("totalShares")),
                    "total_shareholders": parse_number(data.get("totalShareholders")),
                    "pledged_pct": parse_number(data.get("pledgedSharesPct")),
                    "locked_in_pct": parse_number(data.get("lockedInSharesPct")),
                }
            )
    return rows

"""The FinEdge endpoint matrix.

`symbol_endpoint_matrix()` returns the full set of per-symbol calls the backfill
makes. It is ~63 calls per symbol, matching the budget in
docs/prd/06-data-model-and-ingestion.md.

Invalid parameter combinations are excluded deliberately rather than discovered
at runtime: `period=ytd` is documented as allowed but the API rejects it
("combination pl, ytd is invalid"), and cash flow / balance sheet do not accept
`ttm`. See docs/prd/09-open-questions.md Q15.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

STATEMENT_TYPES = ("s", "c")  # standalone, consolidated
STATEMENT_CODES = ("pl", "bs", "cf")
RATIO_FAMILIES = ("pr", "le", "li", "ef")  # profitability, leverage, liquidity, efficiency
METRIC_FAMILIES = ("gr", "av", "cu")  # growth, average, cumulative
CORP_ACTIONS = ("split", "bonus", "rights")

# Verified valid period values per statement code.
VALID_PERIODS: dict[str, tuple[str, ...]] = {
    "pl": ("annual", "quarterly", "ttm"),
    "bs": ("annual", "quarterly"),
    "cf": ("annual", "quarterly"),
}

# Statement codes accepted by /segment-revenue (cf is not supported).
SEGMENT_CODES = ("pl", "bs")
SEGMENT_PERIODS = ("annual", "quarterly")


@dataclass(frozen=True)
class Call:
    """One planned FinEdge request."""

    endpoint: str
    params: dict[str, Any] = field(default_factory=dict)
    symbol: str | None = None

    @property
    def key(self) -> tuple[str, str, tuple[tuple[str, Any], ...]]:
        return (self.symbol or "", self.endpoint, tuple(sorted(self.params.items())))


def symbol_endpoint_matrix(symbol: str) -> list[Call]:
    """Every per-symbol call needed for a complete company record."""
    calls: list[Call] = [Call(f"/api/v1/company-profile/{symbol}", {}, symbol)]

    for code in STATEMENT_CODES:
        for st in STATEMENT_TYPES:
            for period in VALID_PERIODS[code]:
                calls.append(
                    Call(
                        f"/api/v1/financials/{symbol}",
                        {"statement_type": st, "statement_code": code, "period": period},
                        symbol,
                    )
                )
            calls.append(
                Call(
                    f"/api/v1/basic-financials/{symbol}",
                    {"statement_type": st, "statement_code": code},
                    symbol,
                )
            )

    for st in STATEMENT_TYPES:
        for family in RATIO_FAMILIES:
            calls.append(
                Call(
                    f"/api/v1/ratios/{symbol}", {"statement_type": st, "ratio_type": family}, symbol
                )
            )
        for family in METRIC_FAMILIES:
            calls.append(
                Call(
                    f"/api/v1/financial-metrics/{symbol}",
                    {"statement_type": st, "ratio_type": family},
                    symbol,
                )
            )
        calls.append(Call(f"/api/v1/annual-price-ratios/{symbol}", {"statement_type": st}, symbol))
        calls.append(Call(f"/api/v1/daily-price-ratios/{symbol}", {"statement_type": st}, symbol))
        calls.append(
            Call(f"/api/v1/notes/{symbol}", {"statement_type": st, "period": "annual"}, symbol)
        )
        for code in SEGMENT_CODES:
            for period in SEGMENT_PERIODS:
                calls.append(
                    Call(
                        f"/api/v1/segment-revenue/{symbol}",
                        {"statement_type": st, "statement_code": code, "period": period},
                        symbol,
                    )
                )

    calls.append(Call(f"/api/v1/daily-quotes/{symbol}", {"from": 2013}, symbol))
    calls.append(Call(f"/api/v1/peers/{symbol}", {}, symbol))
    calls.append(Call(f"/api/v1/dividend/{symbol}", {}, symbol))

    for action in CORP_ACTIONS:
        calls.append(Call(f"/api/v1/corporate-actions/{action}/{symbol}", {}, symbol))

    for path in ("pattern", "summary", "distribution"):
        calls.append(
            Call(f"/api/v1/shareholdings/{path}/{symbol}", {"period": "quarterly"}, symbol)
        )
    calls.append(Call(f"/api/v1/shareholdings/ownership-current/{symbol}", {}, symbol))

    return calls


def universe_endpoints() -> list[Call]:
    """Calls that cover the whole market in a single request each."""
    return [
        Call("/api/v1/stock-symbols"),
        # No `symbol` param returns all 5,630 companies in one response.
        Call("/api/v1/quote"),
        Call("/api/v1/index/master"),
        Call("/api/v1/index/market-price/daily-feed"),
        Call("/api/v1/index/price-returns"),
        Call("/api/v1/corporate-actions/all"),
        Call("/api/v1/results-calendar"),
        Call("/api/v1/ipo-calendar"),
        Call("/api/v1/holidays-calendar"),
        Call("/api/v1/corp-announcements"),
        Call("/api/v1/credit-ratings"),
        Call("/api/v1/investor-call-transcripts"),
        Call("/api/v1/investor-presentations"),
    ]

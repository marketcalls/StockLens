"""Preset public screens.

Every one of these parses and compiles against the current catalog; a test
asserts that, so a preset cannot rot when a column is renamed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    slug: str
    name: str
    description: str
    query: str
    columns: tuple[str, ...] = ()


PRESETS: tuple[Preset, ...] = (
    Preset(
        "low-pe-high-roce",
        "Low PE, high ROCE",
        "Profitable businesses trading on a modest multiple.",
        "Price to Earning < 20 AND Average return on capital employed 3Years > 20 "
        "AND Market Capitalization > 1000",
    ),
    Preset(
        "debt-free-compounders",
        "Debt-free compounders",
        "Growing sales and profit without leaning on borrowings.",
        "Debt to equity < 0.1 AND Sales growth 5Years > 15 AND Profit growth 5Years > 15",
        columns=("name", "market_cap", "pe", "revenuegrowth5years", "netincomegrowth5years"),
    ),
    Preset(
        "dividend-champions",
        "Dividend champions",
        "A meaningful yield backed by a sustained payout and decent returns.",
        "Dividend Yield > 3 AND Average dividend payout 3Years > 25 AND Return on equity > 15",
        columns=(
            "name",
            "market_cap",
            "dividend_yield",
            "dividendpayoutpct3yrsavg",
            "returnonequity",
        ),
    ),
    Preset(
        "quality-at-a-reasonable-price",
        "Quality at a reasonable price",
        "Consistent returns on equity without a demanding valuation.",
        "Average return on equity 5Years > 18 AND Price to Earning < 25 AND Debt to equity < 0.5",
    ),
    Preset(
        "cash-generators",
        "Cash generators",
        "Profit that arrives as cash, and free cash flow to show for it.",
        "CFO to PAT > 1 AND Free cash flow > 0 AND Average FCF to revenue 3Years > 8",
        columns=("name", "market_cap", "cfo_to_pat", "fcf", "fcfaspctofrevenue3yearsavg"),
    ),
    Preset(
        "negative-working-capital",
        "Negative working capital cycle",
        "Paid by customers before paying suppliers, while still growing.",
        "Cash conversion cycle < 0 AND Sales growth 3Years > 10",
        columns=("name", "market_cap", "cashconversioncycle", "debtordays", "revenuegrowth3years"),
    ),
    Preset(
        "near-52-week-low",
        "Near 52-week low, still profitable",
        "Well off their highs but still earning a return.",
        "Down from 52w high > 30 AND Return on equity > 12 AND Debt to equity < 1",
        columns=("name", "current_price", "down_from_52w_high", "pe", "returnonequity"),
    ),
    Preset(
        "promoter-pledge-risk",
        "Promoter pledge risk",
        "Promoters have pledged part of their holding. Worth understanding why.",
        "Promoter pledge > 10",
        columns=("name", "market_cap", "promoter_holding", "promoter_pledge", "totaldebttoequity"),
    ),
    Preset(
        "high-growth-small-caps",
        "Small cap growth",
        "Smaller companies growing sales quickly.",
        "Market Capitalization < 5000 AND Market Capitalization > 500 AND Sales growth 3Years > 20",
        columns=("name", "market_cap", "revenuegrowth3years", "returnonequity", "pe"),
    ),
    Preset(
        "turnaround",
        "Turnaround candidates",
        "Back in profit after a loss-making year.",
        "Net Profit > 0 AND Profit growth 3Years > 0 AND Return on equity > 0 "
        "AND Price to Earning < 30",
    ),
    Preset(
        "nifty-value",
        "Nifty 50 value",
        "The cheapest names in the Nifty 50 on a price-to-earnings basis.",
        'Index = "NIF50" AND Price to Earning < 20',
    ),
    Preset(
        "trading-below-book",
        "Trading below book value",
        "Priced under net asset value, with earnings to support it.",
        "Price to book value < 1 AND Return on equity > 8 AND Market Capitalization > 500",
        columns=("name", "market_cap", "pb", "book_value", "current_price", "returnonequity"),
    ),
)


PRESETS_BY_SLUG = {p.slug: p for p in PRESETS}

"""The screener column catalog.

Single source of truth for what can be screened on. Both the snapshot
materialisation and the query compiler read it, so a column cannot exist in one
and not the other.

Units follow the reference product so pasted queries behave as users expect:

- money in **Rs. Crore**
- percentages as **percent**, not fractions - `Return on equity > 15` means 15%
- ratios unitless

FinEdge does not use those units, so every column carries the conversion.
Verified against stored data on 2026-08-06:

    profitLossForPeriod  957540000000 raw -> 95,754 Cr   (matches the reference)
    eps                  59.69 raw -> 59.69              (per share, no scaling)
    returnOnEquity       0.0827 raw -> 8.27%             (fraction -> percent)
    currentRatio         1.1 raw -> 1.1                  (already unitless)
    market_cap (quote)   1793061.38 raw                  (already Rs Crore)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Unit = Literal["crore", "percent", "ratio", "price", "count", "days", "text"]
SourceKind = Literal["quote", "company", "statement", "basic", "ratio", "metric", "computed"]

# Absolute rupees -> Rs Crore.
RUPEES_TO_CRORE = 1e-7
# Fraction -> percent.
FRACTION_TO_PERCENT = 100.0

# Fields inside money-bearing responses that are NOT money and must not be
# divided. Getting this wrong turns an EPS of 59.69 into 0.000006.
PER_SHARE_FIELDS = frozenset(
    {
        "eps",
        "bookValuepershare",
        "tangibleBookValueperShare",
        "fcfPerShare",
        "salesPerShare",
        "adjustedFaceValue",
    }
)

# Fields returned as fractions that should read as percentages.
FRACTION_FIELDS = frozenset(
    {
        "tax",
        "dividendPayout",
        "retentionRatio",
        "cashFlowMargin",
    }
)

# Share and holder counts. Neither money nor ratio.
COUNT_FIELDS = frozenset(
    {
        "dilutedOutstandingShares",
        "sharesOutstanding",
        "dilutedSharesOutstanding",
        "adjustedEquityShareCapital",
        "totalShareholders",
    }
)

# Ratio families whose values arrive as fractions.
PERCENT_RATIO_FAMILIES = frozenset({"pr"})
PERCENT_METRIC_FAMILIES = frozenset({"gr", "av"})


@dataclass(frozen=True)
class Column:
    """One screenable column."""

    key: str  # SQL column name in company_snapshot
    label: str  # what the user types
    unit: Unit
    source: SourceKind
    # Where to read it from in Layer 2. Meaning depends on `source`:
    #   statement -> (statement_code, field_name)
    #   basic     -> (statement_code, field_name)
    #   ratio     -> (family, field_name)
    #   metric    -> (family, field_name)
    #   quote     -> (column_name,)
    #   company   -> (column_name,)
    #   computed  -> ()
    path: tuple[str, ...] = ()
    scale: float = 1.0
    aliases: tuple[str, ...] = ()
    description: str = ""
    # Alternative field names for other statement schemas, tried in order when
    # `path` yields nothing. A bank reports net profit as
    # `profitLossForThePeriod`, a life insurer as `profitLossAfterTax`. Without
    # these, every bank and insurer has a blank net profit and drops out of any
    # screen that mentions it.
    fallbacks: tuple[str, ...] = ()

    @property
    def sql_type(self) -> str:
        return "TEXT" if self.unit == "text" else "REAL"

    def match_names(self) -> tuple[str, ...]:
        return (self.label, self.key, *self.aliases)


def _money(field: str, code: str, label: str, source: SourceKind, **kw) -> Column:
    """A money column, scaled to Rs Crore unless the field is per-share or a count."""
    if field in PER_SHARE_FIELDS:
        unit, scale = "price", 1.0
    elif field in COUNT_FIELDS:
        unit, scale = "count", 1.0
    elif field in FRACTION_FIELDS:
        unit, scale = "percent", FRACTION_TO_PERCENT
    else:
        unit, scale = "crore", RUPEES_TO_CRORE
    return Column(
        key=kw.pop("key", f"{code}_{field.lower()}"),
        label=label,
        unit=unit,  # type: ignore[arg-type]
        source=source,
        path=(code, field),
        scale=scale,
        **kw,
    )


def _ratio(family: str, field: str, label: str, unit: Unit = "percent", **kw) -> Column:
    scale = FRACTION_TO_PERCENT if family in PERCENT_RATIO_FAMILIES and unit == "percent" else 1.0
    return Column(
        key=kw.pop("key", field.lower()),
        label=label,
        unit=unit,
        source="ratio",
        path=(family, field),
        scale=scale,
        **kw,
    )


def _metric(family: str, field: str, label: str, unit: Unit = "percent", **kw) -> Column:
    scale = FRACTION_TO_PERCENT if family in PERCENT_METRIC_FAMILIES and unit == "percent" else 1.0
    return Column(
        key=kw.pop("key", field.lower()),
        label=label,
        unit=unit,
        source="metric",
        path=(family, field),
        scale=scale,
        **kw,
    )


COLUMNS: tuple[Column, ...] = (
    # --- identity and classification -----------------------------------------
    Column("name", "Name", "text", "company", ("name",)),
    Column("macro_sector", "Macro sector", "text", "company", ("macro_sector",)),
    Column("industry", "Industry", "text", "company", ("industry",)),
    Column("sector", "Sector", "text", "company", ("sector",)),
    Column("sub_industry", "Sub industry", "text", "company", ("sub_industry",)),
    Column("schema_kind", "Statement schema", "text", "company", ("schema_kind",)),
    # --- price and market ----------------------------------------------------
    Column(
        "current_price",
        "Current price",
        "price",
        "quote",
        ("current_price",),
        aliases=("CMP", "Price"),
    ),
    Column(
        "market_cap",
        "Market Capitalization",
        "crore",
        "quote",
        ("market_cap",),
        aliases=("Market cap", "Mcap"),
    ),
    Column("volume", "Volume", "count", "quote", ("volume",)),
    Column("change_pct", "Day change", "percent", "quote", ("change_pct",)),
    Column("high52", "High price 52 weeks", "price", "quote", ("high52",), aliases=("52w high",)),
    Column("low52", "Low price 52 weeks", "price", "quote", ("low52",), aliases=("52w low",)),
    Column("shares_outstanding", "Shares outstanding", "count", "quote", ("shares",)),
    # --- valuation -----------------------------------------------------------
    Column("pe", "Price to Earning", "ratio", "computed", aliases=("PE", "P/E")),
    Column("pb", "Price to book value", "ratio", "computed", aliases=("PB", "P/B")),
    Column("ps", "Price to Sales", "ratio", "computed", aliases=("PS",)),
    Column("pfcf", "Price to free cash flow", "ratio", "computed", aliases=("PFCF",)),
    Column("ptb", "Price to tangible book", "ratio", "computed"),
    # --- profit and loss, latest annual --------------------------------------
    _money("income", "pl", "Total income", "statement", key="income"),
    _money(
        "revenueFromOperations",
        "pl",
        "Sales",
        "statement",
        key="sales",
        aliases=("Revenue", "Sales latest year"),
        fallbacks=(
            "income",  # bank and insurer total income
            "netPremiumIncome",  # life insurance
            "premiumEarned",  # general insurance
        ),
    ),
    _money(
        "profitLossForPeriod",
        "pl",
        "Net Profit",
        "statement",
        key="net_profit",
        aliases=("PAT", "Profit after tax"),
        fallbacks=(
            "profitLossForThePeriod",  # bank
            "profitLossAfterTax",  # general insurance
            "profitLossAfterTaxAndExtraordinaryItems",  # life insurance
            "profitOrLossAttributableToOwners",
        ),
    ),
    _money(
        "profitBeforeTax",
        "pl",
        "Profit before tax",
        "statement",
        key="pbt",
        fallbacks=("profitLossBeforeTax", "profitOrLossBeforeTax"),
    ),
    _money("eps", "pl", "EPS", "statement", key="eps", aliases=("Earnings per share",)),
    _money(
        "financeCosts",
        "pl",
        "Interest",
        "statement",
        key="interest",
        fallbacks=("interestExpended",),
    ),
    _money("depreciationAndAmortisation", "pl", "Depreciation", "statement", key="depreciation"),
    _money("otherIncome", "pl", "Other income", "statement", key="other_income"),
    _money(
        "taxExpense",
        "pl",
        "Tax",
        "statement",
        key="tax_expense",
        fallbacks=("provisionForTax", "provisionsForTaxes"),
    ),
    # --- derived aggregates --------------------------------------------------
    _money("ebitda", "pl", "EBITDA", "basic", key="ebitda"),
    _money("ebit", "pl", "EBIT", "basic", key="ebit"),
    _money("operatingProfit", "pl", "Operating profit", "basic", key="operating_profit"),
    _money("operatingRevenue", "pl", "Operating revenue", "basic", key="operating_revenue"),
    _money("dividendPayout", "pl", "Dividend Payout", "basic", key="dividend_payout"),
    _money("salesPerShare", "pl", "Sales per share", "basic", key="sales_per_share"),
    _money("bookValue", "bs", "Book value total", "basic", key="book_value_total"),
    _money(
        "bookValuepershare",
        "bs",
        "Book value",
        "basic",
        key="book_value",
        aliases=("Book value per share",),
    ),
    _money(
        "tangibleBookValueperShare", "bs", "Tangible book value", "basic", key="tangible_book_value"
    ),
    _money("totalAssets", "bs", "Total assets", "basic", key="total_assets"),
    _money("totalEquity", "bs", "Total equity", "basic", key="total_equity"),
    _money("totalDebt", "bs", "Total debt", "basic", key="total_debt", aliases=("Debt",)),
    _money("netDebt", "bs", "Net debt", "basic", key="net_debt"),
    _money("totalCash", "bs", "Cash", "basic", key="total_cash"),
    _money("totalReserves", "bs", "Reserves", "basic", key="reserves"),
    _money("workingCapital", "bs", "Working capital", "basic", key="working_capital"),
    _money("operatingCashFlow", "cf", "Cash from operations", "basic", key="cfo"),
    _money("investingCashFlow", "cf", "Cash from investing", "basic", key="cfi"),
    _money("financingCashFlow", "cf", "Cash from financing", "basic", key="cff"),
    _money("fcf", "cf", "Free cash flow", "basic", key="fcf"),
    _money("capex", "cf", "Capital expenditure", "basic", key="capex"),
    _money("fcfPerShare", "cf", "Free cash flow per share", "basic", key="fcf_per_share"),
    # --- profitability ratios ------------------------------------------------
    _ratio("pr", "returnOnEquity", "Return on equity", aliases=("ROE",)),
    _ratio("pr", "returnOnCapital", "Return on capital employed", aliases=("ROCE",)),
    _ratio("pr", "returnOnAsset", "Return on assets", aliases=("ROA",)),
    _ratio("pr", "returnOnTangibleAssets", "Return on tangible assets"),
    _ratio("pr", "grossMargin", "Gross margin"),
    _ratio("pr", "operatingMargin", "OPM", aliases=("Operating margin",)),
    _ratio("pr", "ebitdaMargin", "EBITDA margin"),
    _ratio("pr", "ebitMargin", "EBIT margin"),
    _ratio("pr", "netMargin", "Net profit margin", aliases=("NPM",)),
    _ratio("pr", "preTaxMargin", "Pre tax margin"),
    _ratio("pr", "effectiveTaxRate", "Tax rate"),
    # --- leverage ------------------------------------------------------------
    _ratio("le", "totalDebtToEquity", "Debt to equity", "ratio"),
    _ratio("le", "longTermDebtToEquity", "Long term debt to equity", "ratio"),
    _ratio("le", "totalDebttoAssets", "Debt to assets", "ratio"),
    _ratio("le", "financialLeverage", "Financial leverage", "ratio"),
    _ratio("le", "totalDebtTofcf", "Debt to free cash flow", "ratio"),
    # --- liquidity -----------------------------------------------------------
    _ratio("li", "currentRatio", "Current ratio", "ratio"),
    _ratio("li", "quickRatio", "Quick ratio", "ratio"),
    _ratio("li", "interestCoverage", "Interest Coverage Ratio", "ratio"),
    # --- efficiency ----------------------------------------------------------
    _ratio("ef", "assetTurnover", "Asset turnover", "ratio"),
    _ratio("ef", "inventoryTurnover", "Inventory turnover", "ratio"),
    _ratio("ef", "receivableTurnover", "Receivable turnover", "ratio"),
    _ratio("ef", "workingCapitalTurnover", "Working capital turnover", "ratio"),
    _ratio("ef", "debtorDays", "Debtor days", "days"),
    _ratio("ef", "inventoryDays", "Inventory days", "days"),
    _ratio("ef", "daysPayable", "Days payable", "days"),
    _ratio("ef", "cashConversionCycle", "Cash conversion cycle", "days"),
    _ratio("ef", "workingCapitalDays", "Working capital days", "days"),
    # --- growth --------------------------------------------------------------
    _metric("gr", "revenueGrowth3years", "Sales growth 3Years", aliases=("Sales growth 3Y",)),
    _metric("gr", "revenueGrowth5years", "Sales growth 5Years", aliases=("Sales growth 5Y",)),
    _metric("gr", "netIncomeGrowth3years", "Profit growth 3Years"),
    _metric("gr", "netIncomeGrowth5years", "Profit growth 5Years"),
    _metric("gr", "epsGrowth3years", "EPS growth 3Years"),
    _metric("gr", "epsGrowth5years", "EPS growth 5Years"),
    _metric("gr", "EBITDAGrowth3years", "EBITDA growth 3Years", key="ebitdagrowth3years"),
    _metric("gr", "EBITDAGrowth5years", "EBITDA growth 5Years", key="ebitdagrowth5years"),
    _metric("gr", "assetGrowth3years", "Asset growth 3Years"),
    _metric("gr", "bookValueGrowth3Years", "Book value growth 3Years"),
    _metric("gr", "cfoGrowth3years", "CFO growth 3Years"),
    # --- multi-year averages -------------------------------------------------
    _metric("av", "roe3yearsAvg", "Average return on equity 3Years", aliases=("ROE 3Y",)),
    _metric("av", "roe5yearsAvg", "Average return on equity 5Years", aliases=("ROE 5Y",)),
    _metric(
        "av", "roce3yearsAvg", "Average return on capital employed 3Years", aliases=("ROCE 3Y",)
    ),
    _metric("av", "roce5yearsAvg", "Average return on capital employed 5Years"),
    _metric("av", "roa3yearsAvg", "Average return on assets 3Years"),
    _metric("av", "netMarginPct3YrsAvg", "Average net margin 3Years"),
    _metric("av", "operatingMarginPct3YrsAvg", "Average operating margin 3Years"),
    _metric("av", "dividendPayoutPct3YrsAvg", "Average dividend payout 3Years"),
    _metric("av", "dividendPayoutPct5YrsAvg", "Average dividend payout 5Years"),
    _metric("av", "fcfAsPctOfRevenue3yearsAvg", "Average FCF to revenue 3Years"),
    # --- cumulative ----------------------------------------------------------
    Column(
        "operatingcashflow3yearstotal",
        "Cash from operations 3Years",
        "crore",
        "metric",
        ("cu", "operatingCashFlow3yearsTotal"),
        scale=RUPEES_TO_CRORE,
    ),
    Column(
        "freecashflow3yearstotal",
        "Free cash flow 3Years",
        "crore",
        "metric",
        ("cu", "freeCashFlow3yearsTotal"),
        scale=RUPEES_TO_CRORE,
    ),
    # --- StockLens computed --------------------------------------------------
    Column(
        "dividend_yield",
        "Dividend Yield",
        "percent",
        "computed",
        description="Trailing 12 month dividend over current price",
    ),
    Column(
        "enterprise_value",
        "Enterprise Value",
        "crore",
        "computed",
        aliases=("EV",),
        description="Market cap plus total debt less cash",
    ),
    Column("ev_ebitda", "EV to EBITDA", "ratio", "computed", aliases=("EV/EBITDA",)),
    Column("earnings_yield", "Earnings yield", "percent", "computed"),
    Column("price_cagr_1y", "Return over 1year", "percent", "computed"),
    Column("price_cagr_3y", "Return over 3years", "percent", "computed"),
    Column("price_cagr_5y", "Return over 5years", "percent", "computed"),
    Column("price_cagr_10y", "Return over 10years", "percent", "computed"),
    Column("down_from_52w_high", "Down from 52w high", "percent", "computed"),
    Column("up_from_52w_low", "Up from 52w low", "percent", "computed"),
    Column("dma_50", "DMA 50", "price", "computed"),
    Column("dma_200", "DMA 200", "price", "computed"),
    Column("price_to_dma200", "Price to DMA 200", "ratio", "computed"),
    Column("avg_traded_value_30d", "Average traded value 30days", "crore", "computed"),
    Column("promoter_holding", "Promoter holding", "percent", "computed"),
    Column(
        "promoter_pledge", "Pledged percentage", "percent", "computed", aliases=("Promoter pledge",)
    ),
    Column("public_holding", "Public holding", "percent", "computed"),
    Column(
        "cfo_to_pat",
        "CFO to PAT",
        "ratio",
        "computed",
        description="Cash from operations divided by net profit",
    ),
)


COLUMNS_BY_KEY: dict[str, Column] = {c.key: c for c in COLUMNS}


def _normalise(name: str) -> str:
    return " ".join(name.lower().replace("_", " ").split())


LOOKUP: dict[str, Column] = {}
for _column in COLUMNS:
    for _name in _column.match_names():
        LOOKUP[_normalise(_name)] = _column


def resolve(name: str) -> Column | None:
    """Find a column by label, key or alias. Case and spacing tolerant."""
    return LOOKUP.get(_normalise(name))


def screenable() -> tuple[Column, ...]:
    """Numeric columns only. Text columns are filters, not comparisons."""
    return tuple(c for c in COLUMNS if c.unit != "text")


def snapshot_ddl() -> str:
    """CREATE TABLE for company_snapshot, generated from the catalog.

    Generated rather than hand-written so a column can never exist in the
    catalog but not the table, or the other way round.
    """
    lines = [
        "symbol TEXT PRIMARY KEY",
        "updated_at TEXT NOT NULL",
    ]
    lines += [f"{c.key} {c.sql_type}" for c in COLUMNS]
    body = ",\n  ".join(lines)
    return f"CREATE TABLE IF NOT EXISTS company_snapshot (\n  {body}\n)"

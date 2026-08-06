"""Statement row templates, one set per schema family.

The reference product shows an ordinary company as Sales / Expenses / Operating
Profit / OPM% / ... A bank has none of those lines. It has interest earned,
interest expended, net interest income, gross NPA and capital adequacy. A life
insurer has premiums and actuarial liabilities.

So the row list is a property of the schema family, not of the renderer. One
component draws all four; this module tells it what to draw.

See app/ingest/schemas.py for how a company's family is determined.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RowKind = Literal["field", "derived", "spacer"]


@dataclass(frozen=True)
class Row:
    """One line of a statement table."""

    label: str
    kind: RowKind = "field"
    # Field names to try, in order. First one present wins.
    fields: tuple[str, ...] = ()
    unit: Literal["crore", "percent", "price", "ratio", "count", "fraction_pct"] = "crore"
    emphasis: bool = False
    # Fields to reveal when the row is expanded, mirroring the reference's "+".
    children: tuple[tuple[str, str], ...] = ()
    # For derived rows: how to compute from other row values.
    formula: str = ""


# --- ordinary companies -------------------------------------------------------

GENERAL_PL: tuple[Row, ...] = (
    Row(
        "Sales",
        fields=("operatingRevenue", "revenueFromOperations"),
        children=(
            ("Revenue from sale of product", "revenueFromSaleOfProduct"),
            ("Revenue from sale of services", "revenueFromSaleOfServices"),
            ("Other operating revenue", "otherRevenueFromOperations"),
        ),
    ),
    Row(
        "Expenses",
        fields=("operatingExpenses", "expenses"),
        children=(
            ("Cost of materials consumed", "costOfMaterialsConsumed"),
            ("Purchases of stock in trade", "purchasesOfStockInTrade"),
            ("Changes in inventories", "changesInInventories"),
            ("Employee benefit expense", "employeeBenefitExpense"),
            ("Other expenses", "otherExpenses"),
        ),
    ),
    Row("Operating Profit", fields=("operatingProfit", "ebit"), emphasis=True),
    Row("OPM %", kind="derived", unit="percent", formula="operating_margin"),
    Row(
        "Other Income",
        fields=("otherIncome",),
        children=(
            ("Dividend income", "dividendIncome"),
            ("Rental income", "rentalIncome"),
            ("Interest earned", "interestEarned"),
        ),
    ),
    Row("Interest", fields=("financeCosts",)),
    Row("Depreciation", fields=("depreciationAndAmortisation",)),
    Row("Profit before tax", fields=("profitBeforeTax",), emphasis=True),
    Row("Tax %", kind="derived", unit="percent", formula="tax_rate"),
    Row(
        "Net Profit",
        fields=("profitLossForPeriod",),
        emphasis=True,
        children=(
            ("Profit from discontinued operations", "profitLossFromDiscontinuedOperationsAfterTax"),
            ("Profit of associates", "profitOrLossOfAssociates"),
            ("Non-controlling interests", "nonControllingInterests"),
            ("Attributable to owners", "profitOrLossAttributableToOwners"),
        ),
    ),
    Row("EPS in Rs", fields=("eps",), unit="price"),
    Row("Dividend Payout %", fields=("dividendPayout",), unit="fraction_pct"),
)

GENERAL_BS: tuple[Row, ...] = (
    Row("Equity Capital", fields=("equityCapital", "shareCapital")),
    Row("Reserves", fields=("reserves", "totalReserves")),
    Row(
        "Borrowings",
        fields=("borrowingsNoncurrent",),
        children=(
            ("Long term borrowings", "borrowingsNoncurrent"),
            ("Short term borrowings", "borrowingsCurrent"),
        ),
    ),
    Row(
        "Other Liabilities",
        fields=("noncurrentLiabilities",),
        children=(
            ("Trade payables", "tradePayablesCurrent"),
            ("Current liabilities", "currentLiabilities"),
            ("Non-current liabilities", "noncurrentLiabilities"),
        ),
    ),
    Row("Total Liabilities", fields=("equityAndLiabilities", "liabilities"), emphasis=True),
    Row(
        "Fixed Assets",
        fields=("propertyPlantAndEquipment", "fixedAssets"),
        children=(
            ("Intangible assets", "intangibleAssets"),
            ("Right of use assets", "rightOfUseAssets"),
        ),
    ),
    Row("CWIP", fields=("capitalWorkInProgress",)),
    Row("Investments", fields=("noncurrentInvestments", "currentInvestments")),
    Row(
        "Other Assets",
        fields=("otherNoncurrentAssets", "otherCurrentAssets"),
        children=(
            ("Inventories", "inventories"),
            ("Trade receivables", "tradeReceivablesCurrent"),
            ("Cash and equivalents", "cashAndCashEquivalents"),
        ),
    ),
    Row("Total Assets", fields=("assets",), emphasis=True),
)

GENERAL_CF: tuple[Row, ...] = (
    Row("Cash from Operating Activity", fields=("cashFlowsFromOperatingActivities",)),
    Row("Cash from Investing Activity", fields=("cashFlowsFromInvestingActivities",)),
    Row("Cash from Financing Activity", fields=("cashFlowsFromFinancingActivities",)),
    Row("Net Cash Flow", fields=("netCashFlow",), emphasis=True),
    Row("Free Cash Flow", fields=("fcf",)),
)

# --- banks --------------------------------------------------------------------

BANK_PL: tuple[Row, ...] = (
    Row(
        "Revenue",
        fields=("interestEarned",),
        children=(
            ("Interest on advances / bills", "interestOrDiscountOnAdvancesOrBills"),
            ("Income on investments", "revenueOnInvestments"),
            ("Interest on balances with RBI", "interestOnBalancesWithRBIAndOthers"),
            ("Other interest", "otherInterest"),
        ),
    ),
    Row("Interest", fields=("interestExpended",)),
    Row(
        "Expenses",
        fields=("expenditureExcludingProvisions",),
        children=(
            ("Employee cost", "employeesCost"),
            ("Other operating expenses", "otherOperatingExpenses"),
        ),
    ),
    Row("Financing Profit", kind="derived", formula="net_interest_income", emphasis=True),
    Row("Financing Margin %", kind="derived", unit="percent", formula="nim"),
    Row("Other Income", fields=("otherIncome",)),
    Row("Provisions", fields=("provisionsForLoanLoss",)),
    Row("Profit before tax", fields=("profitLossBeforeTax",), emphasis=True),
    Row("Tax %", kind="derived", unit="percent", formula="tax_rate"),
    Row("Net Profit", fields=("profitLossForThePeriod",), emphasis=True),
    Row("EPS in Rs", fields=("eps",), unit="price"),
    Row("Gross NPA %", fields=("percentageOfGrossNpa",), unit="percent"),
    Row("Net NPA %", fields=("percentageOfNpa",), unit="percent"),
    Row("CET1 Ratio", fields=("cET1Ratio",), unit="percent"),
)

# --- life insurance -----------------------------------------------------------

LIFE_PL: tuple[Row, ...] = (
    Row(
        "Gross Premium Income",
        fields=("grossPremiumIncome",),
        children=(
            ("First year premium", "incomeFirstYearPremium"),
            ("Renewal premium", "incomeRenewalPremium"),
            ("Single premium", "incomeSinglePremium"),
        ),
    ),
    Row("Net Premium Income", fields=("netPremiumIncome",), emphasis=True),
    Row("Income from Investments", fields=("incomeFromInvestmentsNet",)),
    Row("Commission", fields=("netCommission", "commission")),
    Row("Benefits Paid", fields=("benefitsPaidNet",)),
    Row("Change in Actuarial Liability", fields=("changeInActuarialLiability",)),
    Row("Expenses of Management", fields=("expensesOfManagement",)),
    Row("Surplus / Deficit", fields=("surplusDeficit", "netSurplusDeficit"), emphasis=True),
    Row(
        "Profit before tax", fields=("profitLossBeforeTax", "profitOrLossBeforeTax"), emphasis=True
    ),
    Row(
        "Net Profit",
        fields=(
            "profitLossAfterTaxAndExtraordinaryItems",
            "profitLossAfterTaxBeforeExtraordinaryItems",
        ),
        emphasis=True,
    ),
    Row("EPS in Rs", fields=("eps",), unit="price"),
    Row("Solvency Ratio", fields=("solvencyRatio",), unit="ratio"),
    Row("Persistency Ratio", fields=("persistencyRatio",), unit="percent"),
)

# --- general insurance --------------------------------------------------------

GENERAL_INSURANCE_PL: tuple[Row, ...] = (
    Row("Gross Premiums Written", fields=("grossPremiumsWritten",)),
    Row("Net Premium Written", fields=("netPremiumWritten",)),
    Row("Premium Earned", fields=("premiumEarned",), emphasis=True),
    Row("Income from Investments", fields=("incomeFromInvestmentsNet",)),
    Row("Claims Incurred", fields=("incurredClaims", "claimsPaid")),
    Row("Commission", fields=("netCommission",)),
    Row(
        "Operating Expenses",
        fields=("operatingExpensesRelatedToInsuranceBusiness", "operatingExpenses"),
    ),
    Row("Underwriting Profit", fields=("underwritingProfitOrLoss",), emphasis=True),
    Row(
        "Profit before tax", fields=("profitLossBeforeTax", "profitOrLossBeforeTax"), emphasis=True
    ),
    Row("Net Profit", fields=("profitLossAfterTax",), emphasis=True),
    Row("EPS in Rs", fields=("eps",), unit="price"),
    Row("Incurred Claim Ratio", fields=("incurredClaimRatio",), unit="percent"),
    Row("Combined Ratio", fields=("combinedRatio",), unit="percent"),
    Row("Solvency Ratio", fields=("solvencyRatio",), unit="ratio"),
)

RATIOS_ROWS: tuple[Row, ...] = (
    Row("Debtor Days", fields=("debtorDays",), unit="ratio"),
    Row("Inventory Days", fields=("inventoryDays",), unit="ratio"),
    Row("Days Payable", fields=("daysPayable",), unit="ratio"),
    Row("Cash Conversion Cycle", fields=("cashConversionCycle",), unit="ratio", emphasis=True),
    Row("Working Capital Days", fields=("workingCapitalDays",), unit="ratio"),
)

TEMPLATES: dict[tuple[str, str], tuple[Row, ...]] = {
    ("general", "pl"): GENERAL_PL,
    ("general", "bs"): GENERAL_BS,
    ("general", "cf"): GENERAL_CF,
    ("bank", "pl"): BANK_PL,
    ("bank", "bs"): GENERAL_BS,
    ("bank", "cf"): GENERAL_CF,
    ("life_insurance", "pl"): LIFE_PL,
    ("life_insurance", "cf"): GENERAL_CF,
    ("general_insurance", "pl"): GENERAL_INSURANCE_PL,
    ("general_insurance", "cf"): GENERAL_CF,
}


def template_for(schema_kind: str | None, statement_code: str) -> tuple[Row, ...]:
    """Rows to render. Falls back to the general layout for an unknown family.

    An unknown family is better served by the ordinary-company layout than by an
    empty table: most of its lines will be present even if a few are blank.
    """
    key = (schema_kind or "general", statement_code)
    if key in TEMPLATES:
        return TEMPLATES[key]
    return TEMPLATES.get(("general", statement_code), ())


def derive(formula: str, values: dict[str, float | None]) -> float | None:
    """Compute a derived row from the raw figures of the same period."""
    get = values.get

    if formula == "operating_margin":
        profit = get("operatingProfit") or get("ebit")
        sales = get("revenueFromOperations")
        return profit / sales * 100 if profit is not None and sales else None

    if formula == "tax_rate":
        tax = get("taxExpense") or get("provisionForTax")
        pbt = get("profitBeforeTax") or get("profitLossBeforeTax")
        return tax / pbt * 100 if tax is not None and pbt else None

    if formula == "net_interest_income":
        earned, expended = get("interestEarned"), get("interestExpended")
        return earned - expended if earned is not None and expended is not None else None

    if formula == "nim":
        earned, expended = get("interestEarned"), get("interestExpended")
        if earned is None or expended is None or not earned:
            return None
        return (earned - expended) / earned * 100

    if formula == "net_cash_flow":
        parts = [
            get("cashFlowsFromOperatingActivities"),
            get("cashFlowsFromInvestingActivities"),
            get("cashFlowsFromFinancingActivities"),
        ]
        present = [p for p in parts if p is not None]
        return sum(present) if present else None

    return None


@dataclass
class RenderedRow:
    label: str
    unit: str
    emphasis: bool
    values: list[float | None] = field(default_factory=list)
    children: list[RenderedRow] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "unit": self.unit,
            "emphasis": self.emphasis,
            "values": self.values,
            "children": [c.as_dict() for c in self.children],
        }

    @property
    def has_data(self) -> bool:
        return any(v is not None for v in self.values)


CRORE = 1e-7


def render(
    rows: tuple[Row, ...],
    periods: list[dict],
    values_by_period: list[dict[str, float | None]],
) -> list[dict]:
    """Build the table body: one rendered row per template row.

    Rows with no data in any period are dropped rather than shown as a line of
    dashes - a company that reports no depreciation should not have an empty
    Depreciation row.
    """
    out: list[RenderedRow] = []
    for row in rows:
        rendered = RenderedRow(label=row.label, unit=row.unit, emphasis=row.emphasis)
        for period_values in values_by_period:
            rendered.values.append(_value_for(row, period_values))

        for child_label, child_field in row.children:
            child = RenderedRow(label=child_label, unit=row.unit, emphasis=False)
            for period_values in values_by_period:
                raw = period_values.get(child_field)
                child.values.append(_scale(raw, row.unit))
            if child.has_data:
                rendered.children.append(child)

        if rendered.has_data:
            out.append(rendered)

    return [r.as_dict() for r in out]


def _value_for(row: Row, values: dict[str, float | None]) -> float | None:
    if row.kind == "derived":
        raw = derive(row.formula, values)
        # Percent formulas already return percentages; money formulas return
        # raw rupees and still need converting.
        return (
            _scale(raw, row.unit)
            if row.unit == "crore"
            else (None if raw is None else round(raw, 2))
        )
    for name in row.fields:
        raw = values.get(name)
        if raw is not None:
            return _scale(raw, row.unit)
    return None


def _scale(raw: float | None, unit: str) -> float | None:
    if raw is None:
        return None
    if unit == "crore":
        return round(raw * CRORE, 2)
    if unit == "fraction_pct":
        # A fraction that must read as a percentage. dividendPayout arrives as
        # 0.0921 and belongs on the page as 9.21%.
        return round(raw * 100, 2)
    # Percent-valued statement fields (NPA ratios, CET1) already arrive as
    # percentages, unlike the ratio endpoints which send fractions.
    return round(raw, 2)

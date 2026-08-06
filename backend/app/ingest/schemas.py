"""Statement schema families and how a company is assigned to one.

Derived empirically with `app.ingest.discover` over 22 companies spanning large
caps, public and private banks, a small finance bank, NBFCs, an AMC, a broker,
an exchange, life insurers and a general insurer.

Findings that differ from the PRD's assumptions:

1. There are **four** families, not three: general, bank, life insurance and
   general insurance. Life and general insurers share only 14 of their 67 and 42
   fields, so treating "insurance" as one schema would be wrong.
2. **NBFCs, AMCs, brokers and exchanges use the general schema.** BAJFINANCE,
   CHOLAFIN, LICHSGFIN, HDFCAMC, ANGELONE and BSE all matched it exactly. This
   answers docs/prd/09-open-questions.md Q5.
3. Membership must be decided by **subset containment, not exact equality**.
   AUBANK returns 25 of the bank family's 26 fields - it has no subsidiaries, so
   no minority-interest line - and an exact-match rule would strand it in a
   family of one.

Six fields appear in every family and therefore carry no signal:
eps, income, period_start, period_end, result_date, year.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

GENERAL = "general"
BANK = "bank"
LIFE_INSURANCE = "life_insurance"
GENERAL_INSURANCE = "general_insurance"
UNKNOWN = "unknown"

# Present in every family, so excluded from the signature used to classify.
NON_DISCRIMINATING = frozenset(
    {"eps", "income", "period_start", "period_end", "result_date", "year"}
)

# Fields unique enough to identify a family on their own. Used as a fast path and
# as a tie-break when a company returns a sparse subset of several families.
MARKERS: dict[str, frozenset[str]] = {
    BANK: frozenset(
        {
            "interestExpended",
            "interestOrDiscountOnAdvancesOrBills",
            "interestOnBalancesWithRBIAndOthers",
            "provisionsForLoanLoss",
            "expenditureExcludingProvisions",
            "cET1Ratio",
            "grossNonPerformingAssets",
            "percentageOfGrossNpa",
        }
    ),
    LIFE_INSURANCE: frozenset(
        {
            "grossPremiumIncome",
            "netPremiumIncome",
            "incomeFirstYearPremium",
            "incomeRenewalPremium",
            "changeInActuarialLiability",
            "allocationOfBonusToPolicyholders",
            "transferOfFundsToPolicyholdersAccount",
            "persistencyRatio",
            "conservationRatio",
        }
    ),
    GENERAL_INSURANCE: frozenset(
        {
            "grossPremiumsWritten",
            "netPremiumWritten",
            "premiumEarned",
            "incurredClaims",
            "incurredClaimRatio",
            "combinedRatio",
            "underwritingProfitOrLoss",
            "netRetentionRatio",
            "premiumDeficiency",
        }
    ),
    GENERAL: frozenset(
        {
            "revenueFromOperations",
            "costofGoodsSold",
            "costOfMaterialsConsumed",
            "changesInInventories",
            "purchasesOfStockInTrade",
            "employeeBenefitExpense",
            "depreciationAndAmortisation",
            "financeCosts",
        }
    ),
}

# The full observed field set per family, from the discovery run.
FAMILY_FIELDS: dict[str, frozenset[str]] = {
    GENERAL: frozenset(
        {
            "changesInInventories",
            "costOfMaterialsConsumed",
            "costofGoodsSold",
            "currentTax",
            "deferredTax",
            "depreciationAndAmortisation",
            "dilutedOutstandingShares",
            "dividendIncome",
            "employeeBenefitExpense",
            "exceptionalItemsBeforeTax",
            "expenses",
            "extraordinaryItems",
            "feesAndCommission",
            "feesAndCommissionIncome",
            "financeCosts",
            "impairmentOnFinancialInstruments",
            "interestEarned",
            "netGainOnAmortisedDerecognition",
            "netGainOnFairValueChanges",
            "netLossOnAmortisedDerecognition",
            "netLossOnFairValueChanges",
            "nonControllingInterests",
            "otherComprehensiveIncomeNetOfTaxes",
            "otherExpenses",
            "otherIncome",
            "otherRevenueFromOperations",
            "profitBeforeTax",
            "profitLossForPeriod",
            "profitLossFromDiscontinuedOperationsAfterTax",
            "profitOrLossAttributableToOwners",
            "profitOrLossOfAssociates",
            "purchasesOfStockInTrade",
            "rentalIncome",
            "revenueFromOperations",
            "revenueFromSaleOfProduct",
            "revenueFromSaleOfServices",
            "taxExpense",
        }
    ),
    BANK: frozenset(
        {
            "additionalTier1Ratio",
            "cET1Ratio",
            "dilutedOutstandingShares",
            "employeesCost",
            "exceptionalItems",
            "expenditureExcludingProvisions",
            "extraordinaryItems",
            "grossNonPerformingAssets",
            "interestEarned",
            "interestExpended",
            "interestOnBalancesWithRBIAndOthers",
            "interestOrDiscountOnAdvancesOrBills",
            "nonPerformingAssets",
            "otherIncome",
            "otherInterest",
            "otherOperatingExpenses",
            "percentageOfGrossNpa",
            "percentageOfNpa",
            "profitLossBeforeTax",
            "profitLossForThePeriod",
            "profitLossOfAssociates",
            "profitLossOfMinorityInterest",
            "profitOrLossAttributableToOwners",
            "provisionsForLoanLoss",
            "revenueOnInvestments",
            "taxExpense",
        }
    ),
}


@dataclass(frozen=True)
class Classification:
    """Which family a company's statements belong to, and how sure we are."""

    kind: str
    confidence: float
    matched_markers: int
    reason: str

    @property
    def is_confident(self) -> bool:
        return self.confidence >= 0.5 and self.kind != UNKNOWN


def signature(fields: set[str] | frozenset[str]) -> frozenset[str]:
    """Discriminating fields only."""
    return frozenset(fields) - NON_DISCRIMINATING


def classify_fields(fields: set[str] | frozenset[str]) -> Classification:
    """Assign a P&L field set to a schema family.

    Scores each family by the share of its markers present. Containment rather
    than equality, so a company that omits lines it has no need for still lands
    in the right family.
    """
    sig = signature(fields)
    if not sig:
        return Classification(UNKNOWN, 0.0, 0, "no discriminating fields present")

    scores: dict[str, tuple[float, int]] = {}
    for kind, markers in MARKERS.items():
        hits = len(sig & markers)
        scores[kind] = (hits / len(markers), hits)

    best_kind, (best_score, best_hits) = max(scores.items(), key=lambda kv: (kv[1][0], kv[1][1]))
    if best_hits == 0:
        return Classification(UNKNOWN, 0.0, 0, "matched no family markers")

    ranked = sorted(scores.values(), key=lambda s: (-s[0], -s[1]))
    runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
    margin = best_score - runner_up

    return Classification(
        kind=best_kind,
        confidence=round(best_score, 3),
        matched_markers=best_hits,
        reason=(
            f"matched {best_hits}/{len(MARKERS[best_kind])} {best_kind} markers, "
            f"margin {margin:.2f} over next family"
        ),
    )


def classify_statement_rows(rows: list[dict[str, Any]]) -> Classification:
    """Classify from raw `financials` rows.

    Unions field names across periods: early years can omit lines that later
    ones carry, and classifying off a single period under-reports the signature.
    """
    fields: set[str] = set()
    for row in rows:
        fields.update(row.keys())
    return classify_fields(fields)


def unknown_fields(fields: set[str] | frozenset[str], kind: str) -> frozenset[str]:
    """Fields we have no mapping for, so a new FinEdge line does not vanish silently."""
    known = FAMILY_FIELDS.get(kind)
    if known is None:
        return frozenset()
    return signature(fields) - known

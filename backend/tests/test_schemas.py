"""Schema classification tests.

The field sets below are the real ones observed via `app.ingest.discover` on
2026-08-06, trimmed to the discriminating markers.
"""

from __future__ import annotations

from app.ingest.schemas import (
    BANK,
    GENERAL,
    GENERAL_INSURANCE,
    LIFE_INSURANCE,
    UNKNOWN,
    classify_fields,
    classify_statement_rows,
    signature,
    unknown_fields,
)

GENERAL_PL = {
    "income",
    "revenueFromOperations",
    "otherIncome",
    "expenses",
    "costofGoodsSold",
    "costOfMaterialsConsumed",
    "purchasesOfStockInTrade",
    "changesInInventories",
    "employeeBenefitExpense",
    "financeCosts",
    "depreciationAndAmortisation",
    "otherExpenses",
    "profitBeforeTax",
    "taxExpense",
    "profitLossForPeriod",
    "eps",
    "dilutedOutstandingShares",
    "period_start",
    "period_end",
    "result_date",
    "year",
}

BANK_PL = {
    "income",
    "interestEarned",
    "interestOrDiscountOnAdvancesOrBills",
    "revenueOnInvestments",
    "interestOnBalancesWithRBIAndOthers",
    "otherInterest",
    "otherIncome",
    "interestExpended",
    "employeesCost",
    "otherOperatingExpenses",
    "provisionsForLoanLoss",
    "expenditureExcludingProvisions",
    "grossNonPerformingAssets",
    "percentageOfGrossNpa",
    "cET1Ratio",
    "additionalTier1Ratio",
    "profitLossBeforeTax",
    "profitLossForThePeriod",
    "eps",
    "period_start",
    "period_end",
    "result_date",
    "year",
}

# AUBANK: the bank set minus profitOrLossAttributableToOwners. It has no
# subsidiaries, so no minority-interest line.
AUBANK_PL = BANK_PL - {"profitOrLossAttributableToOwners"}

LIFE_PL = {
    "income",
    "grossPremiumIncome",
    "netPremiumIncome",
    "incomeFirstYearPremium",
    "incomeRenewalPremium",
    "incomeSinglePremium",
    "changeInActuarialLiability",
    "allocationOfBonusToPolicyholders",
    "transferOfFundsToPolicyholdersAccount",
    "persistencyRatio",
    "conservationRatio",
    "solvencyRatio",
    "eps",
    "period_start",
    "period_end",
    "result_date",
    "year",
}

GENERAL_INSURANCE_PL = {
    "income",
    "grossPremiumsWritten",
    "netPremiumWritten",
    "premiumEarned",
    "incurredClaims",
    "incurredClaimRatio",
    "combinedRatio",
    "underwritingProfitOrLoss",
    "netRetentionRatio",
    "premiumDeficiency",
    "solvencyRatio",
    "eps",
    "period_start",
    "period_end",
    "result_date",
    "year",
}


class TestSignature:
    def test_strips_fields_common_to_every_family(self) -> None:
        sig = signature(GENERAL_PL)
        for shared in ("eps", "income", "period_start", "period_end", "result_date", "year"):
            assert shared not in sig

    def test_keeps_discriminating_fields(self) -> None:
        assert "revenueFromOperations" in signature(GENERAL_PL)


class TestClassify:
    def test_general(self) -> None:
        assert classify_fields(GENERAL_PL).kind == GENERAL

    def test_bank(self) -> None:
        assert classify_fields(BANK_PL).kind == BANK

    def test_life_insurance(self) -> None:
        assert classify_fields(LIFE_PL).kind == LIFE_INSURANCE

    def test_general_insurance(self) -> None:
        assert classify_fields(GENERAL_INSURANCE_PL).kind == GENERAL_INSURANCE

    def test_life_and_general_insurance_are_not_conflated(self) -> None:
        """They share only 14 of 67 and 42 fields; one 'insurance' kind would be wrong."""
        assert classify_fields(LIFE_PL).kind != classify_fields(GENERAL_INSURANCE_PL).kind

    def test_aubank_lands_with_the_banks(self) -> None:
        """Subset containment, not exact match. An equality rule strands it alone."""
        result = classify_fields(AUBANK_PL)
        assert result.kind == BANK
        assert result.is_confident

    def test_nbfc_uses_the_general_schema(self) -> None:
        """BAJFINANCE, CHOLAFIN and LICHSGFIN all matched general, not bank."""
        nbfc = GENERAL_PL | {"impairmentOnFinancialInstruments", "feesAndCommissionIncome"}
        assert classify_fields(nbfc).kind == GENERAL

    def test_an_nbfc_is_not_pulled_into_bank_by_interest_earned(self) -> None:
        """interestEarned appears in both families, so it must not decide alone."""
        nbfc = GENERAL_PL | {"interestEarned"}
        assert classify_fields(nbfc).kind == GENERAL

    def test_empty_input_is_unknown_not_a_guess(self) -> None:
        result = classify_fields(set())
        assert result.kind == UNKNOWN
        assert not result.is_confident

    def test_only_shared_fields_is_unknown(self) -> None:
        assert classify_fields({"eps", "income", "year"}).kind == UNKNOWN

    def test_unrecognised_fields_are_unknown(self) -> None:
        assert classify_fields({"someBrandNewLine", "anotherOne"}).kind == UNKNOWN

    def test_confidence_is_reported(self) -> None:
        result = classify_fields(BANK_PL)
        assert 0.0 < result.confidence <= 1.0
        assert result.matched_markers > 0
        assert "bank" in result.reason


class TestClassifyRows:
    def test_unions_fields_across_periods(self) -> None:
        """A field absent in the earliest year must still count."""
        rows = [
            {"income": 1, "revenueFromOperations": 1, "costofGoodsSold": 1},
            {"income": 1, "employeeBenefitExpense": 1, "depreciationAndAmortisation": 1},
            {"income": 1, "financeCosts": 1, "changesInInventories": 1},
        ]
        result = classify_statement_rows(rows)
        assert result.kind == GENERAL
        # Classifying off row 0 alone would match far fewer markers.
        assert result.matched_markers > classify_fields(set(rows[0])).matched_markers

    def test_no_rows_is_unknown(self) -> None:
        assert classify_statement_rows([]).kind == UNKNOWN


class TestUnknownFields:
    def test_flags_a_field_we_have_no_mapping_for(self) -> None:
        extended = GENERAL_PL | {"someNewFinEdgeLine"}
        assert "someNewFinEdgeLine" in unknown_fields(extended, GENERAL)

    def test_known_fields_are_not_flagged(self) -> None:
        assert "revenueFromOperations" not in unknown_fields(GENERAL_PL, GENERAL)

    def test_shared_fields_are_not_flagged(self) -> None:
        assert "eps" not in unknown_fields(GENERAL_PL, GENERAL)

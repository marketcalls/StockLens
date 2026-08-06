"""Statement row template tests.

Every bug fixed here was found by rendering real companies and comparing the
result to the reference product, not by a test failing.
"""

from __future__ import annotations

from app.api.presentation import (
    BANK_PL,
    GENERAL_PL,
    LIFE_PL,
    derive,
    render,
    template_for,
)


class TestTemplateSelection:
    def test_each_family_gets_its_own_profit_and_loss(self) -> None:
        general = {r.label for r in template_for("general", "pl")}
        bank = {r.label for r in template_for("bank", "pl")}
        life = {r.label for r in template_for("life_insurance", "pl")}

        assert "Sales" in general and "Sales" not in bank
        assert "Gross NPA %" in bank and "Gross NPA %" not in general
        assert "Gross Premium Income" in life and "Gross Premium Income" not in bank

    def test_general_and_general_insurance_are_different(self) -> None:
        general = {r.label for r in template_for("general", "pl")}
        insurance = {r.label for r in template_for("general_insurance", "pl")}
        assert "Combined Ratio" in insurance
        assert "Combined Ratio" not in general

    def test_an_unknown_family_falls_back_to_the_ordinary_layout(self) -> None:
        """An empty table serves nobody; most general rows will still populate."""
        assert template_for("unknown", "pl") == GENERAL_PL
        assert template_for(None, "pl") == GENERAL_PL

    def test_banks_share_the_general_balance_sheet(self) -> None:
        assert template_for("bank", "bs") == template_for("general", "bs")


class TestDerived:
    def test_operating_margin(self) -> None:
        value = derive(
            "operating_margin", {"operatingProfit": 150.0, "revenueFromOperations": 1000.0}
        )
        assert value == 15.0

    def test_operating_margin_is_none_without_sales(self) -> None:
        assert derive("operating_margin", {"operatingProfit": 150.0}) is None

    def test_operating_margin_does_not_divide_by_zero(self) -> None:
        assert (
            derive("operating_margin", {"operatingProfit": 1.0, "revenueFromOperations": 0}) is None
        )

    def test_tax_rate(self) -> None:
        assert derive("tax_rate", {"taxExpense": 25.0, "profitBeforeTax": 100.0}) == 25.0

    def test_tax_rate_uses_the_bank_field_names(self) -> None:
        value = derive("tax_rate", {"provisionForTax": 20.0, "profitLossBeforeTax": 100.0})
        assert value == 20.0

    def test_net_interest_income(self) -> None:
        value = derive("net_interest_income", {"interestEarned": 300.0, "interestExpended": 170.0})
        assert value == 130.0

    def test_net_interest_margin(self) -> None:
        value = derive("nim", {"interestEarned": 200.0, "interestExpended": 100.0})
        assert value == 50.0

    def test_unknown_formula_returns_none(self) -> None:
        assert derive("does_not_exist", {"anything": 1.0}) is None


class TestRender:
    PERIODS = [{"header": "Mar 2025"}, {"header": "Mar 2026"}]

    def test_money_is_converted_to_crore(self) -> None:
        rows = render(
            GENERAL_PL,
            self.PERIODS,
            [
                {"revenueFromOperations": 9.8e12, "profitLossForPeriod": 8.1e11},
                {"revenueFromOperations": 1.07e13, "profitLossForPeriod": 9.57e11},
            ],
        )
        sales = next(r for r in rows if r["label"] == "Sales")
        assert sales["values"] == [980000.0, 1070000.0]

    def test_a_derived_money_row_is_also_converted(self) -> None:
        """Net interest income came out as 1,295,104,700,000 instead of 129,510."""
        rows = render(
            BANK_PL,
            [{"header": "Mar 2026"}],
            [{"interestEarned": 3.486e12, "interestExpended": 1.855e12}],
        )
        financing = next(r for r in rows if r["label"] == "Financing Profit")
        assert financing["values"][0] < 1_000_000
        assert financing["values"][0] == round((3.486e12 - 1.855e12) * 1e-7, 2)

    def test_a_derived_percent_row_is_not_converted_twice(self) -> None:
        rows = render(
            GENERAL_PL,
            [{"header": "Mar 2026"}],
            [{"revenueFromOperations": 1000.0, "operatingProfit": 140.0}],
        )
        opm = next(r for r in rows if r["label"] == "OPM %")
        assert opm["values"][0] == 14.0

    def test_eps_is_not_converted(self) -> None:
        rows = render(GENERAL_PL, [{"header": "Mar 2026"}], [{"eps": 59.69}])
        eps = next(r for r in rows if r["label"] == "EPS in Rs")
        assert eps["values"][0] == 59.69

    def test_dividend_payout_fraction_becomes_a_percentage(self) -> None:
        rows = render(GENERAL_PL, [{"header": "Mar 2026"}], [{"dividendPayout": 0.0921}])
        payout = next(r for r in rows if r["label"] == "Dividend Payout %")
        assert payout["values"][0] == 9.21

    def test_sales_prefers_the_revenue_base_that_reconciles(self) -> None:
        """operatingRevenue - operatingExpenses = operatingProfit.

        Using revenueFromOperations for Sales left the table not adding up.
        """
        rows = render(
            GENERAL_PL,
            [{"header": "Mar 2026"}],
            [
                {
                    "operatingRevenue": 1.104637e13,
                    "revenueFromOperations": 1.075675e13,
                    "operatingExpenses": 9.54414e12,
                    "operatingProfit": 1.50223e12,
                }
            ],
        )
        sales = next(r for r in rows if r["label"] == "Sales")["values"][0]
        expenses = next(r for r in rows if r["label"] == "Expenses")["values"][0]
        profit = next(r for r in rows if r["label"] == "Operating Profit")["values"][0]
        assert round(sales - expenses, 0) == round(profit, 0)

    def test_rows_with_no_data_are_dropped(self) -> None:
        """A company reporting no depreciation should not show an empty row."""
        rows = render(GENERAL_PL, [{"header": "Mar 2026"}], [{"eps": 10.0}])
        assert {r["label"] for r in rows} == {"EPS in Rs"}

    def test_expandable_children_appear_when_populated(self) -> None:
        rows = render(
            GENERAL_PL,
            [{"header": "Mar 2026"}],
            [{"revenueFromOperations": 1e12, "revenueFromSaleOfProduct": 6e11}],
        )
        sales = next(r for r in rows if r["label"] == "Sales")
        assert [c["label"] for c in sales["children"]] == ["Revenue from sale of product"]

    def test_empty_children_are_not_shown(self) -> None:
        rows = render(GENERAL_PL, [{"header": "Mar 2026"}], [{"revenueFromOperations": 1e12}])
        sales = next(r for r in rows if r["label"] == "Sales")
        assert sales["children"] == []

    def test_a_missing_period_renders_as_none_not_zero(self) -> None:
        rows = render(
            GENERAL_PL,
            self.PERIODS,
            [{"eps": 10.0}, {}],
        )
        eps = next(r for r in rows if r["label"] == "EPS in Rs")
        assert eps["values"] == [10.0, None]

    def test_life_insurer_renders_its_own_lines(self) -> None:
        rows = render(
            LIFE_PL,
            [{"header": "Mar 2026"}],
            [{"grossPremiumIncome": 7.9e11, "netPremiumIncome": 7.7e11, "eps": 8.9}],
        )
        labels = [r["label"] for r in rows]
        assert "Gross Premium Income" in labels
        assert "Sales" not in labels

    def test_no_periods_produces_no_rows(self) -> None:
        assert render(GENERAL_PL, [], []) == []

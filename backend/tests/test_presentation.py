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
    def test_operating_expenses_excludes_the_lines_shown_separately(self) -> None:
        """Total expenses less interest and depreciation, which get their own rows."""
        value = derive(
            "operating_expenses",
            {"expenses": 1000.0, "financeCosts": 50.0, "depreciationAndAmortisation": 100.0},
        )
        assert value == 850.0

    def test_operating_profit_is_sales_minus_operating_expenses(self) -> None:
        value = derive(
            "operating_profit",
            {
                "revenueFromOperations": 1000.0,
                "expenses": 900.0,
                "financeCosts": 20.0,
                "depreciationAndAmortisation": 30.0,
            },
        )
        assert value == 150.0

    def test_operating_margin(self) -> None:
        value = derive(
            "operating_margin",
            {
                "revenueFromOperations": 1000.0,
                "expenses": 900.0,
                "financeCosts": 20.0,
                "depreciationAndAmortisation": 30.0,
            },
        )
        assert value == 15.0

    def test_operating_margin_is_none_without_sales(self) -> None:
        assert derive("operating_margin", {"expenses": 100.0}) is None

    def test_operating_margin_does_not_divide_by_zero(self) -> None:
        assert derive("operating_margin", {"revenueFromOperations": 0, "expenses": 1.0}) is None

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
            [{"revenueFromOperations": 1000.0, "expenses": 860.0}],
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

    def test_the_table_reconciles_by_construction(self) -> None:
        """Sales - Expenses = Operating Profit, for every period kind.

        These three are all derived from the statement now. They used to come
        from basic_financial, which holds annual aggregates keyed by a header
        like "Mar 2023" - a string that also names a quarter, so quarterly
        columns were silently showing annual figures.
        """
        rows = render(
            GENERAL_PL,
            [{"header": "Mar 2026"}],
            [
                {
                    "revenueFromOperations": 1.075675e13,
                    "expenses": 9.81475e12,
                    "financeCosts": 2.7061e11,
                    "depreciationAndAmortisation": 5.7688e11,
                }
            ],
        )
        sales = next(r for r in rows if r["label"] == "Sales")["values"][0]
        expenses = next(r for r in rows if r["label"] == "Expenses")["values"][0]
        profit = next(r for r in rows if r["label"] == "Operating Profit")["values"][0]
        assert round(sales - expenses, 0) == round(profit, 0)

    def test_quarterly_sales_stay_quarterly(self) -> None:
        """A quarter is roughly a quarter of a year, not a whole one."""
        rows = render(
            GENERAL_PL,
            [{"header": "Mar 2023"}],
            [{"revenueFromOperations": 2.3286e12, "expenses": 2.1592e12}],
        )
        sales = next(r for r in rows if r["label"] == "Sales")["values"][0]
        assert 200_000 < sales < 300_000

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


class TestAllZeroRows:
    def test_a_row_that_is_zero_in_every_period_is_dropped(self) -> None:
        """A bank showing 0% gross NPA across every quarter has not reported it.

        FinEdge returns 0 for fields it has no value for, so an all-zero row is
        absence rather than an achievement.
        """
        rows = render(
            BANK_PL,
            [{"header": "Mar 2025"}, {"header": "Mar 2026"}],
            [
                {"percentageOfGrossNpa": 0, "eps": 46.3},
                {"percentageOfGrossNpa": 0, "eps": 49.4},
            ],
        )
        labels = [r["label"] for r in rows]
        assert "Gross NPA %" not in labels
        assert "EPS in Rs" in labels

    def test_a_row_with_one_real_figure_is_kept(self) -> None:
        # 0.012, not 1.2: FinEdge sends percentage-valued statement fields as
        # fractions. This fixture used to carry 1.2, a value the feed never
        # sends, which is how the scaling bug survived - the test agreed with
        # the code and both disagreed with the data.
        rows = render(
            BANK_PL,
            [{"header": "Mar 2025"}, {"header": "Mar 2026"}],
            [{"percentageOfGrossNpa": 0}, {"percentageOfGrossNpa": 0.012}],
        )
        npa = next(r for r in rows if r["label"] == "Gross NPA %")
        assert npa["values"] == [0.0, 1.2]

    def test_a_genuine_negative_row_is_kept(self) -> None:
        rows = render(
            GENERAL_PL,
            [{"header": "Mar 2026"}],
            [{"profitLossForPeriod": -1.141e10}],
        )
        assert any(r["label"] == "Net Profit" for r in rows)


class TestPercentageFieldsAreFractions:
    """Every percentage-valued statement field arrives as a fraction.

    The code used to assert the opposite in a comment - "NPA ratios, CET1
    already arrive as percentages" - and rendered Axis Bank's 1.28% gross NPA,
    0.39% net NPA and 14.7% CET1 all as "0%". The sparklines still moved,
    because the underlying numbers were fine; only the scaling was wrong, so
    nothing looked broken enough to notice.
    """

    def _row(self, template_rows, label):
        return next(r for r in template_rows if r.label == label)

    def test_a_banks_percentage_rows_are_scaled(self) -> None:
        from app.api.presentation import BANK_PL

        for label in ("Gross NPA %", "Net NPA %", "CET1 Ratio"):
            assert self._row(BANK_PL, label).unit == "fraction_pct", label

    def test_an_insurers_percentage_rows_are_scaled(self) -> None:
        from app.api.presentation import GENERAL_INSURANCE_PL, LIFE_PL

        assert self._row(LIFE_PL, "Persistency Ratio").unit == "fraction_pct"
        for label in ("Incurred Claim Ratio", "Combined Ratio"):
            assert self._row(GENERAL_INSURANCE_PL, label).unit == "fraction_pct"

    def test_the_real_axis_bank_figures_render_correctly(self) -> None:
        from app.api.presentation import _scale

        # Values taken from the stored statement lines for AXISBANK, Mar 2026.
        assert _scale(0.0123, "fraction_pct") == 1.23  # gross NPA
        assert _scale(0.0037, "fraction_pct") == 0.37  # net NPA
        assert _scale(0.1445, "fraction_pct") == 14.45  # CET1

    def test_an_insurer_can_exceed_a_hundred_percent(self) -> None:
        from app.api.presentation import _scale

        # ICICI Lombard's combined ratio above 100% means an underwriting loss.
        # It must not be clamped or mistaken for a fraction of something.
        assert _scale(1.072, "fraction_pct") == 107.2

    def test_computed_percentages_are_left_alone(self) -> None:
        from app.api.presentation import _scale

        # Operating margin, tax rate and net interest margin are worked out here
        # and are already percentages. Scaling them again would give 4500%.
        assert _scale(45.0, "percent") == 45.0

    def test_no_statement_field_uses_the_computed_percent_unit(self) -> None:
        """The distinction that was got wrong, guarded at the source.

        `percent` means "we computed this". Any row that reads a field from the
        statement and calls itself `percent` is the original bug returning.
        """
        from app.api.presentation import TEMPLATES

        for template in TEMPLATES.values():
            for row in template:
                if row.unit == "percent":
                    assert row.kind == "derived", (
                        f"{row.label!r} reads {row.fields} from the statement but is marked"
                        " `percent`; statement percentages arrive as fractions"
                    )


class TestSolvencyRatio:
    """Two conventions for the same quantity, not consistent per company.

    HDFC Life and ICICI Prudential send 1.85 and 2.27 - the "times" convention.
    LIC and ICICI Lombard send 0.0235 and 0.0267 for the same thing, and SBI
    Life sends both across its own series. Rendered as stored, LIC's solvency of
    2.35 shows as "0.02", which reads as an insurer on the brink.
    """

    def test_the_times_convention_is_left_alone(self) -> None:
        from app.api.presentation import _scale

        for value in (1.75, 1.85, 1.94, 1.96, 2.273):
            assert _scale(value, "solvency") == round(value, 2)

    def test_the_hundredths_convention_is_rescaled(self) -> None:
        from app.api.presentation import _scale

        # Real stored values, and the figures the insurers actually report.
        assert _scale(0.0235, "solvency") == 2.35  # LIC
        assert _scale(0.0211, "solvency") == 2.11  # LIC, earlier period
        assert _scale(0.0267, "solvency") == 2.67  # ICICI Lombard
        assert _scale(0.019, "solvency") == 1.9  # SBI Life

    def test_both_conventions_in_one_series_land_together(self) -> None:
        from app.api.presentation import _scale

        # SBI Life sends 0.019 and 1.96 for adjacent periods. Rendered, they
        # must sit on the same scale or the row is a cliff.
        assert abs(_scale(0.019, "solvency") - _scale(1.96, "solvency")) < 0.1

    def test_everything_lands_above_the_regulatory_floor(self) -> None:
        from app.api.presentation import SOLVENCY_FLOOR, _scale

        # IRDAI requires 1.5. A rescaling that produced a figure below it would
        # be evidence the rule is wrong, not that the insurer is insolvent.
        stored = [1.75, 1.85, 1.94, 1.918, 2.273, 0.0211, 0.0235, 0.0267, 0.019, 1.96]
        assert all(_scale(v, "solvency") >= SOLVENCY_FLOOR for v in stored)

    def test_a_genuinely_distressed_insurer_is_not_inflated(self) -> None:
        # 0.8 is below the floor but nowhere near the hundredths form, so it is
        # reported as it stands rather than turned into a healthy 80.
        from app.api.presentation import _scale

        assert _scale(0.8, "solvency") == 0.8

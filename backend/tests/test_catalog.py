"""Column catalog tests.

The scaling rules are the risky part: getting one wrong silently produces a
number that is off by a factor of ten million and still looks plausible.
"""

from __future__ import annotations

from app.screener.catalog import (
    COLUMNS,
    COLUMNS_BY_KEY,
    FRACTION_TO_PERCENT,
    RUPEES_TO_CRORE,
    resolve,
    screenable,
    snapshot_ddl,
)


class TestLookup:
    def test_resolves_by_label(self) -> None:
        assert resolve("Return on equity").key == "returnonequity"

    def test_resolves_by_alias(self) -> None:
        assert resolve("ROE").key == "returnonequity"
        assert resolve("CMP").key == "current_price"
        assert resolve("Market cap").key == "market_cap"

    def test_resolves_by_key(self) -> None:
        assert resolve("net_profit").key == "net_profit"

    def test_is_case_insensitive(self) -> None:
        assert resolve("RETURN ON EQUITY") is resolve("return on equity")

    def test_treats_underscores_as_spaces(self) -> None:
        assert resolve("market_cap") is resolve("market cap")

    def test_unknown_name_returns_none_rather_than_guessing(self) -> None:
        assert resolve("Sharpe ratio") is None

    def test_every_key_is_unique(self) -> None:
        keys = [c.key for c in COLUMNS]
        assert len(keys) == len(set(keys))

    def test_no_alias_collides_with_another_columns_name(self) -> None:
        seen: dict[str, str] = {}
        for column in COLUMNS:
            for name in column.match_names():
                normalised = " ".join(name.lower().replace("_", " ").split())
                assert normalised not in seen or seen[normalised] == column.key, (
                    f"'{name}' maps to both {seen.get(normalised)} and {column.key}"
                )
                seen[normalised] = column.key


class TestScaling:
    def test_money_from_statements_converts_rupees_to_crore(self) -> None:
        """957,540,000,000 raw is 95,754 crore, which matches the reference."""
        column = COLUMNS_BY_KEY["net_profit"]
        assert column.scale == RUPEES_TO_CRORE
        assert 957540000000 * column.scale == 95754.0

    def test_eps_is_not_scaled(self) -> None:
        """Dividing a per-share figure would turn 59.69 into 0.000006."""
        assert COLUMNS_BY_KEY["eps"].scale == 1.0
        assert COLUMNS_BY_KEY["eps"].unit == "price"

    def test_book_value_per_share_is_not_scaled(self) -> None:
        assert COLUMNS_BY_KEY["book_value"].scale == 1.0

    def test_profitability_ratios_become_percentages(self) -> None:
        """FinEdge returns 0.0827; a user typing `ROE > 15` means 15%."""
        column = COLUMNS_BY_KEY["returnonequity"]
        assert column.scale == FRACTION_TO_PERCENT
        assert round(0.0827 * column.scale, 2) == 8.27

    def test_leverage_ratios_are_not_scaled(self) -> None:
        """Debt to equity of 0.41 is 0.41, not 41."""
        assert COLUMNS_BY_KEY["totaldebttoequity"].scale == 1.0

    def test_liquidity_ratios_are_not_scaled(self) -> None:
        assert COLUMNS_BY_KEY["currentratio"].scale == 1.0
        assert COLUMNS_BY_KEY["interestcoverage"].scale == 1.0

    def test_day_counts_are_not_scaled(self) -> None:
        assert COLUMNS_BY_KEY["debtordays"].scale == 1.0
        assert COLUMNS_BY_KEY["debtordays"].unit == "days"

    def test_growth_metrics_become_percentages(self) -> None:
        assert COLUMNS_BY_KEY["revenuegrowth5years"].scale == FRACTION_TO_PERCENT

    def test_average_metrics_become_percentages(self) -> None:
        assert COLUMNS_BY_KEY["roe3yearsavg"].scale == FRACTION_TO_PERCENT

    def test_cumulative_cash_metrics_convert_to_crore(self) -> None:
        assert COLUMNS_BY_KEY["freecashflow3yearstotal"].scale == RUPEES_TO_CRORE

    def test_market_cap_from_quotes_is_already_in_crore(self) -> None:
        assert COLUMNS_BY_KEY["market_cap"].scale == 1.0

    def test_share_counts_are_not_scaled(self) -> None:
        assert COLUMNS_BY_KEY["shares_outstanding"].scale == 1.0


class TestSchemaFallbacks:
    def test_net_profit_covers_bank_and_insurance_field_names(self) -> None:
        """Without these, every bank and insurer screens as having no profit."""
        fallbacks = COLUMNS_BY_KEY["net_profit"].fallbacks
        assert "profitLossForThePeriod" in fallbacks  # bank
        assert "profitLossAfterTax" in fallbacks  # general insurance
        assert "profitLossAfterTaxAndExtraordinaryItems" in fallbacks  # life

    def test_sales_falls_back_to_total_income_for_lenders(self) -> None:
        assert "income" in COLUMNS_BY_KEY["sales"].fallbacks

    def test_interest_falls_back_to_interest_expended_for_banks(self) -> None:
        assert "interestExpended" in COLUMNS_BY_KEY["interest"].fallbacks

    def test_general_schema_columns_keep_their_primary_field_first(self) -> None:
        assert COLUMNS_BY_KEY["net_profit"].path == ("pl", "profitLossForPeriod")


class TestSnapshotDdl:
    def test_includes_every_catalog_column(self) -> None:
        ddl = snapshot_ddl()
        for column in COLUMNS:
            assert f"{column.key} " in ddl

    def test_has_a_primary_key_and_a_timestamp(self) -> None:
        ddl = snapshot_ddl()
        assert "symbol TEXT PRIMARY KEY" in ddl
        assert "updated_at TEXT NOT NULL" in ddl

    def test_text_columns_are_text_and_numbers_are_real(self) -> None:
        ddl = snapshot_ddl()
        assert "sector TEXT" in ddl
        assert "market_cap REAL" in ddl


class TestScreenable:
    def test_excludes_text_columns(self) -> None:
        keys = {c.key for c in screenable()}
        assert "sector" not in keys
        assert "market_cap" in keys

    def test_there_are_enough_columns_to_be_useful(self) -> None:
        assert len(screenable()) > 100

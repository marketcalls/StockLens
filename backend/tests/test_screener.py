"""Screener parser, compiler and execution tests.

The security tests are the important ones: a column identifier must never come
from user text.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from app.db.engine import build_engine
from app.db.layer2 import create_layer2
from app.ingest import layer2_store as l2
from app.ingest.materialise import materialise
from app.screener.compiler import compile_query
from app.screener.execute import PUBLIC_ROW_CAP, normalise_query, query_hash, run_screen
from app.screener.parser import (
    CompareNode,
    InNode,
    LogicalNode,
    NotNode,
    QueryError,
    columns_used,
    parse,
)
from app.screener.presets import PRESETS

NOW = "2026-08-06T15:00:00+00:00"


def sql_for(query: str) -> tuple[str, dict]:
    compiled = compile_query(parse(query))
    return compiled.where, compiled.params


class TestParsing:
    def test_a_simple_comparison(self) -> None:
        node = parse("Market Capitalization > 500")
        assert isinstance(node, CompareNode)
        assert node.op == ">"

    def test_multi_word_column_names(self) -> None:
        """The tokeniser cannot split on whitespace: names contain spaces."""
        assert columns_used(parse("Return on equity > 15")) == {"returnonequity"}

    def test_the_longest_matching_column_wins(self) -> None:
        """'Average return on equity 3Years' must not stop at a shorter match."""
        assert columns_used(parse("Average return on equity 3Years > 15")) == {"roe3yearsavg"}

    def test_aliases_resolve(self) -> None:
        assert columns_used(parse("ROE > 15")) == {"returnonequity"}
        assert columns_used(parse("PE < 20")) == {"pe"}

    def test_and_binds_tighter_than_or(self) -> None:
        node = parse("PE < 10 OR PE < 20 AND ROE > 15")
        assert isinstance(node, LogicalNode)
        assert node.op == "OR"

    def test_brackets_override_precedence(self) -> None:
        node = parse("(PE < 10 OR PE < 20) AND ROE > 15")
        assert isinstance(node, LogicalNode)
        assert node.op == "AND"

    def test_not(self) -> None:
        assert isinstance(parse("NOT (Promoter pledge > 0)"), NotNode)

    def test_column_to_column_comparison(self) -> None:
        assert columns_used(parse("Current price < Book value")) == {"current_price", "book_value"}

    def test_arithmetic(self) -> None:
        where, _ = sql_for("Market Capitalization / Sales < 3")
        assert "/" in where

    def test_in_with_strings(self) -> None:
        node = parse('Sector IN ("Banks", "Finance")')
        assert isinstance(node, InNode)
        assert node.values == ("Banks", "Finance")

    def test_equality_on_a_text_column(self) -> None:
        node = parse('Index = "NIF50"')
        assert isinstance(node, InNode)

    def test_case_insensitive_keywords(self) -> None:
        assert parse("pe < 20 and roe > 15") is not None

    def test_decimal_numbers(self) -> None:
        _where, params = sql_for("Debt to equity < 0.5")
        assert 0.5 in params.values()

    def test_negative_numbers(self) -> None:
        assert parse("Cash conversion cycle < -10") is not None


class TestParseErrors:
    def test_empty_query(self) -> None:
        with pytest.raises(QueryError, match="empty"):
            parse("")

    def test_unknown_column(self) -> None:
        with pytest.raises(QueryError, match="Unknown column"):
            parse("Sharpe ratio > 1")

    def test_missing_comparison(self) -> None:
        with pytest.raises(QueryError):
            parse("Market Capitalization 500")

    def test_unbalanced_bracket(self) -> None:
        with pytest.raises(QueryError):
            parse("(PE < 20")

    def test_trailing_operator(self) -> None:
        with pytest.raises(QueryError):
            parse("PE <")

    def test_an_absurdly_complex_query_is_refused(self) -> None:
        with pytest.raises(QueryError, match="too complex"):
            parse(" AND ".join(["PE < 20"] * 200))

    def test_error_carries_a_position(self) -> None:
        with pytest.raises(QueryError) as exc:
            parse("PE < 20 AND Nonsense > 1")
        assert exc.value.position is not None


class TestSecurity:
    """No user text may reach SQL as an identifier."""

    def test_injection_in_a_column_position_is_rejected(self) -> None:
        with pytest.raises(QueryError):
            parse("market_cap; DROP TABLE company_snapshot; -- > 1")

    def test_injection_inside_a_string_becomes_a_bound_parameter(self) -> None:
        where, params = sql_for('Sector IN ("\'; DROP TABLE company_snapshot; --")')
        assert "DROP" not in where
        assert "'; DROP TABLE company_snapshot; --" in params.values()

    def test_every_literal_is_bound_not_inlined(self) -> None:
        where, params = sql_for("Market Capitalization > 12345")
        assert "12345" not in where
        assert 12345.0 in params.values()

    def test_only_catalog_keys_appear_as_identifiers(self) -> None:
        from app.screener.catalog import COLUMNS_BY_KEY

        where, _ = sql_for("Market Capitalization > 1 AND Return on equity > 2")
        identifiers = {
            w for w in where.replace("(", " ").replace(")", " ").split() if w.isidentifier()
        }
        for identifier in identifiers:
            assert identifier in COLUMNS_BY_KEY or identifier in {"AND", "OR", "NOT", "COALESCE"}

    def test_a_comment_sequence_is_not_a_column(self) -> None:
        with pytest.raises(QueryError):
            parse("-- > 1")


class TestNullHandling:
    """An unknown value matches nothing, whichever way the test is written.

    NOT used to compile to `NOT COALESCE(inner, 0)`, so that
    `NOT (pledge > 0)` would include companies reporting no pledge. That reads
    well until you notice what it does to a column that is merely undownloaded:
    `NOT (Price to Earning > 20)` returned 5,180 companies when only 54 are
    known to trade under 20 times earnings, because five thousand companies with
    no P/E counted as having a P/E of zero.

    Missing is not zero - the rule that has held everywhere else in this
    codebase - and NOT was the one operator that broke it.
    """

    def test_not_excludes_unknowns_like_every_other_operator(self) -> None:
        where, _ = sql_for("NOT (Promoter pledge > 0)")
        assert "COALESCE" not in where

    def test_not_agrees_with_the_comparison_it_negates(self, db: Engine) -> None:
        """`NOT (x > n)` and `x <= n` must return the same companies."""
        negated = run_screen(db, "NOT (Price to Earning > 20)")
        direct = run_screen(db, "Price to Earning <= 20")
        assert {r["symbol"] for r in negated.rows} == {r["symbol"] for r in direct.rows}
        assert negated.total == direct.total

    def test_a_company_with_no_value_matches_neither_side(self, db: Engine) -> None:
        above = {r["symbol"] for r in run_screen(db, "Price to Earning > 20").rows}
        below = {r["symbol"] for r in run_screen(db, "NOT (Price to Earning > 20)").rows}
        assert not (above & below), "a company cannot be on both sides of the same test"

    def test_unknowns_are_not_swept_into_the_negation(self, db: Engine) -> None:
        """The bug in one line: NOT must not return the whole universe."""
        from app.screener.catalog import COLUMNS_BY_KEY  # noqa: F401

        everyone = run_screen(db, "Market Capitalization > 0").total
        negated = run_screen(db, "NOT (Price to Earning > 20)").total
        assert negated < everyone

    def test_a_plain_comparison_excludes_unknowns(self) -> None:
        """A company with no reported ROE must not match `ROE > 15`."""
        where, _ = sql_for("Return on equity > 15")
        assert "COALESCE" not in where

    def test_division_guards_against_zero(self) -> None:
        where, _ = sql_for("Market Capitalization / Sales < 3")
        assert "NULLIF" in where


@pytest.fixture
def db(tmp_path: Path) -> Engine:
    engine = build_engine(tmp_path / "screen.db")
    create_layer2(engine)
    l2.upsert_companies(
        engine,
        [
            {"symbol": f"CO{i:03d}", "name": f"Company {i}", "sector": "Widgets", "updated_at": NOW}
            for i in range(60)
        ],
    )
    l2.upsert_quotes(
        engine,
        [
            {
                "symbol": f"CO{i:03d}",
                "market_cap": float(1000 + i * 10),
                "current_price": float(100 + i),
                "updated_at": NOW,
            }
            for i in range(60)
        ],
    )
    materialise(engine)
    # Give half of them a P/E so NULL handling is exercised.
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE company_snapshot SET pe = 10.0 WHERE CAST(SUBSTR(symbol, 3) AS INT) < 30")
        )
        conn.execute(
            text(
                "UPDATE company_snapshot SET returnonequity = 20.0 "
                "WHERE CAST(SUBSTR(symbol, 3) AS INT) < 10"
            )
        )
    return engine


class TestExecution:
    def test_runs_and_returns_matching_rows(self, db: Engine) -> None:
        result = run_screen(db, "Price to Earning < 20")
        assert result.total == 30
        assert all(r["symbol"].startswith("CO") for r in result.rows)

    def test_companies_without_the_column_are_excluded(self, db: Engine) -> None:
        """30 of the 60 have no P/E and must not match a P/E filter."""
        assert run_screen(db, "Price to Earning < 20").total == 30

    def test_and_narrows(self, db: Engine) -> None:
        result = run_screen(db, "Price to Earning < 20 AND Return on equity > 15")
        assert result.total == 10

    def test_sorted_by_market_cap_descending_by_default(self, db: Engine) -> None:
        rows = run_screen(db, "Price to Earning < 20").rows
        caps = [r["market_cap"] for r in rows]
        assert caps == sorted(caps, reverse=True)

    def test_public_cap_limits_rows_but_discloses_the_true_total(self, db: Engine) -> None:
        result = run_screen(db, "Price to Earning < 20", row_cap=PUBLIC_ROW_CAP)
        assert result.total == 30
        assert result.returned == PUBLIC_ROW_CAP
        assert result.capped is True

    def test_the_cap_cannot_be_escaped_by_asking_for_a_later_page(self, db: Engine) -> None:
        """Row 26 must be unreachable for a public caller."""
        result = run_screen(db, "Price to Earning < 20", row_cap=PUBLIC_ROW_CAP, page=2)
        assert result.returned == 0

    def test_no_cap_returns_everything_up_to_the_page_size(self, db: Engine) -> None:
        result = run_screen(db, "Price to Earning < 20", row_cap=None)
        assert result.returned == 30
        assert result.capped is False

    def test_a_result_set_below_the_cap_is_not_marked_capped(self, db: Engine) -> None:
        result = run_screen(db, "Return on equity > 15", row_cap=PUBLIC_ROW_CAP)
        assert result.total == 10
        assert result.capped is False

    def test_display_columns_are_selectable(self, db: Engine) -> None:
        result = run_screen(db, "Price to Earning < 20", display_columns=["Name", "PE"])
        assert [c["key"] for c in result.columns] == ["name", "pe"]
        assert set(result.rows[0]) == {"symbol", "name", "pe"}

    def test_an_unknown_display_column_is_refused(self, db: Engine) -> None:
        with pytest.raises(QueryError):
            run_screen(db, "PE < 20", display_columns=["Nonexistent"])

    def test_sorting_by_a_chosen_column(self, db: Engine) -> None:
        rows = run_screen(
            db, "Price to Earning < 20", sort_by="Current price", descending=False
        ).rows
        prices = [r["market_cap"] for r in rows]
        assert prices == sorted(prices)

    def test_a_query_matching_nothing_returns_an_empty_result(self, db: Engine) -> None:
        result = run_screen(db, "Market Capitalization > 99999999")
        assert result.total == 0
        assert result.rows == []

    def test_companies_without_a_market_cap_are_excluded(self, db: Engine) -> None:
        with db.begin() as conn:
            conn.execute(
                text("UPDATE company_snapshot SET market_cap = NULL WHERE symbol = 'CO000'")
            )
        assert all(r["symbol"] != "CO000" for r in run_screen(db, "Price to Earning < 20").rows)

    def test_elapsed_time_is_reported(self, db: Engine) -> None:
        assert run_screen(db, "Price to Earning < 20").elapsed_ms >= 0


class TestCacheKey:
    def test_whitespace_and_case_do_not_change_the_key(self) -> None:
        assert query_hash("PE  <  20") == query_hash("pe < 20")

    def test_different_queries_differ(self) -> None:
        assert query_hash("PE < 20") != query_hash("PE < 21")

    def test_normal_form(self) -> None:
        assert normalise_query("  PE   <  20 ") == "pe < 20"


class TestPresets:
    def test_every_preset_parses_and_compiles(self) -> None:
        """A preset must not rot when a column is renamed."""
        for preset in PRESETS:
            compile_query(parse(preset.query))

    def test_every_preset_column_resolves(self) -> None:
        from app.screener.execute import resolve_columns

        for preset in PRESETS:
            if preset.columns:
                resolve_columns(list(preset.columns))

    def test_slugs_are_unique(self) -> None:
        slugs = [p.slug for p in PRESETS]
        assert len(slugs) == len(set(slugs))

    def test_every_preset_runs(self, db: Engine) -> None:
        for preset in PRESETS:
            run_screen(db, preset.query, display_columns=list(preset.columns) or None)

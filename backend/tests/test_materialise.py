from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from app.db.engine import build_engine
from app.db.layer2 import (
    basic_financial,
    create_layer2,
    price_ratio_daily,
    ratio,
    shareholding,
)
from app.ingest import layer2_store as l2
from app.ingest.materialise import materialise

NOW = "2026-08-06T15:00:00+00:00"


@pytest.fixture
def db(tmp_path: Path) -> Engine:
    engine = build_engine(tmp_path / "mat.db")
    create_layer2(engine)
    return engine


def _period(symbol: str, code: str, kind: str, header: str, year: int, st: str = "c") -> dict:
    return {
        "symbol": symbol,
        "statement_type": st,
        "statement_code": code,
        "period_kind": kind,
        "header": header,
        "year": year,
        "period_start": None,
        "period_end": f"{year}-03-31",
        "result_date": None,
        "schema_kind": "general" if code == "pl" else "unknown",
    }


def _row(db: Engine, symbol: str) -> dict:
    with db.connect() as conn:
        return dict(
            conn.execute(text("SELECT * FROM company_snapshot WHERE symbol = :s"), {"s": symbol})
            .mappings()
            .one()
        )


class TestUnits:
    def test_money_lands_in_crore(self, db: Engine) -> None:
        l2.upsert_companies(db, [{"symbol": "X", "name": "X Ltd", "updated_at": NOW}])
        l2.store_statements(
            db,
            [_period("X", "pl", "annual", "Mar 2026", 2026)],
            [[{"field_name": "profitLossForPeriod", "value": 957540000000.0}]],
        )
        materialise(db)
        assert _row(db, "X")["net_profit"] == pytest.approx(95754.0)

    def test_eps_is_left_alone(self, db: Engine) -> None:
        l2.upsert_companies(db, [{"symbol": "X", "name": "X Ltd", "updated_at": NOW}])
        l2.store_statements(
            db,
            [_period("X", "pl", "annual", "Mar 2026", 2026)],
            [[{"field_name": "eps", "value": 59.69}]],
        )
        materialise(db)
        assert _row(db, "X")["eps"] == pytest.approx(59.69)

    def test_fractions_become_percentages(self, db: Engine) -> None:
        l2.upsert_companies(db, [{"symbol": "X", "name": "X Ltd", "updated_at": NOW}])
        l2.upsert(
            db,
            ratio,
            [
                {
                    "symbol": "X",
                    "statement_type": "c",
                    "family": "pr",
                    "header": "TTM",
                    "field_name": "returnOnEquity",
                    "year": 2026,
                    "value": 0.0827,
                }
            ],
        )
        materialise(db)
        assert _row(db, "X")["returnonequity"] == pytest.approx(8.27, abs=0.01)


class TestPreferences:
    def test_consolidated_beats_standalone(self, db: Engine) -> None:
        l2.upsert_companies(db, [{"symbol": "X", "name": "X Ltd", "updated_at": NOW}])
        l2.store_statements(
            db,
            [_period("X", "pl", "annual", "Mar 2026", 2026, st="s")],
            [[{"field_name": "profitLossForPeriod", "value": 1e10}]],
        )
        l2.store_statements(
            db,
            [_period("X", "pl", "annual", "Mar 2026", 2026, st="c")],
            [[{"field_name": "profitLossForPeriod", "value": 9e11}]],
        )
        materialise(db)
        assert _row(db, "X")["net_profit"] == pytest.approx(90000.0)

    def test_ttm_beats_the_latest_annual(self, db: Engine) -> None:
        l2.upsert_companies(db, [{"symbol": "X", "name": "X Ltd", "updated_at": NOW}])
        l2.store_statements(
            db,
            [_period("X", "pl", "annual", "Mar 2026", 2026)],
            [[{"field_name": "eps", "value": 50.0}]],
        )
        l2.store_statements(
            db,
            [_period("X", "pl", "ttm", "TTM", 2026)],
            [[{"field_name": "eps", "value": 55.22}]],
        )
        materialise(db)
        assert _row(db, "X")["eps"] == pytest.approx(55.22)

    def test_valuation_prefers_consolidated_not_alphabetical_order(self, db: Engine) -> None:
        """A (date, statement_type) tuple sorts "s" above "c".

        That silently reported RELIANCE at a P/E of 45.7 instead of 24.0.
        """
        l2.upsert_companies(db, [{"symbol": "X", "name": "X Ltd", "updated_at": NOW}])
        l2.upsert(
            db,
            price_ratio_daily,
            [
                {
                    "symbol": "X",
                    "statement_type": "s",
                    "quote_date": "2026-08-06",
                    "pe": 45.72,
                    "pb": 3.17,
                    "ptb": None,
                    "ps": None,
                    "pfcf": None,
                },
                {
                    "symbol": "X",
                    "statement_type": "c",
                    "quote_date": "2026-08-06",
                    "pe": 23.99,
                    "pb": 1.98,
                    "ptb": None,
                    "ps": None,
                    "pfcf": None,
                },
            ],
        )
        materialise(db)
        row = _row(db, "X")
        assert row["pe"] == pytest.approx(23.99)
        assert row["pb"] == pytest.approx(1.98)

    def test_a_later_date_still_wins_over_statement_type(self, db: Engine) -> None:
        l2.upsert_companies(db, [{"symbol": "X", "name": "X Ltd", "updated_at": NOW}])
        l2.upsert(
            db,
            price_ratio_daily,
            [
                {
                    "symbol": "X",
                    "statement_type": "c",
                    "quote_date": "2026-08-01",
                    "pe": 20.0,
                    "pb": None,
                    "ptb": None,
                    "ps": None,
                    "pfcf": None,
                },
                {
                    "symbol": "X",
                    "statement_type": "c",
                    "quote_date": "2026-08-06",
                    "pe": 24.0,
                    "pb": None,
                    "ptb": None,
                    "ps": None,
                    "pfcf": None,
                },
            ],
        )
        materialise(db)
        assert _row(db, "X")["pe"] == pytest.approx(24.0)


class TestSchemaFallbacks:
    def test_a_bank_gets_a_net_profit(self, db: Engine) -> None:
        """Banks report profitLossForThePeriod, not profitLossForPeriod."""
        l2.upsert_companies(db, [{"symbol": "BANKCO", "name": "Bank Co", "updated_at": NOW}])
        period = _period("BANKCO", "pl", "annual", "Mar 2026", 2026)
        period["schema_kind"] = "bank"
        l2.store_statements(
            db, [period], [[{"field_name": "profitLossForThePeriod", "value": 8.25e11}]]
        )
        materialise(db)
        assert _row(db, "BANKCO")["net_profit"] == pytest.approx(82500.0)

    def test_a_life_insurer_gets_a_net_profit(self, db: Engine) -> None:
        l2.upsert_companies(db, [{"symbol": "LIFECO", "name": "Life Co", "updated_at": NOW}])
        period = _period("LIFECO", "pl", "annual", "Mar 2026", 2026)
        period["schema_kind"] = "life_insurance"
        l2.store_statements(
            db,
            [period],
            [[{"field_name": "profitLossAfterTaxAndExtraordinaryItems", "value": 1.975e10}]],
        )
        materialise(db)
        assert _row(db, "LIFECO")["net_profit"] == pytest.approx(1975.0)

    def test_the_primary_field_wins_when_both_are_present(self, db: Engine) -> None:
        l2.upsert_companies(db, [{"symbol": "X", "name": "X Ltd", "updated_at": NOW}])
        l2.store_statements(
            db,
            [_period("X", "pl", "annual", "Mar 2026", 2026)],
            [
                [
                    {"field_name": "profitLossForPeriod", "value": 1e10},
                    {"field_name": "profitLossForThePeriod", "value": 9e11},
                ]
            ],
        )
        materialise(db)
        assert _row(db, "X")["net_profit"] == pytest.approx(1000.0)

    def test_schema_kind_reaches_the_snapshot(self, db: Engine) -> None:
        l2.upsert_companies(db, [{"symbol": "BANKCO", "name": "Bank Co", "updated_at": NOW}])
        period = _period("BANKCO", "pl", "annual", "Mar 2026", 2026)
        period["schema_kind"] = "bank"
        l2.store_statements(db, [period], [[{"field_name": "eps", "value": 1.0}]])
        materialise(db)
        assert _row(db, "BANKCO")["schema_kind"] == "bank"


class TestComputed:
    def test_enterprise_value_and_ev_ebitda(self, db: Engine) -> None:
        l2.upsert_companies(db, [{"symbol": "X", "name": "X Ltd", "updated_at": NOW}])
        l2.upsert_quotes(
            db,
            [
                {
                    "symbol": "X",
                    "market_cap": 100000.0,
                    "current_price": 100.0,
                    "high52": 150.0,
                    "low52": 50.0,
                    "updated_at": NOW,
                }
            ],
        )
        l2.upsert(
            db,
            basic_financial,
            [
                {
                    "symbol": "X",
                    "statement_type": "c",
                    "statement_code": "bs",
                    "header": "TTM",
                    "field_name": "totalDebt",
                    "year": 2026,
                    "value": 2e11,
                },
                {
                    "symbol": "X",
                    "statement_type": "c",
                    "statement_code": "bs",
                    "header": "TTM",
                    "field_name": "totalCash",
                    "year": 2026,
                    "value": 1e11,
                },
                {
                    "symbol": "X",
                    "statement_type": "c",
                    "statement_code": "pl",
                    "header": "TTM",
                    "field_name": "ebitda",
                    "year": 2026,
                    "value": 1e11,
                },
            ],
        )
        materialise(db)
        row = _row(db, "X")
        # 100,000 + 20,000 - 10,000 = 110,000 crore
        assert row["enterprise_value"] == pytest.approx(110000.0)
        assert row["ev_ebitda"] == pytest.approx(11.0)

    def test_distance_from_52_week_extremes(self, db: Engine) -> None:
        l2.upsert_companies(db, [{"symbol": "X", "name": "X Ltd", "updated_at": NOW}])
        l2.upsert_quotes(
            db,
            [
                {
                    "symbol": "X",
                    "current_price": 100.0,
                    "high52": 150.0,
                    "low52": 50.0,
                    "market_cap": 1.0,
                    "updated_at": NOW,
                }
            ],
        )
        materialise(db)
        row = _row(db, "X")
        assert row["down_from_52w_high"] == pytest.approx(33.333, abs=0.01)
        assert row["up_from_52w_low"] == pytest.approx(100.0)

    def test_promoter_holding_and_pledge(self, db: Engine) -> None:
        l2.upsert_companies(db, [{"symbol": "X", "name": "X Ltd", "updated_at": NOW}])
        l2.upsert(
            db,
            shareholding,
            [
                {
                    "symbol": "X",
                    "period_label": "Mar 2026",
                    "group_name": "promoterAndPromoterGroup",
                    "shareholding_pct": 50.0,
                    "total_shares": 1.0,
                    "total_shareholders": 1.0,
                    "pledged_pct": 2.5,
                    "locked_in_pct": 0.0,
                },
                {
                    "symbol": "X",
                    "period_label": "Jun 2026",
                    "group_name": "promoterAndPromoterGroup",
                    "shareholding_pct": 50.48,
                    "total_shares": 1.0,
                    "total_shareholders": 1.0,
                    "pledged_pct": 0.0,
                    "locked_in_pct": 0.0,
                },
            ],
        )
        materialise(db)
        row = _row(db, "X")
        # Jun 2026 is the later quarter even though "Jun" < "Mar" alphabetically.
        assert row["promoter_holding"] == pytest.approx(50.48)
        assert row["promoter_pledge"] == pytest.approx(0.0)


class TestRebuild:
    def test_materialise_is_idempotent(self, db: Engine) -> None:
        l2.upsert_companies(db, [{"symbol": "X", "name": "X Ltd", "updated_at": NOW}])
        first = materialise(db)
        second = materialise(db)
        assert first["companies"] == second["companies"] == 1

    def test_a_removed_company_does_not_linger(self, db: Engine) -> None:
        l2.upsert_companies(
            db,
            [
                {"symbol": "X", "name": "X Ltd", "updated_at": NOW},
                {"symbol": "Y", "name": "Y Ltd", "updated_at": NOW},
            ],
        )
        materialise(db)
        with db.begin() as conn:
            conn.execute(text("DELETE FROM company WHERE symbol = 'Y'"))
        materialise(db)
        with db.connect() as conn:
            rows = conn.execute(text("SELECT symbol FROM company_snapshot")).all()
        assert [r[0] for r in rows] == ["X"]

    def test_empty_database(self, db: Engine) -> None:
        assert materialise(db)["companies"] == 0

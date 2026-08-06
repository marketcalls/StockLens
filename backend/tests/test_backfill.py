from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import Engine, select

from app.db.engine import build_engine
from app.db.layer2 import (
    basic_financial,
    company,
    corporate_action,
    create_layer2,
    index_constituent,
    metric,
    price_ratio_annual,
    quote,
    ratio,
    statement_period,
)
from app.finedge.endpoints import Call
from app.ingest import layer2_store as l2
from app.ingest.backfill import (
    CALLS_PER_SYMBOL,
    _normalise_call,
    dry_run,
    prioritised_symbols,
)

BASE = "https://data.finedgeapi.com"
NOW = "2026-08-06T15:00:00+00:00"


@pytest.fixture
def db(tmp_path: Path) -> Engine:
    engine = build_engine(tmp_path / "backfill.db")
    create_layer2(engine)
    return engine


def _seed(db: Engine) -> None:
    l2.upsert_companies(
        db,
        [
            {"symbol": "BIGINDEX", "name": "Big Index Co", "updated_at": NOW},
            {"symbol": "SMALLINDEX", "name": "Small Index Co", "updated_at": NOW},
            {"symbol": "OTHERINDEX", "name": "Other Index Co", "updated_at": NOW},
            {"symbol": "BIGOUTSIDE", "name": "Big Outside Co", "updated_at": NOW},
            {"symbol": "TINY", "name": "Tiny Co", "updated_at": NOW},
            {"symbol": "NOQUOTE", "name": "No Quote Co", "updated_at": NOW},
        ],
    )
    l2.upsert_quotes(
        db,
        [
            {"symbol": "BIGINDEX", "market_cap": 500000.0, "updated_at": NOW},
            {"symbol": "SMALLINDEX", "market_cap": 1000.0, "updated_at": NOW},
            {"symbol": "OTHERINDEX", "market_cap": 5000.0, "updated_at": NOW},
            {"symbol": "BIGOUTSIDE", "market_cap": 900000.0, "updated_at": NOW},
            {"symbol": "TINY", "market_cap": 5.0, "updated_at": NOW},
        ],
    )
    l2.replace_index_master(
        db,
        [{"index_symbol": "NIF50", "index_name": "Nifty 50", "updated_at": NOW}],
        [{"index_symbol": "NIF50", "symbol": s} for s in ("BIGINDEX", "SMALLINDEX")],
    )
    l2.replace_index_master(
        db,
        [{"index_symbol": "SOMEOTHER", "index_name": "Some Other", "updated_at": NOW}],
        [{"index_symbol": "SOMEOTHER", "symbol": "OTHERINDEX"}],
    )


class TestPrioritisation:
    def test_priority_index_members_come_first(self, db: Engine) -> None:
        _seed(db)
        order = prioritised_symbols(db)
        assert order[0] == "BIGINDEX"
        assert order[1] == "SMALLINDEX"

    def test_a_huge_company_outside_the_priority_indices_does_not_jump_the_queue(
        self, db: Engine
    ) -> None:
        """BIGOUTSIDE has the largest cap but no priority-index membership."""
        _seed(db)
        order = prioritised_symbols(db)
        assert order.index("SMALLINDEX") < order.index("BIGOUTSIDE")

    def test_other_index_members_beat_non_members(self, db: Engine) -> None:
        _seed(db)
        order = prioritised_symbols(db)
        assert order.index("OTHERINDEX") < order.index("BIGOUTSIDE")

    def test_within_a_tier_bigger_market_cap_wins(self, db: Engine) -> None:
        _seed(db)
        order = prioritised_symbols(db)
        assert order.index("BIGOUTSIDE") < order.index("TINY")

    def test_companies_without_a_quote_are_kept_not_dropped(self, db: Engine) -> None:
        """A missing quote does not mean a missing company."""
        _seed(db)
        order = prioritised_symbols(db)
        assert "NOQUOTE" in order
        assert order[-1] == "NOQUOTE"

    def test_limit_truncates(self, db: Engine) -> None:
        _seed(db)
        assert len(prioritised_symbols(db, limit=3)) == 3

    def test_empty_universe(self, db: Engine) -> None:
        assert prioritised_symbols(db) == []


class TestDryRun:
    def test_reports_cost_without_fetching(self, db: Engine) -> None:
        report = dry_run(db, ["A", "B", "C"], rps=5.0)
        assert report["symbols"] == 3
        assert report["estimated_calls"] == 3 * CALLS_PER_SYMBOL

    def test_whole_universe_estimate_is_in_the_expected_range(self, db: Engine) -> None:
        """~332k calls at 59 per symbol across 5,630 companies."""
        report = dry_run(db, [f"S{i}" for i in range(5630)], rps=5.0)
        assert 300_000 < report["estimated_calls"] < 360_000
        assert 15 < report["estimated_hours"] < 22

    @respx.mock
    def test_dry_run_makes_no_requests(self, db: Engine) -> None:
        route = respx.get(url__startswith=BASE).mock(return_value=httpx.Response(200))
        dry_run(db, ["RELIANCE"])
        assert route.call_count == 0


class TestNormaliseRouting:
    def test_profile(self, db: Engine) -> None:
        l2.upsert_companies(db, [{"symbol": "ITC", "name": "ITC Ltd", "updated_at": NOW}])
        call = Call("/api/v1/company-profile/ITC", {}, "ITC")
        _normalise_call(db, "ITC", call, {"macro_sector": "FMCG", "sector": "Cigarettes"})
        with db.connect() as conn:
            row = conn.execute(select(company).where(company.c.symbol == "ITC")).mappings().one()
        assert row["macro_sector"] == "FMCG"

    def test_statements(self, db: Engine) -> None:
        call = Call(
            "/api/v1/financials/ITC",
            {"statement_type": "c", "statement_code": "pl", "period": "annual"},
            "ITC",
        )
        payload = {
            "financials": [
                {
                    "header": "Mar 2026",
                    "year": 2026,
                    "period_end": "20260331",
                    "income": 1000.0,
                    "revenueFromOperations": 900.0,
                    "costofGoodsSold": 400.0,
                    "employeeBenefitExpense": 100.0,
                    "financeCosts": 10.0,
                    "depreciationAndAmortisation": 20.0,
                    "changesInInventories": 1.0,
                    "costOfMaterialsConsumed": 2.0,
                    "purchasesOfStockInTrade": 3.0,
                    "eps": 16.19,
                }
            ]
        }
        assert _normalise_call(db, "ITC", call, payload) > 0
        with db.connect() as conn:
            row = conn.execute(select(statement_period)).mappings().one()
        assert row["schema_kind"] == "general"
        assert row["period_end"] == "2026-03-31"

    def test_basic_financials(self, db: Engine) -> None:
        call = Call(
            "/api/v1/basic-financials/ITC",
            {"statement_type": "c", "statement_code": "pl"},
            "ITC",
        )
        payload = {"ratios": [{"header": "TTM", "year": 2026, "ebitda": 100.0, "ebit": 90.0}]}
        assert _normalise_call(db, "ITC", call, payload) == 2
        with db.connect() as conn:
            names = {r[0] for r in conn.execute(select(basic_financial.c.field_name)).all()}
        assert names == {"ebitda", "ebit"}

    def test_ratios(self, db: Engine) -> None:
        call = Call("/api/v1/ratios/ITC", {"statement_type": "c", "ratio_type": "pr"}, "ITC")
        payload = {"ratios": [{"header": "TTM", "year": 2026, "returnOnEquity": 0.0827}]}
        _normalise_call(db, "ITC", call, payload)
        with db.connect() as conn:
            row = conn.execute(select(ratio)).mappings().one()
        assert row["family"] == "pr"
        assert row["value"] == 0.0827

    def test_metrics(self, db: Engine) -> None:
        call = Call(
            "/api/v1/financial-metrics/ITC",
            {"statement_type": "c", "ratio_type": "gr"},
            "ITC",
        )
        payload = {"financial_metrics": {"revenueGrowth3years": 0.0688}, "symbol": "ITC"}
        _normalise_call(db, "ITC", call, payload)
        with db.connect() as conn:
            row = conn.execute(select(metric)).mappings().one()
        assert row["field_name"] == "revenueGrowth3years"

    def test_annual_price_ratios_treat_zero_as_missing(self, db: Engine) -> None:
        """pb=0 means the ratio could not be computed, not that book value is infinite."""
        call = Call("/api/v1/annual-price-ratios/ITC", {"statement_type": "c"}, "ITC")
        payload = {
            "price_ratios": [{"header": "Dec 2024", "year": 2024, "pe": 35.1, "pb": 0, "ps": 2.42}]
        }
        _normalise_call(db, "ITC", call, payload)
        with db.connect() as conn:
            row = conn.execute(select(price_ratio_annual)).mappings().one()
        assert row["pe"] == 35.1
        assert row["pb"] is None

    def test_dividends(self, db: Engine) -> None:
        call = Call("/api/v1/dividend/ITC", {}, "ITC")
        payload = {
            "dividend": [{"date": "27-May-2026", "amount": 8, "dividend_type": "final dividend"}]
        }
        _normalise_call(db, "ITC", call, payload)
        with db.connect() as conn:
            row = conn.execute(select(corporate_action)).mappings().one()
        assert row["ex_date"] == "2026-05-27"
        assert row["action"] == "dividend"

    def test_bonus(self, db: Engine) -> None:
        call = Call("/api/v1/corporate-actions/bonus/RELIANCE", {}, "RELIANCE")
        payload = {"bonus": [{"action": "Bonus issue 1:1", "date": "28-Oct-2024"}]}
        _normalise_call(db, "RELIANCE", call, payload)
        with db.connect() as conn:
            row = conn.execute(select(corporate_action)).mappings().one()
        assert row["action"] == "bonus"
        assert row["subject"] == "Bonus issue 1:1"

    def test_unknown_endpoint_is_archived_but_not_normalised(self, db: Engine) -> None:
        """A new endpoint must not silently corrupt Layer 2."""
        call = Call("/api/v1/something-new/ITC", {}, "ITC")
        assert _normalise_call(db, "ITC", call, {"anything": 1}) == 0

    def test_empty_payload_writes_nothing(self, db: Engine) -> None:
        call = Call(
            "/api/v1/financials/ITC",
            {"statement_type": "c", "statement_code": "pl", "period": "annual"},
            "ITC",
        )
        assert _normalise_call(db, "ITC", call, {}) == 0


def test_index_constituent_seed_is_isolated(db: Engine) -> None:
    _seed(db)
    with db.connect() as conn:
        count = len(conn.execute(select(index_constituent)).all())
    assert count == 3
    with db.connect() as conn:
        quotes = len(conn.execute(select(quote)).all())
    assert quotes == 5

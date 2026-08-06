from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, select

from app.db.engine import build_engine
from app.db.layer2 import company, create_layer2, index_constituent, index_return, quote
from app.ingest import layer2_store as l2


@pytest.fixture
def db(tmp_path: Path) -> Engine:
    engine = build_engine(tmp_path / "layer2.db")
    create_layer2(engine)
    return engine


NOW = "2026-08-06T15:00:00+00:00"


class TestCompanies:
    def test_insert_then_update_by_symbol(self, db: Engine) -> None:
        l2.upsert_companies(db, [{"symbol": "ITC", "name": "ITC Ltd", "updated_at": NOW}])
        l2.upsert_companies(db, [{"symbol": "ITC", "name": "ITC Limited", "updated_at": NOW}])
        with db.connect() as conn:
            rows = conn.execute(select(company.c.symbol, company.c.name)).all()
        assert len(rows) == 1
        assert rows[0].name == "ITC Limited"

    def test_profile_merge_keeps_identity_from_the_symbol_master(self, db: Engine) -> None:
        """The two sources own different columns; neither may null the other's."""
        l2.upsert_companies(
            db,
            [
                {
                    "symbol": "RELIANCE",
                    "name": "Reliance Industries Ltd",
                    "nse_code": "RELIANCE",
                    "bse_code": "500325",
                    "updated_at": NOW,
                }
            ],
        )
        l2.update_company_profiles(
            db,
            [
                {
                    "symbol": "RELIANCE",
                    "macro_sector": "Energy",
                    "industry": "Petroleum Products",
                    "sector": "Refineries & Marketing",
                    "website": "www.ril.com",
                    "name": None,
                    "updated_at": NOW,
                }
            ],
        )
        with db.connect() as conn:
            row = (
                conn.execute(select(company).where(company.c.symbol == "RELIANCE")).mappings().one()
            )
        assert row["nse_code"] == "RELIANCE"
        assert row["name"] == "Reliance Industries Ltd"
        assert row["macro_sector"] == "Energy"
        assert row["industry"] == "Petroleum Products"

    def test_profile_for_an_unknown_symbol_creates_the_row(self, db: Engine) -> None:
        l2.update_company_profiles(
            db, [{"symbol": "NEWCO", "macro_sector": "Energy", "updated_at": NOW}]
        )
        with db.connect() as conn:
            row = conn.execute(select(company).where(company.c.symbol == "NEWCO")).mappings().one()
        assert row["name"] == "NEWCO"

    def test_empty_input_writes_nothing(self, db: Engine) -> None:
        assert l2.upsert_companies(db, []) == 0


class TestQuotes:
    def test_refresh_overwrites_the_previous_quote(self, db: Engine) -> None:
        l2.upsert_quotes(db, [{"symbol": "ITC", "current_price": 285.0, "updated_at": NOW}])
        l2.upsert_quotes(db, [{"symbol": "ITC", "current_price": 291.5, "updated_at": NOW}])
        with db.connect() as conn:
            rows = conn.execute(select(quote.c.symbol, quote.c.current_price)).all()
        assert len(rows) == 1
        assert rows[0].current_price == 291.5

    def test_batches_beyond_the_chunk_size(self, db: Engine) -> None:
        """5,630 companies arrive in one payload; chunking must not lose any."""
        rows = [
            {"symbol": f"SYM{i:05d}", "current_price": float(i), "updated_at": NOW}
            for i in range(1000)
        ]
        assert l2.upsert_quotes(db, rows) == 1000
        assert l2.counts(db)["quotes"] == 1000


class TestIndexMembership:
    def test_constituents_are_replaced_not_accumulated(self, db: Engine) -> None:
        """Indices rebalance. A dropped company must not stay a member forever."""
        indices = [{"index_symbol": "NIF50", "index_name": "Nifty 50", "updated_at": NOW}]
        l2.replace_index_master(
            db,
            indices,
            [{"index_symbol": "NIF50", "symbol": s} for s in ("RELIANCE", "ITC", "OLDCO")],
        )
        l2.replace_index_master(
            db,
            indices,
            [{"index_symbol": "NIF50", "symbol": s} for s in ("RELIANCE", "ITC", "NEWCO")],
        )
        with db.connect() as conn:
            members = {
                r.symbol
                for r in conn.execute(
                    select(index_constituent.c.symbol).where(
                        index_constituent.c.index_symbol == "NIF50"
                    )
                ).all()
            }
        assert members == {"RELIANCE", "ITC", "NEWCO"}

    def test_other_indices_are_untouched(self, db: Engine) -> None:
        l2.replace_index_master(
            db,
            [{"index_symbol": "BSE500", "index_name": "BSE 500", "updated_at": NOW}],
            [{"index_symbol": "BSE500", "symbol": "SOMECO"}],
        )
        l2.replace_index_master(
            db,
            [{"index_symbol": "NIF50", "index_name": "Nifty 50", "updated_at": NOW}],
            [{"index_symbol": "NIF50", "symbol": "RELIANCE"}],
        )
        with db.connect() as conn:
            count = conn.execute(
                select(index_constituent.c.symbol).where(
                    index_constituent.c.index_symbol == "BSE500"
                )
            ).all()
        assert len(count) == 1


class TestIndexReturns:
    def test_returns_are_replaced_per_index(self, db: Engine) -> None:
        l2.replace_index_returns(
            db,
            [
                {
                    "index_symbol": "NIF50",
                    "horizon": "1Y",
                    "return_pct": 2.84,
                    "as_of": "2026-08-06",
                },
                {
                    "index_symbol": "NIF50",
                    "horizon": "10Y",
                    "return_pct": 11.21,
                    "as_of": "2026-08-06",
                },
            ],
        )
        l2.replace_index_returns(
            db,
            [{"index_symbol": "NIF50", "horizon": "1Y", "return_pct": 3.1, "as_of": "2026-08-07"}],
        )
        with db.connect() as conn:
            rows = conn.execute(select(index_return.c.horizon, index_return.c.return_pct)).all()
        assert len(rows) == 1
        assert rows[0].return_pct == 3.1


class TestStatements:
    PERIOD = {
        "symbol": "RELIANCE",
        "statement_type": "c",
        "statement_code": "pl",
        "period_kind": "annual",
        "header": "Mar 2026",
        "year": 2026,
        "period_start": "2025-04-01",
        "period_end": "2026-03-31",
        "result_date": "2026-04-18",
        "schema_kind": "general",
    }

    def test_writes_periods_and_lines(self, db: Engine) -> None:
        periods, lines = l2.store_statements(
            db,
            [self.PERIOD],
            [[{"field_name": "income", "value": 1.0}, {"field_name": "eps", "value": 55.22}]],
        )
        assert (periods, lines) == (1, 2)
        assert l2.counts(db)["statement_lines"] == 2

    def test_a_restatement_replaces_lines_rather_than_merging(self, db: Engine) -> None:
        """A removed line must not survive as a stale value."""
        l2.store_statements(
            db,
            [self.PERIOD],
            [
                [
                    {"field_name": "income", "value": 1.0},
                    {"field_name": "exceptionalItemsBeforeTax", "value": 99.0},
                ]
            ],
        )
        l2.store_statements(db, [self.PERIOD], [[{"field_name": "income", "value": 2.0}]])
        counts = l2.counts(db)
        assert counts["statement_periods"] == 1
        assert counts["statement_lines"] == 1

    def test_different_periods_coexist(self, db: Engine) -> None:
        other = {**self.PERIOD, "header": "Mar 2025", "year": 2025}
        l2.store_statements(
            db,
            [self.PERIOD, other],
            [[{"field_name": "income", "value": 1.0}], [{"field_name": "income", "value": 2.0}]],
        )
        assert l2.counts(db)["statement_periods"] == 2

    def test_standalone_and_consolidated_are_separate_periods(self, db: Engine) -> None:
        standalone = {**self.PERIOD, "statement_type": "s"}
        l2.store_statements(
            db,
            [self.PERIOD, standalone],
            [[{"field_name": "income", "value": 1.0}], [{"field_name": "income", "value": 2.0}]],
        )
        assert l2.counts(db)["statement_periods"] == 2

    def test_empty_input(self, db: Engine) -> None:
        assert l2.store_statements(db, [], []) == (0, 0)


def test_counts_on_an_empty_database(db: Engine) -> None:
    assert l2.counts(db) == {
        "companies": 0,
        "quotes": 0,
        "statement_periods": 0,
        "statement_lines": 0,
        "price_days": 0,
        "indices": 0,
        "index_constituents": 0,
        "index_returns": 0,
    }

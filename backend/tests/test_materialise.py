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


class TestEnterpriseMultiple:
    """EV/EBITDA needs a denominator that means something."""

    # EBITDA is stored in rupees and scaled to crore on the way in.
    RUPEES_PER_CRORE = 1e7

    def _company(self, db: Engine, ebitda_crore: float, mcap: float = 187894.0) -> dict:
        l2.upsert_companies(db, [{"symbol": "X", "name": "X Ltd", "updated_at": NOW}])
        l2.upsert_quotes(
            db,
            [{"symbol": "X", "current_price": 100.0, "market_cap": mcap, "updated_at": NOW}],
        )
        l2.upsert(
            db,
            basic_financial,
            [
                {
                    "symbol": "X",
                    "statement_type": "c",
                    "statement_code": "pl",
                    "header": "TTM",
                    "field_name": "ebitda",
                    "year": 2026,
                    "value": ebitda_crore * self.RUPEES_PER_CRORE,
                }
            ],
        )
        materialise(db)
        return _row(db, "X")

    def test_a_near_zero_ebitda_produces_no_multiple(self, db: Engine) -> None:
        # VAML reports EBITDA of -0.03 Cr against an enterprise value of
        # 187,894 Cr. Divided out that is -6,242,332, which sorts to the front
        # of any screen on EV/EBITDA and carries no information.
        row = self._company(db, ebitda_crore=-0.0301)
        assert row["ebitda"] == pytest.approx(-0.0301, abs=1e-6)
        assert row["ev_ebitda"] is None
        assert row["enterprise_value"] is not None, "the EV itself is still real"

    def test_a_real_ebitda_still_gets_a_multiple(self, db: Engine) -> None:
        row = self._company(db, ebitda_crore=20000.0)
        assert row["ev_ebitda"] == pytest.approx(187894.0 / 20000.0, abs=0.01)

    def test_a_genuine_operating_loss_keeps_its_negative_multiple(self, db: Engine) -> None:
        # Negative EBITDA is a real measurement when it is large enough to mean
        # something. Only the near-zero denominator is excluded.
        row = self._company(db, ebitda_crore=-5000.0)
        assert row["ev_ebitda"] == pytest.approx(187894.0 / -5000.0, abs=0.01)

    def test_the_threshold_is_on_magnitude_not_sign(self, db: Engine) -> None:
        from app.ingest.materialise import MIN_EBITDA_FOR_MULTIPLE

        half = MIN_EBITDA_FOR_MULTIPLE / 2
        assert self._company(db, ebitda_crore=half)["ev_ebitda"] is None
        assert self._company(db, ebitda_crore=-half)["ev_ebitda"] is None
        assert self._company(db, ebitda_crore=MIN_EBITDA_FOR_MULTIPLE * 2)["ev_ebitda"] is not None


class TestTrailingDividend:
    """The twelve-month window must belong to the company, not the database.

    The cutoff used to be derived from the latest ex-date anywhere in the
    corporate-actions table, so every company's trailing dividend depended on
    what other companies happened to be loaded. When the backfill reached
    Glenmark, whose next ex-date is 2026-08-31, the cutoff jumped to 2025-08-31
    and Reliance's 2025-08-14 dividend fell outside it - halving Reliance's
    yield from 0.87% to 0.45% without a single figure of its own changing.
    """

    TODAY = "2026-08-07"

    def _dividends(self, db: Engine, rows: list[tuple[str, str, float]]) -> dict:
        from app.db.layer2 import corporate_action
        from app.ingest.materialise import _load_dividends

        l2.upsert(
            db,
            corporate_action,
            [
                {
                    "symbol": symbol,
                    "action": "dividend",
                    "ex_date": ex_date,
                    "subject": "final dividend",
                    "amount": amount,
                    "dividend_type": "final dividend",
                }
                for symbol, ex_date, amount in rows
            ],
        )
        return _load_dividends(db, today=self.TODAY)

    def test_one_companys_dividend_does_not_move_anothers_window(self, db: Engine) -> None:
        totals = self._dividends(
            db,
            [
                ("RELIANCE", "2026-06-05", 6.0),
                ("RELIANCE", "2025-08-14", 5.5),
                # Glenmark's ex-date is later than both, and in the future.
                ("GLENMARK", "2026-08-31", 2.5),
            ],
        )
        assert totals["RELIANCE"] == 11.5

    def test_a_dividend_that_has_not_gone_ex_is_not_trailing(self, db: Engine) -> None:
        totals = self._dividends(
            db, [("GLENMARK", "2026-08-31", 2.5), ("GLENMARK", "2026-03-01", 2.5)]
        )
        assert totals["GLENMARK"] == 2.5

    def test_a_dividend_older_than_a_year_is_excluded(self, db: Engine) -> None:
        totals = self._dividends(db, [("X", "2026-06-05", 6.0), ("X", "2025-08-06", 99.0)])
        assert totals["X"] == 6.0

    def test_the_boundary_is_a_year_back_from_today(self, db: Engine) -> None:
        # 2025-08-07 is exactly a year before TODAY and is outside; the next day
        # is inside. Pinned because an off-by-one here silently drops a dividend.
        assert self._dividends(db, [("X", "2025-08-07", 5.0)]) == {}
        assert self._dividends(db, [("Y", "2025-08-08", 5.0)])["Y"] == 5.0

    def test_a_company_that_pays_nothing_is_absent_not_zero(self, db: Engine) -> None:
        assert "NOPAYER" not in self._dividends(db, [("X", "2026-06-05", 6.0)])


class TestPriceCagrHorizon:
    """A "three year" return must be measured over three years.

    The base price used to be found by counting a fixed 248 trading days per
    year backwards. A company whose history has gaps - suspended, thinly traded,
    relisted after a demerger - runs out of sessions long before it runs out of
    calendar. United Spirits' three-year figure was measured across 13.46 years
    and then annualised as though it were three; 360 ONE's five-year figure
    spanned 9.12.
    """

    @staticmethod
    def _dates(start: str, count: int, step_days: int) -> list[str]:
        from datetime import date, timedelta

        begin = date.fromisoformat(start)
        return [(begin + timedelta(days=i * step_days)).isoformat() for i in range(count)]

    def test_a_dense_history_finds_the_price_a_year_back(self) -> None:
        from datetime import date, timedelta

        from app.ingest.materialise import _price_years_ago

        # Daily sessions for four years.
        dates = self._dates("2022-08-07", 1460, 1)
        closes = [100.0 + i for i in range(len(dates))]

        # Derived from the last date in the series, not assumed: 1460 daily
        # steps from 2022-08-07 ends on 2026-08-05, not 2026-08-07.
        a_year_back = (date.fromisoformat(dates[-1]) - timedelta(days=365)).isoformat()
        assert _price_years_ago(dates, closes, 1) == closes[dates.index(a_year_back)]

    def test_a_gappy_history_gives_no_figure_rather_than_a_wrong_one(self) -> None:
        from app.ingest.materialise import _price_years_ago

        # Only 300 sessions, but spread across thirteen years. Counting 3 * 248
        # sessions back would run off the start; by date there is no price
        # anywhere near three years ago either, because the gap straddles it.
        dates = self._dates("2013-01-01", 40, 16) + self._dates("2026-01-01", 5, 1)
        closes = [10.0] * 40 + [900.0] * 5
        assert _price_years_ago(dates, closes, 3) is None

    def test_a_price_close_enough_to_the_mark_is_used(self) -> None:
        from app.ingest.materialise import _price_years_ago

        # Weekly sessions: the nearest to three years back is within days.
        dates = self._dates("2020-01-01", 350, 7)
        closes = [float(i) for i in range(len(dates))]
        assert _price_years_ago(dates, closes, 3) is not None

    def test_a_history_shorter_than_the_horizon_gives_nothing(self) -> None:
        from app.ingest.materialise import _price_years_ago

        dates = self._dates("2025-01-01", 400, 1)
        closes = [100.0] * 400
        assert _price_years_ago(dates, closes, 10) is None

    def test_the_tolerance_is_proportional_to_the_horizon(self) -> None:
        from app.ingest.materialise import _price_years_ago

        # Six months adrift is fatal on a one-year horizon and fine on ten.
        one_year_gap = ["2025-02-07", "2026-08-07"]
        assert _price_years_ago(one_year_gap, [10.0, 20.0], 1) is None

        ten_year_gap = ["2016-02-07", "2026-08-07"]
        assert _price_years_ago(ten_year_gap, [10.0, 20.0], 10) is not None

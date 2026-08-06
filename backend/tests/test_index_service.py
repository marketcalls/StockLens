"""Index detail, and the members that are not equities.

Index constituent lists reference REITs, InvITs and SME listings by scrip code.
Those never appear in the equity symbol master, so they have no company page and
no statements - but they are genuine members, and dropping them would misstate
the index.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.db.layer2 import create_layer2, index_constituent, index_master
from app.screener.catalog import snapshot_ddl
from app.services import index as index_service
from app.services.errors import NotFound


@pytest.fixture
def db(engines):
    engine = engines[0]
    create_layer2(engine)
    with engine.begin() as conn:
        conn.execute(text(snapshot_ddl()))
        conn.execute(
            index_master.insert().values(
                index_symbol="TESTIDX",
                index_name="Test Index",
                exchange="BSE",
                index_type="equity",
                index_sub_type="Thematic Indices",
                market_cap=None,
                updated_at="2026-08-07T00:00:00+00:00",
            )
        )
        # One real equity, two members identified only by scrip code.
        conn.execute(
            text(
                "INSERT INTO company (symbol, name, updated_at)"
                " VALUES ('REALCO', 'Real Co Ltd', '')"
            )
        )
        for symbol in ("REALCO", "540526", "543217"):
            conn.execute(index_constituent.insert().values(index_symbol="TESTIDX", symbol=symbol))
    return engine


def test_non_equity_members_are_flagged_not_dropped(db) -> None:
    detail = index_service.detail("TESTIDX", engine=db)

    assert detail["count"] == 3, "all three are genuine members of the index"
    assert detail["outside_universe"] == 2

    flags = {c["symbol"]: c["in_universe"] for c in detail["constituents"]}
    assert flags["REALCO"] is True
    assert flags["540526"] is False
    assert flags["543217"] is False


def test_in_universe_is_a_real_bool_not_a_sqlite_integer(db) -> None:
    # SQLite has no boolean type, so the raw column comes back as 0/1. A JSON
    # consumer checking `if (row.in_universe)` would be fine, but one rendering
    # the value, or an agent comparing to False, would not.
    detail = index_service.detail("TESTIDX", engine=db)
    for row in detail["constituents"]:
        assert isinstance(row["in_universe"], bool)


def test_an_index_of_only_non_equities_reports_it(db) -> None:
    with db.begin() as conn:
        conn.execute(
            text("DELETE FROM index_constituent WHERE index_symbol='TESTIDX' AND symbol='REALCO'")
        )
    detail = index_service.detail("TESTIDX", engine=db)
    assert detail["count"] == 2
    assert detail["outside_universe"] == 2
    assert detail["with_fundamentals"] == 0


def test_unknown_index_is_a_miss(db) -> None:
    with pytest.raises(NotFound):
        index_service.detail("NOSUCHINDEX", engine=db)


def test_lookup_is_case_insensitive(db) -> None:
    assert index_service.detail("testidx", engine=db)["index_symbol"] == "TESTIDX"


class TestConstituentMedians:
    """A median is meant to answer "what is a typical valuation here"."""

    @staticmethod
    def _seed(engine, rows):
        """rows: (symbol, pe, pb, returnonequity, net_profit)."""
        with engine.begin() as conn:
            for symbol, pe, pb, roe, profit in rows:
                conn.execute(
                    text("INSERT INTO company (symbol, name, updated_at) VALUES (:s, :s, '')"),
                    {"s": symbol},
                )
                conn.execute(
                    text(
                        "INSERT INTO company_snapshot (symbol, name, updated_at, pe, pb,"
                        " returnonequity, net_profit) VALUES (:s, :s, '', :pe, :pb, :roe, :np)"
                    ),
                    {"s": symbol, "pe": pe, "pb": pb, "roe": roe, "np": profit},
                )
                conn.execute(
                    index_constituent.insert().values(index_symbol="TESTIDX", symbol=symbol)
                )

    def test_a_negative_pe_is_left_out_of_the_median(self, db) -> None:
        # IndiGo comes back at -42.8 on a Rs. 4,808 Cr loss. Sorted into the
        # median it lands at the bottom and reads as the index's cheapest stock.
        self._seed(
            db,
            [
                ("LOSSCO", -42.8, 1.0, -15.0, -4807.9),
                ("CHEAPCO", 12.0, 1.5, 18.0, 500.0),
                ("MIDCO", 24.0, 3.0, 15.0, 800.0),
                ("DEARCO", 60.0, 8.0, 12.0, 900.0),
            ],
        )
        median = index_service.detail("TESTIDX", engine=db)["median"]
        # Of the three real multiples (12, 24, 60) the middle is 24.
        assert median["pe"] == 24.0

    def test_negative_return_on_equity_is_kept(self, db) -> None:
        # Unlike a multiple, a negative return is a real measurement. Dropping
        # it would flatter an index full of loss-makers.
        self._seed(
            db,
            [
                ("LOSSCO", -42.8, 1.0, -15.0, -4807.9),
                ("CHEAPCO", 12.0, 1.5, 18.0, 500.0),
                ("MIDCO", 24.0, 3.0, 4.0, 800.0),
            ],
        )
        median = index_service.detail("TESTIDX", engine=db)["median"]
        assert median["returnonequity"] == 4.0

    def test_an_index_where_nobody_earns_has_no_median_multiple(self, db) -> None:
        self._seed(db, [("A", -10.0, -2.0, -5.0, -100.0), ("B", -20.0, -3.0, -8.0, -200.0)])
        median = index_service.detail("TESTIDX", engine=db)["median"]
        assert median["pe"] is None
        assert median["pb"] is None
        assert median["returnonequity"] is not None

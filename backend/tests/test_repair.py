"""Re-applying normalisation to rows already stored.

Normalisation runs when a row is fetched, so a rule added later never reaches
what came before it - and a long backfill keeps writing with the code it started
with, so a fix landed mid-run misses the rest of that run. Three times this was
patched by hand with ad-hoc SQL; this is the same work, tested.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from app.db.engine import build_engine
from app.db.layer2 import create_layer2
from app.ingest.normalise import normalise_index_quotes, normalise_prices, normalise_quotes
from app.ingest.repair import repair


@pytest.fixture
def db(tmp_path) -> Engine:
    engine = build_engine(tmp_path / "repair.db")
    create_layer2(engine)
    return engine


def _price(db: Engine, symbol: str, date: str, o: float, h: float, low: float, c: float) -> None:
    with db.begin() as conn:
        conn.execute(
            text(
                'INSERT INTO price_daily (symbol, quote_date, "open", high, low, "close", volume)'
                " VALUES (:s, :d, :o, :h, :l, :c, 1000)"
            ),
            {"s": symbol, "d": date, "o": o, "h": h, "l": low, "c": c},
        )


def _rows(db: Engine, sql: str) -> list:
    with db.connect() as conn:
        return conn.execute(text(sql)).all()


def test_a_zero_close_is_removed(db: Engine) -> None:
    # Escorts, Mphasis and Shree Cement each arrived with a real open and a
    # close of zero while the backfill ran on pre-fix code.
    _price(db, "ESCORTS", "2026-08-05", 3137.55, 3140.0, 3100.0, 0.0)
    _price(db, "ESCORTS", "2026-08-06", 3137.55, 3140.0, 3100.0, 3130.0)

    assert repair(db)["price_rows_removed"] == 1
    assert len(_rows(db, "SELECT 1 FROM price_daily")) == 1


def test_negative_history_is_removed(db: Engine) -> None:
    # Adani Green's first sessions carry negative OHLC on real volume.
    _price(db, "ADANIGREEN", "2018-06-28", -11.95, -11.0, -13.8, -11.65)
    assert repair(db)["price_rows_removed"] == 1
    assert _rows(db, "SELECT 1 FROM price_daily") == []


def test_a_real_session_survives(db: Engine) -> None:
    _price(db, "RELIANCE", "2026-08-06", 1283.3, 1325.0, 1282.0, 1325.0)
    repair(db)
    assert len(_rows(db, "SELECT 1 FROM price_daily")) == 1


def test_zero_quote_fields_become_absent(db: Engine) -> None:
    with db.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO quote (symbol, current_price, market_cap, high52, volume,"
                " change_pct, updated_at) VALUES ('CORONA', 0, 12460.7, 0, 0, -100, '')"
            )
        )
    repair(db)
    row = _rows(db, "SELECT current_price, market_cap, high52, volume, change_pct FROM quote")[0]
    assert row.current_price is None
    assert row.market_cap == 12460.7, "a real market cap is not collateral damage"
    assert row.high52 is None
    assert row.volume == 0, "no trades is a fact about the day"
    assert row.change_pct is None, "-100% is computed from the missing price"


def test_index_valuation_zeros_become_absent(db: Engine) -> None:
    with db.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO index_quote_daily (index_symbol, quote_date, close_price,"
                " pe, pb, div_yield, market_cap) VALUES ('INDVIX', '2026-08-06', 12.11, 0, 0, 0, 0)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO index_quote_daily (index_symbol, quote_date, close_price,"
                " pe, pb, div_yield, market_cap)"
                " VALUES ('NIF50', '2026-08-06', 24636.0, 20.91, 3.02, 1.26, 20031898.79)"
            )
        )
    repair(db)
    vix = _rows(
        db,
        "SELECT pe, pb, div_yield, market_cap, close_price FROM index_quote_daily"
        " WHERE index_symbol='INDVIX'",
    )[0]
    assert (vix.pe, vix.pb, vix.div_yield, vix.market_cap) == (None, None, None, None)
    assert vix.close_price == 12.11, "the level itself is real"

    nifty = _rows(db, "SELECT pe, market_cap FROM index_quote_daily WHERE index_symbol='NIF50'")[0]
    assert nifty.pe == 20.91 and nifty.market_cap == 20031898.79


def test_running_it_twice_changes_nothing_the_second_time(db: Engine) -> None:
    _price(db, "ESCORTS", "2026-08-05", 3137.55, 3140.0, 3100.0, 0.0)
    repair(db)
    assert repair(db)["total"] == 0


class TestRepairAgreesWithNormalisation:
    """The two must decide identically, or repair undoes what ingest just did."""

    def test_prices(self) -> None:
        raw = {
            "price": [
                {
                    "quote_date": "2026-08-05",
                    "open_price": 3137.55,
                    "high_price": 3140.0,
                    "low_price": 3100.0,
                    "close_price": 0.0,
                    "volume": 1000,
                },
                {
                    "quote_date": "2018-06-28",
                    "open_price": -11.95,
                    "high_price": -11.0,
                    "low_price": -13.8,
                    "close_price": -11.65,
                    "volume": 1000,
                },
                {
                    "quote_date": "2026-08-06",
                    "open_price": 1283.3,
                    "high_price": 1325.0,
                    "low_price": 1282.0,
                    "close_price": 1325.0,
                    "volume": 1000,
                },
            ]
        }
        kept = normalise_prices("X", raw)
        assert [r["quote_date"] for r in kept] == ["2026-08-06"]

    def test_quotes(self) -> None:
        row = normalise_quotes(
            {
                "X": {
                    "current_price": 0,
                    "market_cap": 12460.7,
                    "high52": 0,
                    "volume": 0,
                    "change": "-100.00%",
                }
            }
        )[0]
        assert row["current_price"] is None
        assert row["market_cap"] == 12460.7
        assert row["high52"] is None
        assert row["volume"] == 0
        assert row["change_pct"] is None

    def test_index_quotes(self) -> None:
        row = normalise_index_quotes(
            [
                {
                    "index_symbol": "INDVIX",
                    "quote_date": "2026-08-06",
                    "close_price": 12.11,
                    "pe": 0,
                    "pb": 0,
                    "div_yield": 0,
                    "market_cap": 0,
                }
            ]
        )[0]
        assert (row["pe"], row["pb"], row["div_yield"], row["market_cap"]) == (None,) * 4
        assert row["close_price"] == 12.11

"""Normalisation tests. Fixtures are real FinEdge payload shapes."""

from __future__ import annotations

from app.ingest.normalise import (
    normalise_index_master,
    normalise_index_quotes,
    normalise_index_returns,
    normalise_prices,
    normalise_profile,
    normalise_quotes,
    normalise_statements,
    normalise_symbols,
    parse_date,
    parse_number,
    parse_percent_string,
)


class TestParseDate:
    def test_iso(self) -> None:
        assert parse_date("2026-08-06") == "2026-08-06"

    def test_compact(self) -> None:
        """period_end arrives as 20260331."""
        assert parse_date("20260331") == "2026-03-31"

    def test_day_month_year(self) -> None:
        """Dividend ex-dates arrive as 27-May-2026."""
        assert parse_date("27-May-2026") == "2026-05-27"

    def test_single_digit_day(self) -> None:
        assert parse_date("7-Aug-2026") == "2026-08-07"

    def test_datetime_is_truncated_to_the_date(self) -> None:
        """Announcements arrive as 2026-08-06 19:27:07."""
        assert parse_date("2026-08-06 19:27:07") == "2026-08-06"

    def test_iso_datetime_with_t_and_zulu(self) -> None:
        assert parse_date("2026-08-06T15:51:08Z") == "2026-08-06"

    def test_unrecognised_returns_none_rather_than_guessing(self) -> None:
        assert parse_date("some day in March") is None

    def test_empty_and_none(self) -> None:
        assert parse_date("") is None
        assert parse_date(None) is None


class TestParseNumber:
    def test_numeric_types(self) -> None:
        assert parse_number(1325) == 1325.0
        assert parse_number(23.98) == 23.98

    def test_missing_is_none_not_zero(self) -> None:
        """A missing figure must never be read as zero on a financial screen."""
        assert parse_number(None) is None
        assert parse_number("") is None
        assert parse_number("-") is None
        assert parse_number("NA") is None

    def test_zero_survives_as_zero(self) -> None:
        assert parse_number(0) == 0.0

    def test_strips_thousands_separators(self) -> None:
        assert parse_number("1,791,661.15") == 1791661.15

    def test_booleans_are_not_numbers(self) -> None:
        assert parse_number(True) is None

    def test_negative(self) -> None:
        assert parse_number(-1141.09) == -1141.09


class TestParsePercentString:
    def test_positive_and_negative(self) -> None:
        assert parse_percent_string("0.28%") == 0.28
        assert parse_percent_string("-0.75%") == -0.75

    def test_flat(self) -> None:
        assert parse_percent_string("0.00%") == 0.0


class TestSymbols:
    PAYLOAD = [
        {
            "symbol": "RELIANCE",
            "nse_code": "RELIANCE",
            "bse_code": "500325",
            "name": "Reliance Industries Ltd",
            "consolidated_ind": True,
        },
        {
            "symbol": "SOMESMALLCO",
            "nse_code": "",
            "bse_code": "500999",
            "name": "Some Small Co Ltd",
            "consolidated_ind": False,
        },
    ]

    def test_maps_identity_fields(self) -> None:
        rows = normalise_symbols(self.PAYLOAD)
        assert len(rows) == 2
        assert rows[0]["symbol"] == "RELIANCE"
        assert rows[0]["consolidated_ind"] is True
        assert rows[1]["consolidated_ind"] is False

    def test_blank_codes_become_none(self) -> None:
        assert normalise_symbols(self.PAYLOAD)[1]["nse_code"] is None

    def test_rows_without_a_symbol_are_dropped(self) -> None:
        assert normalise_symbols([{"name": "No symbol"}]) == []

    def test_non_list_payload(self) -> None:
        assert normalise_symbols({"unexpected": True}) == []


class TestProfile:
    PAYLOAD = {
        "bse_code": "500325",
        "name": "Reliance Industries Ltd",
        "industry": "Petroleum Products",
        "macro_sector": "Energy",
        "sector": "Refineries & Marketing",
        "sub_industry": "Refineries & Marketing",
        "market_cap": 1795091.26,
        "website": "www.ril.com",
        "description": "Reliance Industries Ltd. engages in hydrocarbon exploration",
    }

    def test_keeps_finedge_labels_verbatim(self) -> None:
        row = normalise_profile("RELIANCE", self.PAYLOAD)
        assert row is not None
        assert row["sector_raw"] == "Refineries & Marketing"
        assert row["industry_raw"] == "Petroleum Products"

    def test_normalised_hierarchy_runs_broad_to_narrow(self) -> None:
        """FinEdge's `sector` is narrower than its `industry`, which is inverted."""
        row = normalise_profile("RELIANCE", self.PAYLOAD)
        assert row is not None
        assert row["macro_sector"] == "Energy"
        assert row["industry"] == "Petroleum Products"
        assert row["sector"] == "Refineries & Marketing"

    def test_empty_payload_returns_none(self) -> None:
        assert normalise_profile("X", {}) is None
        assert normalise_profile("X", None) is None


class TestQuotes:
    PAYLOAD = {
        "RELIANCE": {
            "change": "3.43%",
            "current_price": 1325,
            "high52": 1611.2,
            "high_price": 1325,
            "low52": 1250.55,
            "low_price": 1282,
            "market_cap": 1793061.38,
            "open_price": 1283.3,
            "shares": 13532538722,
            "tradetime": "2026-08-06T15:51:08Z",
            "volume": 3185361,
        },
        "EMPTYCO": {},
    }

    def test_maps_every_quote_field(self) -> None:
        rows = normalise_quotes(self.PAYLOAD)
        row = next(r for r in rows if r["symbol"] == "RELIANCE")
        assert row["current_price"] == 1325
        assert row["change_pct"] == 3.43
        assert row["high52"] == 1611.2
        assert row["market_cap"] == 1793061.38

    def test_companies_with_no_quote_are_skipped(self) -> None:
        assert all(r["symbol"] != "EMPTYCO" for r in normalise_quotes(self.PAYLOAD))

    def test_non_dict_payload(self) -> None:
        assert normalise_quotes([1, 2, 3]) == []


class TestStatements:
    GENERAL = {
        "financials": [
            {
                "header": "Mar 2026",
                "year": 2026,
                "period_start": "20250401",
                "period_end": "20260331",
                "result_date": "20260418",
                "income": 11592580000000,
                "revenueFromOperations": 11000000000000,
                "costofGoodsSold": 7473770000000,
                "employeeBenefitExpense": 308030000000,
                "depreciationAndAmortisation": 589460000000,
                "financeCosts": 283620000000,
                "changesInInventories": -73790000000,
                "costOfMaterialsConsumed": 4736760000000,
                "purchasesOfStockInTrade": 100,
                "profitLossForPeriod": 811670000000,
                "eps": 55.22,
            },
            {
                "header": "Mar 2025",
                "year": 2025,
                "period_start": "20240401",
                "period_end": "20250331",
                "income": 10000000000000,
                "revenueFromOperations": 9500000000000,
                "eps": 51.47,
            },
        ]
    }

    BANK = {
        "financials": [
            {
                "header": "Mar 2026",
                "year": 2026,
                "period_end": "20260331",
                "income": 1,
                "interestEarned": 1,
                "interestExpended": 1,
                "interestOrDiscountOnAdvancesOrBills": 1,
                "interestOnBalancesWithRBIAndOthers": 1,
                "provisionsForLoanLoss": 1,
                "expenditureExcludingProvisions": 1,
                "cET1Ratio": 16.8,
                "grossNonPerformingAssets": 1,
                "percentageOfGrossNpa": 1.2,
                "eps": 90.4,
            }
        ]
    }

    def test_classifies_a_general_company(self) -> None:
        periods, _lines, kind = normalise_statements("RELIANCE", "c", "pl", "annual", self.GENERAL)
        assert kind == "general"
        assert all(p["schema_kind"] == "general" for p in periods)

    def test_classifies_a_bank(self) -> None:
        _p, _l, kind = normalise_statements("HDFCBANK", "c", "pl", "annual", self.BANK)
        assert kind == "bank"

    def test_converts_compact_dates(self) -> None:
        periods, _l, _k = normalise_statements("RELIANCE", "c", "pl", "annual", self.GENERAL)
        assert periods[0]["period_end"] == "2026-03-31"
        assert periods[0]["period_start"] == "2025-04-01"
        assert periods[0]["result_date"] == "2026-04-18"

    def test_one_period_row_per_reporting_period(self) -> None:
        periods, lines, _k = normalise_statements("RELIANCE", "c", "pl", "annual", self.GENERAL)
        assert len(periods) == 2
        assert len(lines) == 2

    def test_metadata_keys_are_not_stored_as_financial_lines(self) -> None:
        _p, lines, _k = normalise_statements("RELIANCE", "c", "pl", "annual", self.GENERAL)
        names = {line["field_name"] for line in lines[0]}
        assert "header" not in names
        assert "period_end" not in names
        assert "year" not in names
        assert "income" in names

    def test_classification_uses_all_periods_not_just_the_first(self) -> None:
        """The second period here is sparse; the union still classifies correctly."""
        _p, _l, kind = normalise_statements("RELIANCE", "c", "pl", "annual", self.GENERAL)
        assert kind == "general"

    def test_balance_sheet_is_not_classified_from_pl_markers(self) -> None:
        """Only the P&L carries the family markers."""
        _p, _l, kind = normalise_statements(
            "RELIANCE", "c", "bs", "annual", {"financials": [{"header": "Mar 2026", "assets": 1}]}
        )
        assert kind == "unknown"

    def test_empty_payload(self) -> None:
        assert normalise_statements("X", "c", "pl", "annual", {}) == ([], [], "unknown")

    def test_header_is_derived_when_absent(self) -> None:
        payload = {"financials": [{"period_end": "20260331", "income": 1}]}
        periods, _l, _k = normalise_statements("X", "c", "pl", "annual", payload)
        assert periods[0]["header"] == "Mar 2026"


class TestIndexMaster:
    PAYLOAD = [
        {
            "index_name": "Nifty 50",
            "index_symbol": "NIF50",
            "index_type": "equity",
            "index_sub_type": "Market Cap/Broad",
            "exchange": "NSE",
            "market_cap": 30898050.85,
            "constituents": ["RELIANCE", "HDFCBANK", "TCS"],
        },
        {"index_name": "No constituents", "index_symbol": "EMPTY", "constituents": []},
    ]

    def test_extracts_indices_and_links(self) -> None:
        indices, constituents = normalise_index_master(self.PAYLOAD)
        assert len(indices) == 2
        assert len(constituents) == 3
        assert {"index_symbol": "NIF50", "symbol": "RELIANCE"} in constituents

    def test_index_without_constituents_still_recorded(self) -> None:
        indices, _c = normalise_index_master(self.PAYLOAD)
        assert any(i["index_symbol"] == "EMPTY" for i in indices)


class TestIndexReturns:
    PAYLOAD = [
        {
            "index_symbol": "NIF50",
            "index_name": "Nifty 50",
            "1M": 1.44,
            "3M": 1.87,
            "6M": -1.7,
            "1Y": 2.84,
            "3Y": 9.74,
            "5Y": 9.19,
            "7Y": 12.71,
            "10Y": 11.21,
            "dates": {"last_date": "2026-08-06"},
        },
        {
            "index_symbol": "NEWIDX",
            "index_name": "New Index",
            "1M": 3.21,
            "1Y": 6.05,
            "3Y": 0,
            "5Y": 0,
            "10Y": 0,
            "dates": {"last_date": "2026-08-06"},
        },
    ]

    def test_one_row_per_horizon(self) -> None:
        rows = normalise_index_returns(self.PAYLOAD)
        nifty = [r for r in rows if r["index_symbol"] == "NIF50"]
        assert len(nifty) == 8

    def test_zero_means_the_index_did_not_exist_and_is_dropped(self) -> None:
        rows = normalise_index_returns(self.PAYLOAD)
        new = {r["horizon"] for r in rows if r["index_symbol"] == "NEWIDX"}
        assert new == {"1M", "1Y"}

    def test_negative_returns_are_kept(self) -> None:
        rows = normalise_index_returns(self.PAYLOAD)
        six_month = next(r for r in rows if r["index_symbol"] == "NIF50" and r["horizon"] == "6M")
        assert six_month["return_pct"] == -1.7


class TestPrices:
    PAYLOAD = {
        "symbol": "RELIANCE",
        "price": [
            {
                "quote_date": "2026-08-06",
                "open_price": 1283.3,
                "close_price": 1325,
                "high_price": 1325,
                "low_price": 1282,
                "volume": 3185361,
            }
        ],
    }

    def test_maps_ohlcv(self) -> None:
        rows = normalise_prices("RELIANCE", self.PAYLOAD)
        assert rows[0]["close"] == 1325
        assert rows[0]["open"] == 1283.3
        assert rows[0]["volume"] == 3185361

    def test_empty(self) -> None:
        assert normalise_prices("X", {"symbol": "X", "price": []}) == []


class TestNonTradingRows:
    """FinEdge emits all-zero OHLCV rows for Muhurat and special sessions.

    Stored literally they draw a vertical spike to zero on every price chart,
    and a close of zero is not a price.
    """

    def test_all_zero_row_is_dropped(self) -> None:
        payload = {
            "symbol": "RELIANCE",
            "price": [
                {
                    "quote_date": "2024-11-01",
                    "open_price": 0,
                    "close_price": 0,
                    "high_price": 0,
                    "low_price": 0,
                    "volume": 0,
                },
                {
                    "quote_date": "2024-11-04",
                    "open_price": 1283.3,
                    "close_price": 1325,
                    "high_price": 1325,
                    "low_price": 1282,
                    "volume": 3185361,
                },
            ],
        }
        rows = normalise_prices("RELIANCE", payload)
        assert [r["quote_date"] for r in rows] == ["2024-11-04"]

    def test_a_genuine_zero_volume_day_is_kept(self) -> None:
        """No trades but a carried price is real data, unlike an all-zero row."""
        payload = {
            "symbol": "X",
            "price": [
                {
                    "quote_date": "2024-11-01",
                    "open_price": 100,
                    "close_price": 100,
                    "high_price": 100,
                    "low_price": 100,
                    "volume": 0,
                }
            ],
        }
        assert len(normalise_prices("X", payload)) == 1

    def test_row_of_nulls_is_dropped(self) -> None:
        payload = {
            "symbol": "X",
            "price": [
                {
                    "quote_date": "2024-11-01",
                    "open_price": None,
                    "close_price": None,
                    "high_price": None,
                    "low_price": None,
                    "volume": None,
                }
            ],
        }
        assert normalise_prices("X", payload) == []


class TestIndexQuoteValuation:
    """Upstream sends zeros where an index has no valuation, not nulls."""

    def _quote(self, **over):
        base = {
            "index_symbol": "INDVIX",
            "quote_date": "2026-08-06",
            "close_price": 12.11,
            "pe": 0,
            "pb": 0,
            "div_yield": 0,
        }
        base.update(over)
        return normalise_index_quotes([base])[0]

    def test_zero_pe_and_pb_together_mean_not_published(self):
        # INDIA VIX has no earnings and no book value. Storing 0.0 would put
        # "P/E 0.00" on the page, asserting the index trades at zero times
        # earnings rather than saying the figure does not apply.
        row = self._quote()
        assert row["pe"] is None
        assert row["pb"] is None
        assert row["div_yield"] is None

    def test_the_price_itself_survives(self):
        # VIX has a real level even though it has no valuation ratios.
        assert self._quote()["close_price"] == 12.11

    def test_a_genuine_zero_dividend_yield_is_kept(self):
        # An index of companies that pay nothing really does yield 0%. That is a
        # measurement, and only travels with pe/pb being absent.
        row = self._quote(pe=28.4, pb=3.1, div_yield=0)
        assert row["pe"] == 28.4
        assert row["div_yield"] == 0

    def test_a_real_index_keeps_its_valuation(self):
        row = self._quote(index_symbol="NIF50", pe=20.91, pb=3.02, div_yield=1.26)
        assert (row["pe"], row["pb"], row["div_yield"]) == (20.91, 3.02, 1.26)

    def test_zero_pe_alone_is_not_enough_to_discard(self):
        # Only the pair marks the block absent, so a single odd figure never
        # silently deletes a published book value.
        row = self._quote(pe=0, pb=3.02)
        assert row["pb"] == 3.02


class TestPriceRowsThatAreNotPrices:
    """Rows FinEdge returns that must not be stored as observations."""

    def _payload(self, **over):
        row = {
            "quote_date": "2018-06-28",
            "open_price": 100.0,
            "high_price": 105.0,
            "low_price": 99.0,
            "close_price": 102.0,
            "volume": 1000.0,
        }
        row.update(over)
        return {"price": [row]}

    def test_a_normal_session_is_kept(self):
        assert len(normalise_prices("X", self._payload())) == 1

    def test_an_all_zero_session_is_dropped(self):
        # Diwali Muhurat sessions and special Saturday sittings come back as all
        # zeros. Stored literally they draw a spike to the axis.
        payload = self._payload(open_price=0, high_price=0, low_price=0, close_price=0, volume=0)
        assert normalise_prices("X", payload) == []

    def test_a_negative_close_is_dropped(self):
        # ADANIGREEN's first six sessions in June 2018 come back with every OHLC
        # field below zero, on real volume - the demerger adjustment applied to
        # history from before it listed separately. A share cannot be worth less
        # than nothing.
        payload = self._payload(
            open_price=-11.95, high_price=-11.0, low_price=-13.8, close_price=-11.65
        )
        assert normalise_prices("ADANIGREEN", payload) == []

    def test_a_negative_low_alone_is_dropped(self):
        # A positive close with a negative low is still not a real session.
        payload = self._payload(low_price=-5.0)
        assert normalise_prices("X", payload) == []

    def test_a_zero_volume_session_with_real_prices_is_kept(self):
        # An illiquid day is a real observation: the price stood somewhere even
        # though nothing changed hands. Only the price being absurd disqualifies
        # the row.
        assert len(normalise_prices("X", self._payload(volume=0))) == 1


class TestQuotesThatAreNotQuotes:
    """A share that did not trade has no price, which is not the same as zero."""

    def _payload(self, **over):
        data = {
            "change": "0.00%",
            "current_price": 0,
            "open_price": 0,
            "high_price": 0,
            "low_price": 0,
            "high52": 0,
            "low52": 0,
            "market_cap": 0,
            "shares": 0,
            "volume": 0,
        }
        data.update(over)
        return normalise_quotes({"ILLIQUID": data})[0]

    def test_a_zero_price_is_absent_not_zero(self):
        # Corona Remedies came back at 0.00 against a Rs. 12,461 Cr market cap.
        # Stored as zero it shows Rs. 0.00 on the page and matches a screen for
        # `Current Price < 100`.
        assert self._payload()["current_price"] is None

    def test_a_minus_hundred_change_beside_a_missing_price_is_dropped(self):
        # 59 companies came back at -100%. The change is computed from the price
        # that is missing, so it is not a measurement either.
        assert self._payload(change="-100.00%")["change_pct"] is None

    def test_a_real_minus_hundred_change_is_kept_when_there_is_a_price(self):
        # Guard the rule above: it must key off the missing price, not the number.
        row = self._payload(current_price=5.0, change="-100.00%")
        assert row["current_price"] == 5.0
        assert row["change_pct"] == -100.0

    def test_zero_market_cap_and_share_count_are_absent(self):
        row = self._payload()
        assert row["market_cap"] is None
        assert row["shares"] is None

    def test_zero_volume_survives_as_a_real_observation(self):
        # Nothing changed hands is a fact about the day, unlike a price of zero.
        assert self._payload()["volume"] == 0.0

    def test_a_normal_quote_is_untouched(self):
        row = self._payload(
            current_price=1325, change="3.43%", market_cap=1793061.38, high52=1611.2
        )
        assert row["current_price"] == 1325
        assert row["change_pct"] == 3.43
        assert row["market_cap"] == 1793061.38
        assert row["high52"] == 1611.2

    def test_a_flat_day_keeps_its_zero_change(self):
        # 0% is a measurement: the price did not move.
        assert self._payload(current_price=100, change="0.00%")["change_pct"] == 0.0

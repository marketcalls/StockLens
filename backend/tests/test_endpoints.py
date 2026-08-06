from __future__ import annotations

from app.finedge.endpoints import (
    VALID_PERIODS,
    symbol_endpoint_matrix,
    universe_endpoints,
)


def test_matrix_size_matches_prd_budget() -> None:
    """docs/prd/06 budgets ~63 calls per symbol."""
    calls = symbol_endpoint_matrix("RELIANCE")
    assert 55 <= len(calls) <= 70, f"unexpected matrix size: {len(calls)}"


def test_every_call_is_unique() -> None:
    calls = symbol_endpoint_matrix("RELIANCE")
    assert len({call.key for call in calls}) == len(calls)


def test_symbol_is_interpolated_into_every_path() -> None:
    for call in symbol_endpoint_matrix("TCS"):
        assert "TCS" in call.endpoint
        assert call.symbol == "TCS"


def test_ytd_period_is_never_requested() -> None:
    """The API rejects it: 'combination pl, ytd is invalid'."""
    for call in symbol_endpoint_matrix("RELIANCE"):
        assert call.params.get("period") != "ytd"


def test_ttm_only_requested_for_profit_and_loss() -> None:
    assert "ttm" in VALID_PERIODS["pl"]
    assert "ttm" not in VALID_PERIODS["bs"]
    assert "ttm" not in VALID_PERIODS["cf"]

    for call in symbol_endpoint_matrix("RELIANCE"):
        if call.params.get("period") == "ttm":
            assert call.params.get("statement_code") == "pl"


def test_statement_endpoints_always_carry_required_params() -> None:
    for call in symbol_endpoint_matrix("RELIANCE"):
        if "/financials/" in call.endpoint:
            assert {"statement_type", "statement_code", "period"} <= call.params.keys()
        if "/basic-financials/" in call.endpoint:
            assert {"statement_type", "statement_code"} <= call.params.keys()
        if "/ratios/" in call.endpoint:
            assert {"statement_type", "ratio_type"} <= call.params.keys()
        if "/financial-metrics/" in call.endpoint:
            assert {"statement_type", "ratio_type"} <= call.params.keys()


def test_shareholding_calls_carry_period_where_required() -> None:
    for call in symbol_endpoint_matrix("RELIANCE"):
        if "/shareholdings/" in call.endpoint and "ownership-current" not in call.endpoint:
            assert call.params.get("period") == "quarterly"


def test_universe_quote_call_has_no_symbol() -> None:
    """The whole point: no symbol returns all 5,630 companies in one call."""
    quote = next(c for c in universe_endpoints() if c.endpoint == "/api/v1/quote")
    assert quote.params == {}
    assert quote.symbol is None

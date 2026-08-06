from __future__ import annotations

import httpx
import pytest
import respx

from app.config import get_settings
from app.finedge.client import (
    FinEdgeAuthError,
    FinEdgeClient,
    FinEdgeParameterError,
    FinEdgeUnavailableError,
    redact,
)

BASE = "https://data.finedgeapi.com"


def _client() -> FinEdgeClient:
    settings = get_settings()
    settings.finedge_max_rps = 1000.0  # do not pace the tests
    settings.finedge_max_retries = 2
    return FinEdgeClient(settings)


class TestRedaction:
    def test_redacts_token_in_url(self) -> None:
        url = f"{BASE}/api/v1/quote?symbol=ITC&token=supersecretvalue"
        assert "supersecretvalue" not in redact(url)
        assert "token=REDACTED" in redact(url)

    def test_redacts_token_at_end_of_string(self) -> None:
        assert redact("token=abc123") == "token=REDACTED"

    def test_leaves_other_params_intact(self) -> None:
        out = redact(f"{BASE}/api/v1/quote?symbol=ITC&token=abc&period=annual")
        assert "symbol=ITC" in out
        assert "period=annual" in out

    def test_secret_not_in_settings_repr(self) -> None:
        settings = get_settings()
        assert "test_key_not_a_real_credential" not in repr(settings)


@respx.mock
async def test_get_returns_parsed_payload() -> None:
    respx.get(f"{BASE}/api/v1/quote").mock(
        return_value=httpx.Response(200, json={"ITC": {"current_price": 285}})
    )
    async with _client() as client:
        response = await client.get("/api/v1/quote", symbol="ITC")

    assert response.payload["ITC"]["current_price"] == 285
    assert response.status_code == 200
    assert len(response.content_hash) == 64
    assert client.calls_made == 1


@respx.mock
async def test_token_is_sent_as_query_param() -> None:
    route = respx.get(f"{BASE}/api/v1/quote").mock(return_value=httpx.Response(200, json={}))
    async with _client() as client:
        await client.get("/api/v1/quote")

    assert route.calls.last.request.url.params["token"] == "test_key_not_a_real_credential"


@respx.mock
async def test_none_params_are_dropped() -> None:
    route = respx.get(f"{BASE}/api/v1/quote").mock(return_value=httpx.Response(200, json={}))
    async with _client() as client:
        response = await client.get("/api/v1/quote", symbol=None, period="annual")

    assert "symbol" not in route.calls.last.request.url.params
    assert response.params == {"period": "annual"}


@respx.mock
async def test_401_raises_auth_error_without_leaking_token() -> None:
    respx.get(f"{BASE}/api/v1/quote").mock(
        return_value=httpx.Response(401, text="ER006 - missing or invalid token")
    )
    async with _client() as client:
        with pytest.raises(FinEdgeAuthError) as exc:
            await client.get("/api/v1/quote")

    assert "test_key_not_a_real_credential" not in str(exc.value)


@respx.mock
async def test_400_raises_parameter_error_and_does_not_retry() -> None:
    route = respx.get(f"{BASE}/api/v1/financials/RELIANCE").mock(
        return_value=httpx.Response(400, text="statement type selection is emtpy or invalid")
    )
    async with _client() as client:
        with pytest.raises(FinEdgeParameterError):
            await client.get("/api/v1/financials/RELIANCE")

    assert route.call_count == 1


@respx.mock
async def test_503_is_retried_then_succeeds() -> None:
    route = respx.get(f"{BASE}/api/v1/commodity-list").mock(
        side_effect=[
            httpx.Response(503, text="Service Temporarily Unavailable"),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    async with _client() as client:
        response = await client.get("/api/v1/commodity-list")

    assert response.payload == {"ok": True}
    assert route.call_count == 2


@respx.mock
async def test_retry_budget_is_exhausted() -> None:
    respx.get(f"{BASE}/api/v1/name-changes").mock(return_value=httpx.Response(503))
    async with _client() as client:
        with pytest.raises(FinEdgeUnavailableError):
            await client.get("/api/v1/name-changes")


@respx.mock
async def test_non_json_response_is_wrapped_not_raised() -> None:
    respx.get(f"{BASE}/api/v1/quote").mock(return_value=httpx.Response(200, text="not json"))
    async with _client() as client:
        response = await client.get("/api/v1/quote")

    assert response.payload == {"_raw_text": "not json"}


async def test_missing_key_raises_before_any_request() -> None:
    settings = get_settings()
    settings.finedge_api_key = type(settings.finedge_api_key)("")
    async with FinEdgeClient(settings) as client:
        with pytest.raises(FinEdgeAuthError):
            await client.get("/api/v1/quote")

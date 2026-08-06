"""Rate limiting and hardening.

The suite turns limiting off globally (see conftest), so these tests switch it
back on deliberately.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.security.middleware import MAX_BODY_BYTES
from app.security.ratelimit import (
    AUTH,
    READ,
    SCREENER,
    Rule,
    SlidingWindowLimiter,
    limiter,
)


@pytest.fixture
def limited(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    get_settings.cache_clear()
    limiter.reset()
    with TestClient(create_app()) as client:
        yield client
    limiter.reset()
    get_settings.cache_clear()


@pytest.fixture
def unlimited() -> TestClient:
    with TestClient(create_app()) as client:
        yield client


class TestSlidingWindow:
    def test_allows_up_to_the_limit(self) -> None:
        window = SlidingWindowLimiter()
        rule = Rule(3, 60, "t")
        for _ in range(3):
            allowed, _remaining, _retry = window.check("k", rule, now=100.0)
            assert allowed

    def test_refuses_beyond_the_limit(self) -> None:
        window = SlidingWindowLimiter()
        rule = Rule(2, 60, "t")
        window.check("k", rule, now=100.0)
        window.check("k", rule, now=100.0)
        allowed, remaining, retry = window.check("k", rule, now=100.0)
        assert not allowed
        assert remaining == 0
        assert retry == pytest.approx(60.0)

    def test_the_window_slides_rather_than_resetting_on_a_boundary(self) -> None:
        """A fixed bucket would allow 2x the limit across a boundary."""
        window = SlidingWindowLimiter()
        rule = Rule(2, 60, "t")
        window.check("k", rule, now=0.0)
        window.check("k", rule, now=59.0)
        assert not window.check("k", rule, now=59.5)[0]
        # The first hit ages out at t=60, freeing exactly one slot.
        assert window.check("k", rule, now=60.5)[0]
        assert not window.check("k", rule, now=60.6)[0]

    def test_keys_are_counted_separately(self) -> None:
        window = SlidingWindowLimiter()
        rule = Rule(1, 60, "t")
        assert window.check("a", rule, now=0.0)[0]
        assert window.check("b", rule, now=0.0)[0]
        assert not window.check("a", rule, now=0.0)[0]

    def test_remaining_counts_down(self) -> None:
        window = SlidingWindowLimiter()
        rule = Rule(3, 60, "t")
        assert window.check("k", rule, now=0.0)[1] == 2
        assert window.check("k", rule, now=0.0)[1] == 1
        assert window.check("k", rule, now=0.0)[1] == 0

    def test_empty_buckets_are_swept(self) -> None:
        window = SlidingWindowLimiter()
        rule = Rule(5, 10, "t")
        for i in range(50):
            window.check(f"key{i}", rule, now=0.0)
        assert window.tracked_keys == 50
        # A sweep runs at most every 5 minutes; by then the hits have aged out.
        window.check("trigger", rule, now=400.0)
        assert window.tracked_keys < 50

    def test_rule_descriptions_read_naturally(self) -> None:
        assert Rule(10, 60).description == "10 per minute"
        assert Rule(5, 3600).description == "5 per hour"
        assert Rule(20, 86400).description == "20 per day"


class TestEnforcement:
    def test_a_burst_is_refused_with_429(self, limited: TestClient) -> None:
        statuses = [
            limited.post(
                "/api/screener/run", json={"query": "Market Capitalization > 0"}
            ).status_code
            for _ in range(SCREENER.limit + 3)
        ]
        assert 429 in statuses
        assert statuses.count(200) <= SCREENER.limit

    def test_the_refusal_says_what_the_limit_is(self, limited: TestClient) -> None:
        for _ in range(SCREENER.limit + 1):
            response = limited.post(
                "/api/screener/run", json={"query": "Market Capitalization > 0"}
            )
        assert response.status_code == 429
        assert "per minute" in response.json()["detail"]
        assert "Retry-After" in response.headers

    def test_login_is_limited_far_more_tightly_than_reading(self) -> None:
        """Credential stuffing is the threat; browsing is not."""
        assert AUTH.limit < READ.limit
        assert AUTH.window > READ.window

    def test_repeated_failed_logins_are_cut_off(self, limited: TestClient) -> None:
        statuses = [
            limited.post(
                "/api/auth/login", json={"email": "a@b.com", "password": "wrong password"}
            ).status_code
            for _ in range(AUTH.limit + 2)
        ]
        assert statuses[-1] == 429

    def test_limiting_can_be_switched_off(self, unlimited: TestClient) -> None:
        statuses = [
            unlimited.post(
                "/api/screener/run", json={"query": "Market Capitalization > 0"}
            ).status_code
            for _ in range(SCREENER.limit + 5)
        ]
        assert 429 not in statuses


class TestProxyHeaders:
    def test_forwarded_headers_are_ignored_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Otherwise anyone can mint a fresh identity per request."""
        from app.security.ratelimit import client_ip

        monkeypatch.setenv("TRUST_PROXY_HEADERS", "false")
        get_settings.cache_clear()

        class FakeRequest:
            headers = {"x-forwarded-for": "1.2.3.4"}
            client = type("C", (), {"host": "10.0.0.1"})()

        assert client_ip(FakeRequest()) == "10.0.0.1"  # type: ignore[arg-type]
        get_settings.cache_clear()

    def test_forwarded_headers_are_used_when_trusted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.security.ratelimit import client_ip

        monkeypatch.setenv("TRUST_PROXY_HEADERS", "true")
        get_settings.cache_clear()

        class FakeRequest:
            headers = {"x-forwarded-for": "1.2.3.4, 5.6.7.8"}
            client = type("C", (), {"host": "10.0.0.1"})()

        assert client_ip(FakeRequest()) == "1.2.3.4"  # type: ignore[arg-type]
        get_settings.cache_clear()


class TestSecurityHeaders:
    def test_the_standard_headers_are_present(self, unlimited: TestClient) -> None:
        headers = unlimited.get("/").headers
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"] == "DENY"
        assert headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "geolocation=()" in headers["Permissions-Policy"]

    def test_a_strict_policy_applies_outside_plain_http(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("JWT_SECRET", "x" * 48)
        get_settings.cache_clear()
        with TestClient(create_app()) as client:
            headers = client.get("/").headers
        assert "script-src 'self'" in headers["Content-Security-Policy"]
        assert "'unsafe-eval'" not in headers["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
        assert "Strict-Transport-Security" in headers
        get_settings.cache_clear()

    def test_no_strict_transport_over_plain_http(self, unlimited: TestClient) -> None:
        """Sending HSTS from a development server would pin it in the browser."""
        assert "Strict-Transport-Security" not in unlimited.get("/").headers


class TestBodySize:
    def test_an_oversized_body_is_refused_before_it_is_read(self, unlimited: TestClient) -> None:
        response = unlimited.post(
            "/api/screener/run",
            content=b"x" * 16,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(MAX_BODY_BYTES + 1),
            },
        )
        assert response.status_code == 413

    def test_a_normal_body_passes(self, unlimited: TestClient) -> None:
        response = unlimited.post("/api/screener/run", json={"query": "PE < 20"})
        assert response.status_code in (200, 400)

    def test_the_query_length_is_capped_by_the_schema(self, unlimited: TestClient) -> None:
        response = unlimited.post("/api/screener/run", json={"query": "x" * 5000})
        assert response.status_code == 422

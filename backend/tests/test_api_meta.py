from __future__ import annotations

import httpx
import respx
from fastapi.testclient import TestClient

from app.main import create_app

BASE = "https://data.finedgeapi.com"


def _client() -> TestClient:
    return TestClient(create_app())


def test_root_returns_service_identity() -> None:
    with _client() as client:
        body = client.get("/").json()
    assert body["name"] == "StockLens"


def test_health_checks_the_database() -> None:
    """The dependency whose loss breaks every read is the one worth reporting."""
    with _client() as client:
        response = client.get("/api/meta/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"]["reachable"] is True
    assert body["database"]["error"] is None


def test_health_reports_degraded_and_503_when_the_database_is_gone(monkeypatch) -> None:
    """A healthcheck that says "ok" while the database is unreachable is worse
    than no healthcheck: an orchestrator keeps routing traffic to a dead node."""
    import app.api.meta as meta

    def broken() -> None:
        raise RuntimeError("unable to open database file")

    monkeypatch.setattr(meta, "get_engine", broken)

    with _client() as client:
        response = client.get("/api/meta/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["database"]["reachable"] is False
    assert "unable to open database file" in body["database"]["error"]


@respx.mock
def test_health_does_not_call_finedge_by_default() -> None:
    """Polled every few seconds by a container runtime, a default FinEdge probe
    would hammer a third party for no benefit.

    The mock raises, so if the route called it at all this test fails rather than
    passing on a response that merely looks right.
    """
    route = respx.get(f"{BASE}/healthcheck").mock(
        side_effect=AssertionError("health must not call FinEdge unless asked")
    )

    with _client() as client:
        response = client.get("/api/meta/health")

    assert response.status_code == 200
    assert route.call_count == 0
    body = response.json()
    assert body["finedge"]["checked"] is False
    assert body["finedge"]["key_configured"] is True
    assert "reachable" not in body["finedge"]


@respx.mock
def test_health_reports_finedge_reachable_when_asked() -> None:
    route = respx.get(f"{BASE}/healthcheck").mock(return_value=httpx.Response(200))

    with _client() as client:
        body = client.get("/api/meta/health?finedge=true").json()

    assert route.call_count == 1
    assert body["status"] == "ok"
    assert body["finedge"]["reachable"] is True
    assert body["finedge"]["key_configured"] is True


@respx.mock
def test_health_reports_finedge_unreachable_without_failing() -> None:
    """FinEdge being down does not stop us serving data we already hold."""
    respx.get(f"{BASE}/healthcheck").mock(side_effect=httpx.ConnectError("down"))

    with _client() as client:
        response = client.get("/api/meta/health?finedge=true")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["finedge"]["reachable"] is False


@respx.mock
def test_health_never_returns_the_key() -> None:
    respx.get(f"{BASE}/healthcheck").mock(return_value=httpx.Response(200))
    with _client() as client:
        body = client.get("/api/meta/health?finedge=true").text
    assert "test_key_not_a_real_credential" not in body


def test_freshness_on_empty_database() -> None:
    with _client() as client:
        body = client.get("/api/meta/freshness").json()

    assert body["raw"]["raw_responses"] == 0
    assert body["recent_runs"] == []

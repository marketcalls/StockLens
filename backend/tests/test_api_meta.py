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


@respx.mock
def test_health_reports_finedge_reachable() -> None:
    respx.get(f"{BASE}/healthcheck").mock(return_value=httpx.Response(200))
    with _client() as client:
        body = client.get("/api/meta/health").json()

    assert body["status"] == "ok"
    assert body["finedge"]["reachable"] is True
    assert body["finedge"]["key_configured"] is True


@respx.mock
def test_health_reports_finedge_unreachable_without_failing() -> None:
    respx.get(f"{BASE}/healthcheck").mock(side_effect=httpx.ConnectError("down"))
    with _client() as client:
        response = client.get("/api/meta/health")

    assert response.status_code == 200
    assert response.json()["finedge"]["reachable"] is False


@respx.mock
def test_health_never_returns_the_key() -> None:
    respx.get(f"{BASE}/healthcheck").mock(return_value=httpx.Response(200))
    with _client() as client:
        body = client.get("/api/meta/health").text
    assert "test_key_not_a_real_credential" not in body


def test_freshness_on_empty_database() -> None:
    with _client() as client:
        body = client.get("/api/meta/freshness").json()

    assert body["raw"]["raw_responses"] == 0
    assert body["recent_runs"] == []

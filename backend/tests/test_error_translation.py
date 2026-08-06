"""How domain errors reach an HTTP caller.

The service layer raises ServiceError subclasses with context attached; only
app/api/_translate.py knows about status codes. These tests pin the wire shape,
because both the query editor and any programmatic caller depend on it.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_not_found_carries_machine_readable_context() -> None:
    """`detail` is a sentence for a person; the context keys are for a program.

    An agent handling a miss should not have to parse the symbol back out of an
    English sentence.
    """
    with _client() as client:
        response = client.get("/api/companies/NOSUCHSYMBOL")

    assert response.status_code == 404
    body = response.json()
    assert isinstance(body["detail"], str)
    assert body["symbol"] == "NOSUCHSYMBOL"


def test_unknown_index_reports_which_index() -> None:
    with _client() as client:
        response = client.get("/api/indices/NOSUCHINDEX")

    assert response.status_code == 404
    assert response.json()["index"] == "NOSUCHINDEX"


def test_query_error_keeps_the_nested_shape_the_editor_reads() -> None:
    """frontend/src/lib/api.ts reads detail.message and detail.position.

    Flattening this would silently stop the editor underlining the fault, so the
    shape is pinned rather than left to convention.
    """
    with _client() as client:
        response = client.post(
            "/api/screener/run",
            json={"query": "Price to Earning < 20 AND Bogus Column > 1"},
        )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert isinstance(detail, dict)
    assert "Bogus" in detail["message"]
    assert detail["position"] == 26


def test_context_omits_empty_values() -> None:
    """A null in the body invites a caller to treat it as meaningful."""
    with _client() as client:
        body = client.get("/api/companies/NOSUCHSYMBOL").json()

    assert all(value is not None for value in body.values())

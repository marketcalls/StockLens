"""Keep docs/API.md honest about what the API actually exposes.

Documentation drifts silently: nothing fails when a route is added and the page
is not updated, and a reader has no way to tell. These tests fail instead.

They deliberately check only the things a reader would act on - that every route
is mentioned, and that field names in the prose are the field names in the
response. Prose is not asserted on.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.main import create_app

DOCS = Path(__file__).resolve().parents[2] / "docs"


@pytest.fixture(scope="module")
def api_doc() -> str:
    return (DOCS / "API.md").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def routes() -> list[str]:
    spec = create_app().openapi()
    return [p for p in spec["paths"] if p.startswith("/api")]


def _normalise(path: str) -> str:
    """Collapse path parameter names so {id} and {screen_id} compare equal."""
    return re.sub(r"\{[^}]+\}", "{}", path)


def test_every_route_is_documented(api_doc: str, routes: list[str]) -> None:
    documented = {_normalise(m) for m in re.findall(r"/api/[\w/{}\-]+", api_doc)}
    missing = sorted(p for p in routes if _normalise(p) not in documented)
    assert not missing, f"routes missing from docs/API.md: {missing}"


def test_the_stated_endpoint_count_is_right(api_doc: str, routes: list[str]) -> None:
    spec = create_app().openapi()
    live = sum(
        1
        for path, ops in spec["paths"].items()
        if path.startswith("/api")
        for method in ops
        if method in {"get", "post", "put", "patch", "delete"}
    )
    claimed = int(re.search(r"^(\d+) endpoints under", api_doc, re.MULTILINE).group(1))
    assert claimed == live, f"docs say {claimed} endpoints, the app serves {live}"


def test_documented_statement_fields_are_the_real_ones(api_doc: str, engines) -> None:
    """Field names in the prose must be the field names in the response.

    The page once told readers a statement response carries `family`. The field
    is `schema_kind`, so anyone following the doc read None and had no way to
    know why.
    """
    from sqlalchemy import text

    from app.db.layer2 import create_layer2
    from app.services import company

    engine = engines[0]
    create_layer2(engine)
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO company (symbol, name, updated_at) VALUES ('DOCS', 'Docs Co', '')")
        )

    # A company with no statements yet still returns the response envelope,
    # which is what a reader needs the field names of.
    envelope = set(company.statements("DOCS", engine=engine).keys())

    for field in ("schema_kind", "statement_type", "available"):
        assert field in api_doc, f"docs/API.md should name {field}"
        assert field in envelope, f"docs name {field}, but the response has {sorted(envelope)}"

    assert "`family`" not in api_doc, "there is no `family` field on a statement response"


def test_the_statement_envelope_does_not_change_shape_with_the_data(engines) -> None:
    """A response's keys must not depend on whether there is data in it.

    The no-data branch used to omit schema_kind, result_dates and unit_note, so
    a caller reading any of them hit a KeyError for whichever companies happened
    not to be backfilled yet - which is most of them, most of the time.
    """
    from sqlalchemy import text

    from app.db.layer2 import create_layer2
    from app.services import company

    engine = engines[0]
    create_layer2(engine)
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO company (symbol, name, updated_at) VALUES ('EMPTY', 'Empty Co', '')")
        )

    empty = company.statements("EMPTY", engine=engine)
    assert empty["available"] is False
    for field in ("schema_kind", "statement_type", "headers", "result_dates", "rows", "unit_note"):
        assert field in empty, f"the no-data branch dropped {field}"
    assert empty["schema_kind"] is None
    assert empty["rows"] == []

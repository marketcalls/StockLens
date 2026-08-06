"""Regression tests for credential leakage into logs.

The first live run of the ingestion worker printed the FinEdge token in full,
because httpx logs the request URL at INFO level and only our own log calls were
being redacted. These tests pin the fix.
"""

from __future__ import annotations

import io
import logging

import httpx
import respx

from app.config import get_settings
from app.finedge.client import FinEdgeClient
from app.logging_setup import RedactingFilter, configure_logging

BASE = "https://data.finedgeapi.com"
SECRET = "test_key_not_a_real_credential"


class TestRedactingFilter:
    def test_scrubs_the_message(self) -> None:
        record = logging.LogRecord(
            "httpx",
            logging.INFO,
            __file__,
            1,
            f"HTTP Request: GET {BASE}/api/v1/quote?token={SECRET} 200 OK",
            None,
            None,
        )
        RedactingFilter().filter(record)
        assert SECRET not in record.getMessage()
        assert "token=REDACTED" in record.getMessage()

    def test_scrubs_tuple_args(self) -> None:
        record = logging.LogRecord(
            "httpx",
            logging.INFO,
            __file__,
            1,
            "url=%s status=%d",
            (f"{BASE}/api/v1/quote?token={SECRET}", 200),
            None,
        )
        RedactingFilter().filter(record)
        assert SECRET not in record.getMessage()

    def test_scrubs_dict_args(self) -> None:
        # logging unwraps a single-mapping tuple into record.args, which is how
        # `logger.info("%(url)s", {"url": ...})` actually reaches a filter.
        record = logging.LogRecord(
            "httpx",
            logging.INFO,
            __file__,
            1,
            "url=%(url)s",
            ({"url": f"{BASE}?token={SECRET}"},),
            None,
        )
        assert isinstance(record.args, dict)
        RedactingFilter().filter(record)
        assert SECRET not in record.getMessage()

    def test_never_drops_records(self) -> None:
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "harmless", None, None)
        assert RedactingFilter().filter(record) is True


def test_scrubs_non_string_url_objects() -> None:
    """httpx logs `request.url` as an httpx.URL, not a str.

    This is the exact shape that leaked the key on the first verbose run.
    """
    url = httpx.URL(f"{BASE}/api/v1/quote?symbol=ITC&token={SECRET}")
    record = logging.LogRecord(
        "httpx",
        logging.INFO,
        __file__,
        1,
        'HTTP Request: %s %s "%s %d %s"',
        ("GET", url, "HTTP/1.1", 200, "OK"),
        None,
    )
    RedactingFilter().filter(record)
    message = record.getMessage()
    assert SECRET not in message
    assert "token=REDACTED" in message
    assert "200" in message  # the %d arg still formats


def test_numeric_args_survive_scrubbing() -> None:
    record = logging.LogRecord(
        "x",
        logging.INFO,
        __file__,
        1,
        "count=%d ratio=%.2f flag=%s",
        (7, 1.5, True),
        None,
    )
    RedactingFilter().filter(record)
    assert record.getMessage() == "count=7 ratio=1.50 flag=True"


@respx.mock
async def test_real_client_call_does_not_leak_token_to_a_handler() -> None:
    """End-to-end: drive the client and read what a production handler emits.

    caplog cannot be used here: configure_logging replaces the root handlers,
    which removes caplog's own handler and makes the assertion vacuous. That is
    how the first version of this test passed while the leak was still live.
    """
    configure_logging(level=logging.INFO, quiet_httpx=False)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RedactingFilter())
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger().addHandler(handler)

    respx.get(f"{BASE}/api/v1/quote").mock(return_value=httpx.Response(200, json={}))
    settings = get_settings()
    settings.finedge_max_rps = 1000.0

    try:
        async with FinEdgeClient(settings) as client:
            await client.get("/api/v1/quote", symbol="ITC")
    finally:
        logging.getLogger().removeHandler(handler)

    output = stream.getvalue()
    assert "HTTP Request" in output, "httpx did not log; the test would be vacuous"
    assert SECRET not in output


def test_configure_logging_quiets_httpx_by_default() -> None:
    configure_logging(level=logging.INFO)
    assert logging.getLogger("httpx").level == logging.WARNING


def test_configure_logging_attaches_filter_to_root_handler() -> None:
    configure_logging(level=logging.INFO)
    root = logging.getLogger()
    assert root.handlers
    assert any(isinstance(f, RedactingFilter) for f in root.handlers[0].filters)


def test_configure_logging_replaces_handlers_rather_than_stacking() -> None:
    configure_logging(level=logging.INFO)
    configure_logging(level=logging.INFO)
    assert len(logging.getLogger().handlers) == 1

"""Logging configuration with credential redaction.

The FinEdge token travels as a query parameter, so any library that logs a
request URL will log the credential. httpx does exactly that at INFO level.
Redacting only our own log calls is not enough: the filter below is attached to
the root logger so every record from every library is scrubbed.
"""

from __future__ import annotations

import logging

from app.finedge.client import redact


def _scrub(value: object) -> object:
    """Redact a single log argument.

    Strings are redacted directly. Non-strings are only touched when their text
    form carries a token, in which case the redacted string is substituted -
    httpx logs `request.url` as an `httpx.URL` object, not a str, so checking
    only for `str` lets the credential straight through. Values without a token
    are returned unchanged so that `%d` and friends still format correctly.
    """
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, bool | int | float) or value is None:
        return value
    text = str(value)
    return redact(text) if "token=" in text else value


class RedactingFilter(logging.Filter):
    """Scrub token values from a record's message and arguments.

    Returns True always: this filter rewrites records, it does not drop them.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        elif "token=" in str(record.msg):
            record.msg = redact(str(record.msg))
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: _scrub(v) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(_scrub(a) for a in record.args)
        return True


def configure_logging(level: int = logging.INFO, *, quiet_httpx: bool = True) -> None:
    """Install a redacting root handler.

    `quiet_httpx` raises httpx's own logger to WARNING. The redaction filter
    already makes its output safe, but its per-request INFO lines duplicate ours.
    """
    root = logging.getLogger()
    root.setLevel(level)

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    handler.addFilter(RedactingFilter())

    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)

    # Belt and braces: filter at the logger level too, so a handler added later
    # by another library still receives scrubbed records.
    for name in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(name).addFilter(RedactingFilter())

    # Set the level explicitly in both directions. Leaving it alone when
    # quiet_httpx is False would let an earlier quiet call stick, so `-v` would
    # silently fail to surface the request lines it promises.
    http_level = logging.WARNING if quiet_httpx else logging.NOTSET
    logging.getLogger("httpx").setLevel(http_level)
    logging.getLogger("httpcore").setLevel(http_level)

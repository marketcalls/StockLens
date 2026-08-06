"""Keep warnings and errors where an operator can read them.

A self-hosted install is usually a container with no one watching stdout. This
writes WARNING and above to the database, with the traceback when there is one,
so the diagnostics page can show what went wrong without shell access.

Two things matter more than the feature:

- **The FinEdge token must never land here.** It travels as a query parameter,
  so any library logging a request URL logs the credential. The redaction filter
  is attached to this handler explicitly; attaching it to the root logger is not
  enough, because filters on a logger do not run for handlers added elsewhere.
- **Logging must never break the app.** A handler that raises turns a warning
  into a crash, so every failure here is swallowed.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, delete, desc, func, select

from app.db.models import log_record
from app.finedge.client import redact
from app.logging_setup import RedactingFilter, RedactingFormatter

# Rows kept. Old ones are trimmed as new ones arrive, so the table cannot grow
# without bound on a long-running instance.
LOG_RETENTION = 2000

# How many inserts between trims. Trimming on every record would double the
# write cost of logging.
TRIM_EVERY = 50

MESSAGE_LIMIT = 4000
TRACEBACK_LIMIT = 16000


class DatabaseLogHandler(logging.Handler):
    """Write records to `log_record`, redacted, never raising."""

    def __init__(self, engine: Engine, level: int = logging.WARNING) -> None:
        super().__init__(level)
        self._engine = engine
        self._since_trim = 0
        self._lock = threading.Lock()
        # Explicit: this handler is not covered by the root handler's filter.
        self.addFilter(RedactingFilter())

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # Redact the FORMATTED text, not just the record. The filter sees
            # the template and the arguments separately, so `log("...token=%s",
            # key)` has no `token=` anywhere for it to match until the two are
            # joined. And a traceback is rendered from exc_info without passing
            # through any filter at all, while carrying the URL of the call that
            # failed.
            message = redact(self.format(record))[:MESSAGE_LIMIT]
            trace = None
            if record.exc_info:
                rendered = logging.Formatter().formatException(record.exc_info)
                trace = redact(rendered)[:TRACEBACK_LIMIT]

            with self._engine.begin() as conn:
                conn.execute(
                    log_record.insert().values(
                        created_at=datetime.now(UTC).isoformat(),
                        level=record.levelname,
                        logger=record.name,
                        message=message,
                        traceback=trace,
                        path=getattr(record, "request_path", None),
                        method=getattr(record, "request_method", None),
                        status=getattr(record, "response_status", None),
                        actor_id=getattr(record, "actor_id", None),
                    )
                )
            self._maybe_trim()
        except Exception:  # noqa: BLE001 - logging must not be able to break the app
            self.handleError(record)

    def _maybe_trim(self) -> None:
        with self._lock:
            self._since_trim += 1
            if self._since_trim < TRIM_EVERY:
                return
            self._since_trim = 0
        with contextlib.suppress(Exception):
            trim(self._engine)


def trim(engine: Engine, keep: int = LOG_RETENTION) -> int:
    """Drop the oldest records beyond `keep`. Returns how many went."""
    with engine.begin() as conn:
        total = conn.execute(select(func.count()).select_from(log_record)).scalar_one()
        if total <= keep:
            return 0
        cutoff = conn.execute(
            select(log_record.c.id).order_by(desc(log_record.c.id)).limit(1).offset(keep - 1)
        ).scalar_one()
        return conn.execute(delete(log_record).where(log_record.c.id < cutoff)).rowcount


def install(engine: Engine, level: int = logging.WARNING) -> DatabaseLogHandler:
    """Attach the handler to the root logger, replacing any earlier one."""
    root = logging.getLogger()
    for existing in list(root.handlers):
        if isinstance(existing, DatabaseLogHandler):
            root.removeHandler(existing)
    handler = DatabaseLogHandler(engine, level)
    handler.setFormatter(RedactingFormatter("%(message)s"))
    root.addHandler(handler)
    return handler


def context(
    *,
    path: str | None = None,
    method: str | None = None,
    status: int | None = None,
    actor_id: int | None = None,
) -> dict[str, Any]:
    """Extra fields for a log call, so a record can be tied to a request."""
    return {
        "request_path": path,
        "request_method": method,
        "response_status": status,
        "actor_id": actor_id,
    }

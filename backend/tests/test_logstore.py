"""Warnings and errors kept in the database.

The overriding requirement is that the FinEdge token never lands here. It
travels as a query parameter, so any library that logs a request URL logs the
credential - and this table is readable through the diagnostics page.
"""

from __future__ import annotations

import logging

import pytest
from sqlalchemy import Engine, func, select

from app.db.engine import build_engine
from app.db.models import create_all, log_record
from app.logging_setup import RedactingFormatter
from app.logstore import LOG_RETENTION, DatabaseLogHandler, context, trim

SECRET = "sk_live_not_a_real_credential_1234567890"


@pytest.fixture
def db(tmp_path) -> Engine:
    engine = build_engine(tmp_path / "logs.db")
    create_all(engine, build_engine(tmp_path / "raw.db"))
    return engine


@pytest.fixture
def log(db: Engine):
    """A logger wired only to the database handler, isolated from the root."""
    handler = DatabaseLogHandler(db, level=logging.WARNING)
    handler.setFormatter(RedactingFormatter("%(message)s"))
    logger = logging.getLogger(f"stocklens.test.{id(handler)}")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    return logger


def _rows(db: Engine) -> list:
    with db.connect() as conn:
        return conn.execute(select(log_record)).mappings().all()


class TestTheKeyNeverLands:
    def test_a_token_in_the_message_is_redacted(self, db: Engine, log) -> None:
        log.error("calling https://data.finedgeapi.com/quote?token=%s", SECRET)
        stored = _rows(db)[0]["message"]
        assert SECRET not in stored
        assert "token=" in stored, "the shape is kept so the log still reads sensibly"

    def test_a_token_in_an_argument_is_redacted(self, db: Engine, log) -> None:
        log.warning("url %s", f"https://data.finedgeapi.com/x?token={SECRET}")
        assert SECRET not in _rows(db)[0]["message"]

    def test_a_token_inside_a_traceback_is_redacted(self, db: Engine, log) -> None:
        # The traceback is stored in its own column, which the message filter
        # does not touch. Its text can carry the URL from the failing call.
        try:
            raise RuntimeError(f"GET https://data.finedgeapi.com/x?token={SECRET} failed")
        except RuntimeError:
            log.exception("request failed")

        row = _rows(db)[0]
        assert row["traceback"], "the traceback is what makes the record useful"
        assert SECRET not in row["traceback"]
        assert SECRET not in str(dict(row))

    def test_a_non_string_carrying_a_token_is_redacted(self, db: Engine, log) -> None:
        # httpx logs request.url as an httpx.URL, not a str.
        class Url:
            def __str__(self) -> str:
                return f"https://data.finedgeapi.com/x?token={SECRET}"

        log.warning("requesting %s", Url())
        assert SECRET not in _rows(db)[0]["message"]


class TestWhatIsKept:
    def test_info_is_not_stored(self, db: Engine, log) -> None:
        # Storing every info line would fill the table with routine chatter.
        log.info("routine")
        assert _rows(db) == []

    def test_a_warning_is_stored_with_its_logger(self, db: Engine, log) -> None:
        log.warning("something looks wrong")
        row = _rows(db)[0]
        assert row["level"] == "WARNING"
        assert row["message"] == "something looks wrong"
        assert row["logger"].startswith("stocklens.test")

    def test_an_exception_keeps_its_traceback(self, db: Engine, log) -> None:
        try:
            _ = 1 / 0
        except ZeroDivisionError:
            log.exception("materialise failed")
        row = _rows(db)[0]
        assert "ZeroDivisionError" in row["traceback"]
        assert "division by zero" in row["traceback"]

    def test_request_context_is_recorded_when_given(self, db: Engine, log) -> None:
        log.error(
            "boom", extra=context(path="/api/screener/run", method="POST", status=500, actor_id=7)
        )
        row = _rows(db)[0]
        assert (row["path"], row["method"], row["status"], row["actor_id"]) == (
            "/api/screener/run",
            "POST",
            500,
            7,
        )

    def test_a_background_job_has_no_request_context(self, db: Engine, log) -> None:
        log.warning("backfill retried")
        row = _rows(db)[0]
        assert row["path"] is None and row["method"] is None


class TestItCannotBreakTheApp:
    def test_a_broken_database_does_not_raise(self, tmp_path) -> None:
        # A handler that raises turns a warning into a crash.
        engine = build_engine(tmp_path / "no-tables.db")  # log_record never created
        handler = DatabaseLogHandler(engine)
        handler.setFormatter(RedactingFormatter("%(message)s"))
        logger = logging.getLogger("stocklens.test.broken")
        logger.handlers = [handler]
        logger.propagate = False

        logging.raiseExceptions = False
        try:
            logger.error("this must not explode")
        finally:
            logging.raiseExceptions = True

    def test_the_table_does_not_grow_without_bound(self, db: Engine, log) -> None:
        with db.begin() as conn:
            conn.execute(
                log_record.insert(),
                [
                    {
                        "created_at": "2026-08-07T00:00:00+00:00",
                        "level": "WARNING",
                        "logger": "x",
                        "message": f"row {i}",
                    }
                    for i in range(LOG_RETENTION + 120)
                ],
            )
        removed = trim(db)
        assert removed == 120
        with db.connect() as conn:
            assert (
                conn.execute(select(func.count()).select_from(log_record)).scalar_one()
                == LOG_RETENTION
            )

    def test_trimming_keeps_the_newest(self, db: Engine, log) -> None:
        with db.begin() as conn:
            conn.execute(
                log_record.insert(),
                [
                    {
                        "created_at": "2026-08-07T00:00:00+00:00",
                        "level": "ERROR",
                        "logger": "x",
                        "message": f"row {i}",
                    }
                    for i in range(LOG_RETENTION + 10)
                ],
            )
        trim(db)
        with db.connect() as conn:
            newest = conn.execute(
                select(log_record.c.message).order_by(log_record.c.id.desc()).limit(1)
            ).scalar_one()
        assert newest == f"row {LOG_RETENTION + 9}"

"""SQLite engine setup.

WAL mode is what makes SQLite viable here: the ingestion worker writes while the
web tier keeps serving reads. See docs/prd/07-architecture-and-api.md.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

PRAGMAS = {
    "journal_mode": "WAL",
    "synchronous": "NORMAL",
    "foreign_keys": "ON",
    "busy_timeout": "5000",
    "cache_size": "-64000",  # 64 MB page cache
    "mmap_size": "268435456",  # 256 MB
}


def _apply_pragmas(dbapi_connection: sqlite3.Connection, _record: object) -> None:
    cursor = dbapi_connection.cursor()
    try:
        for name, value in PRAGMAS.items():
            cursor.execute(f"PRAGMA {name}={value}")
    finally:
        cursor.close()


def build_engine(db_path: Path, *, echo: bool = False) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite+pysqlite:///{db_path}",
        echo=echo,
        future=True,
        # check_same_thread=False lets FastAPI's threadpool share the engine.
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _apply_pragmas)
    return engine


_engine: Engine | None = None
_raw_engine: Engine | None = None


def get_engine() -> Engine:
    """Engine for the serving database."""
    global _engine
    if _engine is None:
        _engine = build_engine(get_settings().stocklens_db_path)
    return _engine


def get_raw_engine() -> Engine:
    """Engine for the raw response archive, a separate file by design."""
    global _raw_engine
    if _raw_engine is None:
        _raw_engine = build_engine(get_settings().stocklens_raw_db_path)
    return _raw_engine


def reset_engines() -> None:
    """Drop cached engines. Used by tests that point at a temporary database."""
    global _engine, _raw_engine
    for engine in (_engine, _raw_engine):
        if engine is not None:
            engine.dispose()
    _engine = None
    _raw_engine = None


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    """Transactional session. Commits on success, rolls back on failure."""
    factory = sessionmaker(bind=engine or get_engine(), future=True, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with session_scope() as session:
        yield session

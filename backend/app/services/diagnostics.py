"""What an operator needs when something is wrong.

A self-hosted install is usually a container nobody is watching. This gathers
the recent warnings and errors, the state of the data, and the state of the
process, so a diagnosis does not need shell access.
"""

from __future__ import annotations

import platform
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, desc, func, select

from app.config import get_settings
from app.db.engine import get_engine, get_raw_engine
from app.db.models import ingestion_run, log_record
from app.services.errors import NotFound

RECENT_WINDOW = timedelta(hours=24)


def _engine(engine: Engine | None = None) -> Engine:
    return engine or get_engine()


def logs(
    *,
    level: str | None = None,
    logger: str | None = None,
    limit: int = 100,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Recent warnings and errors, newest first."""
    with _engine(engine).connect() as conn:
        query = select(log_record)
        if level:
            query = query.where(log_record.c.level == level.upper())
        if logger:
            query = query.where(log_record.c.logger.like(f"{logger}%"))
        rows = (
            conn.execute(query.order_by(desc(log_record.c.id)).limit(min(limit, 500)))
            .mappings()
            .all()
        )
        counts = dict(
            conn.execute(
                select(log_record.c.level, func.count()).group_by(log_record.c.level)
            ).all()
        )
        total = conn.execute(select(func.count()).select_from(log_record)).scalar_one()

    return {
        "total": total,
        "by_level": counts,
        "entries": [dict(r) for r in rows],
    }


def entry(log_id: int, *, engine: Engine | None = None) -> dict[str, Any]:
    """One record, with its traceback."""
    with _engine(engine).connect() as conn:
        row = conn.execute(select(log_record).where(log_record.c.id == log_id)).mappings().first()
    if row is None:
        raise NotFound(f"No log entry with the id {log_id}", log_id=log_id)
    return dict(row)


def health(*, engine: Engine | None = None) -> dict[str, Any]:
    """A single page an operator can read to decide whether anything is wrong."""
    db = _engine(engine)
    settings = get_settings()
    now = datetime.now(UTC)
    since = (now - RECENT_WINDOW).isoformat()

    with db.connect() as conn:
        recent = dict(
            conn.execute(
                select(log_record.c.level, func.count())
                .where(log_record.c.created_at >= since)
                .group_by(log_record.c.level)
            ).all()
        )
        newest = (
            conn.execute(
                select(log_record)
                .where(log_record.c.level.in_(("ERROR", "CRITICAL")))
                .order_by(desc(log_record.c.id))
                .limit(1)
            )
            .mappings()
            .first()
        )
        runs = (
            conn.execute(select(ingestion_run).order_by(desc(ingestion_run.c.started_at)).limit(1))
            .mappings()
            .first()
        )

    errors = recent.get("ERROR", 0) + recent.get("CRITICAL", 0)
    return {
        "checked_at": now.isoformat(),
        "environment": settings.environment,
        "errors_last_24h": errors,
        "warnings_last_24h": recent.get("WARNING", 0),
        "last_error": dict(newest) if newest else None,
        "last_run": dict(runs) if runs else None,
        "process": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "storage": _storage(db),
    }


def _storage(engine: Engine) -> dict[str, Any]:
    """Row counts and file sizes, so "is the disk full" is answerable."""
    from pathlib import Path

    out: dict[str, Any] = {}
    for label, eng in (("core", engine), ("raw", get_raw_engine())):
        url = eng.url.database
        if url and url != ":memory:":
            path = Path(url)
            out[label] = {
                "path": str(path),
                "bytes": path.stat().st_size if path.exists() else 0,
            }
    return out

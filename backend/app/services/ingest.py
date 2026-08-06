"""Ingestion control.

Wraps the jobs in app/ingest so they can be triggered and monitored from the
Super Admin console, a script, or an agent - not only from the CLI.

Long runs execute in a background thread and report progress through the
`ingestion_run` and `ingestion_task` tables, so progress survives a page reload
and can be read by anything with database access.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, func, select

from app.db.engine import get_engine
from app.db.models import ingestion_run, ingestion_task
from app.ingest.backfill import CALLS_PER_SYMBOL, backfill_symbols, dry_run, prioritised_symbols
from app.ingest.jobs import run_price_refresh, run_universe_sync
from app.ingest.materialise import materialise
from app.ingest.quality import summary as quality_summary
from app.ingest.repair import repair as repair_rows
from app.ingest.store import finish_run, new_run_id
from app.services.errors import Conflict, NotFound

logger = logging.getLogger("stocklens.services.ingest")

JOB_KINDS = ("universe", "price", "backfill", "materialise")

# One long job at a time. SQLite has a single writer, and two backfills would
# fight over it while doubling the request rate against FinEdge.
_active: dict[str, str] = {}
_lock = threading.Lock()

# A run left "running" for longer than this is treated as abandoned rather than
# holding the lock forever. It has to exceed the longest legitimate job: a full
# universe backfill is roughly eighteen hours, so a day is the first duration
# that cannot be a live run. An operator who knows a job died can clear it
# immediately with `release_stuck_run` rather than waiting.
STALE_RUN_AFTER = timedelta(hours=24)


def _engine(engine: Engine | None = None) -> Engine:
    return engine or get_engine()


def _running_row(engine: Engine) -> dict[str, Any] | None:
    """The live run according to the database, ignoring abandoned ones.

    The in-process flag alone is not enough: a job started by the CLI, or by a
    second worker, is invisible to this process's memory but very much real to
    FinEdge and to SQLite's single writer.
    """
    with engine.connect() as conn:
        row = (
            conn.execute(
                select(ingestion_run)
                .where(ingestion_run.c.status == "running")
                .order_by(ingestion_run.c.started_at.desc())
            )
            .mappings()
            .first()
        )
    if row is None:
        return None

    started = _parse_time(row["started_at"])
    if started is not None and datetime.now(UTC) - started > STALE_RUN_AFTER:
        return None
    return dict(row)


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def active_run(engine: Engine | None = None) -> str | None:
    with _lock:
        in_process = _active.get("run_id")
    if in_process:
        return in_process
    row = _running_row(_engine(engine))
    return row["id"] if row else None


def _claim(run_id: str, engine: Engine | None = None) -> None:
    with _lock:
        if _active.get("run_id"):
            raise Conflict(
                "A job is already running. Wait for it to finish or stop it first.",
                run_id=_active["run_id"],
            )
        running = _running_row(_engine(engine))
        if running is not None:
            raise Conflict(
                f"A {running['job_kind']} job started at {running['started_at']} is still "
                "running. Wait for it to finish, or clear it if you know it died.",
                run_id=running["id"],
                job_kind=running["job_kind"],
            )
        _active["run_id"] = run_id


def _release() -> None:
    with _lock:
        _active.pop("run_id", None)


def release_stuck_run(run_id: str, *, engine: Engine | None = None) -> dict[str, Any]:
    """Mark an abandoned run as failed so a new one can start.

    A process killed mid-backfill leaves its row saying "running" forever. This
    is the operator saying they know it is dead - it does not stop a live job,
    because nothing here can reach into another process to halt it.
    """
    db = _engine(engine)
    with db.connect() as conn:
        row = (
            conn.execute(select(ingestion_run).where(ingestion_run.c.id == run_id))
            .mappings()
            .first()
        )
    if row is None:
        raise NotFound(f"No run with the id {run_id}", run_id=run_id)
    if row["status"] != "running":
        raise Conflict(
            f"That run already finished with status {row['status']}.",
            run_id=run_id,
            status=row["status"],
        )
    with _lock:
        if _active.get("run_id") == run_id:
            raise Conflict(
                "That job is running in this process right now, so it is not stuck.",
                run_id=run_id,
            )

    finish_run(db, run_id, status="failed", error="Cleared by an administrator as abandoned.")
    return {"run_id": run_id, "cleared": True}


def plan(limit: int | None = None, *, engine: Engine | None = None) -> dict[str, Any]:
    """What a backfill would cost, without spending it."""
    db = _engine(engine)
    symbols = prioritised_symbols(db, limit=limit)
    if not symbols:
        return {
            "symbols": 0,
            "message": "No symbols loaded. Run the universe sync first.",
            "calls_per_symbol": CALLS_PER_SYMBOL,
            "estimated_calls": 0,
            "estimated_hours": 0,
        }
    return dry_run(db, symbols)


def status(*, engine: Engine | None = None) -> dict[str, Any]:
    """Current and recent runs, with per-run task progress."""
    db = _engine(engine)
    with db.connect() as conn:
        runs = (
            conn.execute(
                select(ingestion_run).order_by(ingestion_run.c.started_at.desc()).limit(10)
            )
            .mappings()
            .all()
        )
        progress: dict[str, dict[str, int]] = {}
        for row in conn.execute(
            select(ingestion_task.c.run_id, ingestion_task.c.status, func.count()).group_by(
                ingestion_task.c.run_id, ingestion_task.c.status
            )
        ):
            progress.setdefault(row[0], {})[row[1]] = row[2]

        # Task rows are written per symbol as the run reaches it, so "tasks done
        # over tasks recorded" is always ~100% and tells the operator nothing.
        # Symbols are the honest denominator: the run knows up front how many it
        # set out to fetch.
        symbols_seen = {
            row[0]: row[1]
            for row in conn.execute(
                select(
                    ingestion_task.c.run_id, func.count(ingestion_task.c.symbol.distinct())
                ).group_by(ingestion_task.c.run_id)
            )
        }

    running = active_run()
    return {
        "active_run_id": running,
        "is_running": running is not None,
        "runs": [
            {
                **dict(r),
                "progress": progress.get(r["id"], {}),
                "symbols_done": symbols_seen.get(r["id"], 0),
                "symbols_total": _planned_symbols(r["scope"]),
                "is_active": r["id"] == running,
            }
            for r in runs
        ],
    }


def _planned_symbols(scope: str | None) -> int | None:
    """How many companies the run set out to fetch, from its recorded scope."""
    if not scope:
        return None
    try:
        parsed = json.loads(scope)
    except (TypeError, ValueError):
        return None
    value = parsed.get("symbols") if isinstance(parsed, dict) else None
    return value if isinstance(value, int) else None


def run_detail(run_id: str, *, engine: Engine | None = None) -> dict[str, Any]:
    db = _engine(engine)
    with db.connect() as conn:
        row = (
            conn.execute(select(ingestion_run).where(ingestion_run.c.id == run_id))
            .mappings()
            .first()
        )
        if row is None:
            raise NotFound(f"No run with the id {run_id}", run_id=run_id)
        counts = {
            r[0]: r[1]
            for r in conn.execute(
                select(ingestion_task.c.status, func.count())
                .where(ingestion_task.c.run_id == run_id)
                .group_by(ingestion_task.c.status)
            )
        }
        symbols_done = (
            conn.execute(
                select(func.count(ingestion_task.c.symbol.distinct())).where(
                    ingestion_task.c.run_id == run_id
                )
            ).scalar()
            or 0
        )
        failures = (
            conn.execute(
                select(
                    ingestion_task.c.symbol,
                    ingestion_task.c.endpoint,
                    ingestion_task.c.last_error,
                )
                .where(ingestion_task.c.run_id == run_id, ingestion_task.c.status == "failed")
                .limit(20)
            )
            .mappings()
            .all()
        )
    return {
        **dict(row),
        "progress": counts,
        "symbols_done": symbols_done,
        "symbols_total": _planned_symbols(row["scope"]),
        "is_active": run_id == active_run(),
        "failures": [dict(f) for f in failures],
    }


def _run_in_background(job_kind: str, coro_factory, run_id: str) -> None:
    """Execute an async job on its own thread and always release the lock."""

    def target() -> None:
        try:
            asyncio.run(coro_factory())
        except Exception as exc:  # noqa: BLE001 - a failed job must not wedge the lock
            logger.exception("%s job failed", job_kind)
            try:
                finish_run(get_engine(), run_id, status="failed", error=str(exc))
            except Exception:  # noqa: BLE001
                logger.exception("could not record the failure for run %s", run_id)
        finally:
            _release()

    thread = threading.Thread(target=target, name=f"stocklens-{job_kind}", daemon=True)
    thread.start()


def start_universe_sync() -> dict[str, Any]:
    """Symbol master, all indices with constituents, index quotes and returns.

    Four calls. Fast enough to run inline rather than in the background.
    """
    run_id = new_run_id()
    _claim(run_id)
    try:
        return asyncio.run(run_universe_sync())
    finally:
        _release()


def start_price_refresh() -> dict[str, Any]:
    """Every company's quote in a single call."""
    run_id = new_run_id()
    _claim(run_id)
    try:
        return asyncio.run(run_price_refresh())
    finally:
        _release()


def start_backfill(
    *,
    limit: int | None = None,
    symbols: list[str] | None = None,
    call_budget: int | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Fetch and normalise the full endpoint matrix for many companies.

    Runs in the background: the full universe is roughly 332,000 calls and
    eighteen hours. Progress is written to the run and task tables as it goes.
    """
    db = _engine(engine)
    chosen = [s.upper() for s in symbols] if symbols else prioritised_symbols(db, limit=limit)
    if not chosen:
        raise Conflict("No symbols to backfill. Run the universe sync first.")

    run_id = new_run_id()
    _claim(run_id, db)
    _run_in_background(
        "backfill",
        lambda: backfill_symbols(chosen, call_budget=call_budget, run_id=run_id),
        run_id,
    )
    return {
        "run_id": run_id,
        "started": True,
        "symbols": len(chosen),
        "estimated_calls": len(chosen) * CALLS_PER_SYMBOL,
        "first": chosen[:10],
    }


def rebuild_snapshot(*, engine: Engine | None = None) -> dict[str, Any]:
    """Re-materialise the screener table from the normalised tables."""
    return materialise(_engine(engine))


def repair(*, engine: Engine | None = None) -> dict[str, Any]:
    """Re-apply the normalisation rules to rows already stored.

    Normalisation only runs when a row is fetched, so a rule added later leaves
    everything downloaded before it untouched - including the rest of a backfill
    that was already running when the rule landed. No FinEdge calls.
    """
    return repair_rows(_engine(engine))


def quality(*, engine: Engine | None = None) -> dict[str, Any]:
    return quality_summary(_engine(engine))

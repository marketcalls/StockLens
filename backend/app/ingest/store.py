"""Persistence for Layer 1 raw responses and job control rows."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import zstandard
from sqlalchemy import Engine, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models import ingestion_run, ingestion_task, raw_response
from app.finedge.client import FinEdgeResponse

_COMPRESSOR = zstandard.ZstdCompressor(level=10)
_DECOMPRESSOR = zstandard.ZstdDecompressor()


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def canonical_params(params: dict[str, Any]) -> str:
    """Stable JSON so the same request always hashes identically."""
    return json.dumps(params, sort_keys=True, separators=(",", ":"))


def params_hash(params: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_params(params).encode()).hexdigest()


def new_run_id() -> str:
    return str(uuid.uuid4())


def start_run(
    engine: Engine,
    *,
    job_kind: str,
    scope: dict[str, Any] | None = None,
    call_budget: int | None = None,
    run_id: str | None = None,
) -> str:
    run_id = run_id or new_run_id()
    with engine.begin() as conn:
        conn.execute(
            ingestion_run.insert().values(
                id=run_id,
                job_kind=job_kind,
                scope=json.dumps(scope) if scope else None,
                status="running",
                started_at=utcnow(),
            )
        )
    return run_id


def finish_run(
    engine: Engine,
    run_id: str,
    *,
    status: str,
    calls_made: int = 0,
    bytes_fetched: int = 0,
    rows_written: int = 0,
    error: str | None = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            ingestion_run.update()
            .where(ingestion_run.c.id == run_id)
            .values(
                status=status,
                calls_made=calls_made,
                bytes_fetched=bytes_fetched,
                rows_written=rows_written,
                finished_at=utcnow(),
                error=error,
            )
        )


def record_task(
    engine: Engine,
    run_id: str,
    *,
    symbol: str,
    endpoint: str,
    params: dict[str, Any],
    status: str,
    last_error: str | None = None,
) -> None:
    """Upsert a task checkpoint. Resume selects pending and failed rows."""
    values = {
        "run_id": run_id,
        "symbol": symbol or "",
        "endpoint": endpoint,
        "params_hash": params_hash(params),
        "params": canonical_params(params),
        "status": status,
        "last_error": last_error,
        "completed_at": utcnow() if status in ("done", "skipped") else None,
    }
    stmt = sqlite_insert(ingestion_task).values(attempts=1, **values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["run_id", "symbol", "endpoint", "params_hash"],
        set_={
            "status": stmt.excluded.status,
            "last_error": stmt.excluded.last_error,
            "completed_at": stmt.excluded.completed_at,
            "attempts": ingestion_task.c.attempts + 1,
        },
    )
    with engine.begin() as conn:
        conn.execute(stmt)


def store_raw(engine: Engine, run_id: str, response: FinEdgeResponse) -> bool:
    """Persist a raw response. Returns False when the content was already stored.

    The unique index on (endpoint, symbol, content_hash) means an unchanged
    re-fetch costs no storage.
    """
    symbol = _symbol_of(response)
    payload = _COMPRESSOR.compress(response.raw_bytes)
    stmt = (
        sqlite_insert(raw_response)
        .values(
            endpoint=response.endpoint,
            symbol=symbol,
            params=canonical_params(response.params),
            payload=payload,
            content_hash=response.content_hash,
            size_bytes=response.size_bytes,
            status_code=response.status_code,
            fetched_at=utcnow(),
            run_id=run_id,
        )
        .on_conflict_do_nothing(index_elements=["endpoint", "symbol", "content_hash"])
    )
    with engine.begin() as conn:
        result = conn.execute(stmt)
    return bool(result.rowcount)


def load_raw(engine: Engine, endpoint: str, symbol: str = "") -> Any | None:
    """Read back the most recent payload for an endpoint, decompressed."""
    with engine.connect() as conn:
        row = conn.execute(
            select(raw_response.c.payload)
            .where(raw_response.c.endpoint == endpoint, raw_response.c.symbol == symbol)
            .order_by(raw_response.c.fetched_at.desc())
            .limit(1)
        ).first()
    if row is None:
        return None
    return json.loads(_DECOMPRESSOR.decompress(row[0]))


def raw_summary(engine: Engine) -> dict[str, Any]:
    """Counts and freshness for the meta endpoint."""
    with engine.connect() as conn:
        total, symbols, newest, size = conn.execute(
            select(
                func.count(),
                func.count(func.distinct(raw_response.c.symbol)),
                func.max(raw_response.c.fetched_at),
                func.coalesce(func.sum(raw_response.c.size_bytes), 0),
            ).select_from(raw_response)
        ).one()
    return {
        "raw_responses": total,
        "distinct_symbols": symbols,
        "last_fetched_at": newest,
        "uncompressed_bytes": size,
    }


def run_summary(engine: Engine, limit: int = 5) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            select(
                ingestion_run.c.id,
                ingestion_run.c.job_kind,
                ingestion_run.c.status,
                ingestion_run.c.calls_made,
                ingestion_run.c.bytes_fetched,
                ingestion_run.c.started_at,
                ingestion_run.c.finished_at,
            )
            .order_by(ingestion_run.c.started_at.desc())
            .limit(limit)
        ).mappings()
        return [dict(row) for row in rows]


def _symbol_of(response: FinEdgeResponse) -> str:
    """Derive the symbol from the endpoint path, empty for universe-wide calls."""
    parts = [p for p in response.endpoint.split("/") if p]
    if len(parts) >= 4 and parts[0] == "api" and parts[1] == "v1":
        tail = parts[-1]
        known_tails = {
            "all",
            "master",
            "historical",
            "daily-feed",
            "price-returns",
            "quote",
            "stock-symbols",
            "stock-search",
            "results-calendar",
            "ipo-calendar",
            "holidays-calendar",
            "corp-announcements",
            "credit-ratings",
            "investor-call-transcripts",
            "investor-presentations",
            "refreshed-stocks",
            "commodity-list",
            "name-changes",
            "symbol-changes",
        }
        if tail not in known_tails:
            return tail
    return ""

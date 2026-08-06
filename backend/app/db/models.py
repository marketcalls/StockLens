"""Layer 1 (raw) and job-control tables.

Layer 2 (normalised) and Layer 3 (serving) arrive in Phase 1. Schema shapes
follow docs/prd/06-data-model-and-ingestion.md.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)

# Raw archive lives in its own database file, so it gets its own MetaData.
raw_metadata = MetaData()
core_metadata = MetaData()


raw_response = Table(
    "raw_response",
    raw_metadata,
    Column("id", Integer, primary_key=True),
    Column("endpoint", String, nullable=False),
    Column("symbol", String, nullable=False, server_default=""),
    Column("params", String, nullable=False),  # canonical JSON
    Column("payload", LargeBinary, nullable=False),  # zstd-compressed JSON
    Column("content_hash", String, nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("status_code", Integer, nullable=False),
    Column("fetched_at", String, nullable=False),  # ISO-8601 UTC
    Column("run_id", String, nullable=False),
    UniqueConstraint("endpoint", "symbol", "content_hash", name="uq_raw_dedupe"),
    Index("idx_raw_symbol_endpoint", "symbol", "endpoint", "fetched_at"),
)


ingestion_run = Table(
    "ingestion_run",
    core_metadata,
    Column("id", String, primary_key=True),
    Column("job_kind", String, nullable=False),
    Column("scope", String),  # JSON
    Column("triggered_by", Integer),
    Column("status", String, nullable=False),
    Column("calls_made", Integer, nullable=False, server_default="0"),
    Column("call_budget", Integer),
    Column("bytes_fetched", BigInteger, nullable=False, server_default="0"),
    Column("rows_written", BigInteger, nullable=False, server_default="0"),
    Column("started_at", String),
    Column("finished_at", String),
    Column("error", String),
)


ingestion_task = Table(
    "ingestion_task",
    core_metadata,
    Column("run_id", String, ForeignKey("ingestion_run.id", ondelete="CASCADE"), primary_key=True),
    Column("symbol", String, primary_key=True, server_default=""),
    Column("endpoint", String, primary_key=True),
    # sha256 of canonical params JSON: SQLite compares TEXT byte-wise and key
    # ordering in a serialised JSON object is not guaranteed stable.
    Column("params_hash", String, primary_key=True),
    Column("params", String),
    Column("status", String, nullable=False),
    Column("attempts", Integer, nullable=False, server_default="0"),
    Column("last_error", String),
    Column("completed_at", String),
    Index("idx_task_pending", "run_id", "status"),
)


# Warnings, errors and unhandled exceptions, kept so an operator can see what
# went wrong without shell access to the server. Trimmed to LOG_RETENTION rows.
log_record = Table(
    "log_record",
    core_metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("created_at", String, nullable=False, index=True),
    Column("level", String, nullable=False, index=True),
    Column("logger", String, nullable=False),
    Column("message", String, nullable=False),
    Column("traceback", String),
    # Set when the record came from a request rather than a background job.
    Column("path", String),
    Column("method", String),
    Column("status", Integer),
    Column("actor_id", Integer),
)


def create_all(core_engine: object, raw_engine: object) -> None:
    """Create both schemas. Alembic owns migrations; this is for tests and bootstrap."""
    core_metadata.create_all(core_engine)  # type: ignore[arg-type]
    raw_metadata.create_all(raw_engine)  # type: ignore[arg-type]

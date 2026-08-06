"""Persistence for Layer 2 normalised rows.

All writes are upserts, so a job can be re-run safely. Batched into chunks
because SQLite has a variable limit per statement and one writer at a time -
short transactions keep the web tier's readers unblocked under WAL.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, Table, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.layer2 import (
    company,
    index_constituent,
    index_master,
    index_quote_daily,
    index_return,
    price_daily,
    quote,
    statement_line,
    statement_period,
)

# SQLite's default SQLITE_MAX_VARIABLE_NUMBER is 999 on older builds. Chunk so a
# wide table never exceeds it.
CHUNK_ROWS = 200


def _chunks(rows: list[dict[str, Any]], size: int = CHUNK_ROWS):
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def upsert(engine: Engine, table: Table, rows: list[dict[str, Any]]) -> int:
    """Insert or update by primary key. Returns the number of rows written."""
    if not rows:
        return 0
    key_columns = [c.name for c in table.primary_key.columns]
    written = 0
    with engine.begin() as conn:
        for chunk in _chunks(rows):
            stmt = sqlite_insert(table).values(chunk)
            updatable = {
                c.name: getattr(stmt.excluded, c.name)
                for c in table.columns
                if c.name not in key_columns
            }
            if updatable:
                stmt = stmt.on_conflict_do_update(index_elements=key_columns, set_=updatable)
            else:
                stmt = stmt.on_conflict_do_nothing(index_elements=key_columns)
            conn.execute(stmt)
            written += len(chunk)
    return written


def upsert_companies(engine: Engine, rows: list[dict[str, Any]]) -> int:
    return upsert(engine, company, rows)


def update_company_profiles(engine: Engine, rows: list[dict[str, Any]]) -> int:
    """Merge profile fields into existing company rows without clobbering identity.

    The symbol master supplies name and codes; the profile supplies
    classification. A blind upsert would null out whichever the other owns.
    """
    written = 0
    with engine.begin() as conn:
        for row in rows:
            payload = {k: v for k, v in row.items() if k != "symbol" and v is not None}
            if not payload:
                continue
            result = conn.execute(
                company.update().where(company.c.symbol == row["symbol"]).values(**payload)
            )
            if result.rowcount == 0:
                conn.execute(
                    company.insert().values(
                        symbol=row["symbol"],
                        name=payload.get("name") or row["symbol"],
                        **{k: v for k, v in payload.items() if k != "name"},
                    )
                )
            written += 1
    return written


def upsert_quotes(engine: Engine, rows: list[dict[str, Any]]) -> int:
    return upsert(engine, quote, rows)


def upsert_prices(engine: Engine, rows: list[dict[str, Any]]) -> int:
    return upsert(engine, price_daily, rows)


def replace_index_master(
    engine: Engine, indices: list[dict[str, Any]], constituents: list[dict[str, Any]]
) -> tuple[int, int]:
    """Upsert indices and replace their constituent lists.

    Membership changes on rebalance, so stale links must go rather than
    accumulate - an upsert alone would leave a dropped company in the index
    forever.
    """
    written_idx = upsert(engine, index_master, indices)
    touched = {i["index_symbol"] for i in indices}
    with engine.begin() as conn:
        for index_symbol in touched:
            conn.execute(
                index_constituent.delete().where(index_constituent.c.index_symbol == index_symbol)
            )
    written_con = upsert(engine, index_constituent, constituents)
    return written_idx, written_con


def upsert_index_quotes(engine: Engine, rows: list[dict[str, Any]]) -> int:
    return upsert(engine, index_quote_daily, rows)


def replace_index_returns(engine: Engine, rows: list[dict[str, Any]]) -> int:
    """Returns are a full snapshot per run; horizons that vanish should not linger."""
    touched = {r["index_symbol"] for r in rows}
    with engine.begin() as conn:
        for index_symbol in touched:
            conn.execute(index_return.delete().where(index_return.c.index_symbol == index_symbol))
    return upsert(engine, index_return, rows)


def store_statements(
    engine: Engine,
    periods: list[dict[str, Any]],
    lines: list[list[dict[str, Any]]],
) -> tuple[int, int]:
    """Write periods and their lines, replacing any prior version of each period.

    A restatement changes the figures for a period we already hold, so the
    existing lines are cleared rather than merged - otherwise a removed line
    would survive as a stale value.
    """
    if not periods:
        return 0, 0

    written_periods = written_lines = 0
    with engine.begin() as conn:
        for period, period_lines in zip(periods, lines, strict=True):
            existing = conn.execute(
                select(statement_period.c.id).where(
                    statement_period.c.symbol == period["symbol"],
                    statement_period.c.statement_type == period["statement_type"],
                    statement_period.c.statement_code == period["statement_code"],
                    statement_period.c.period_kind == period["period_kind"],
                    statement_period.c.header == period["header"],
                )
            ).scalar_one_or_none()

            if existing is None:
                period_id = conn.execute(
                    statement_period.insert().values(**period)
                ).inserted_primary_key[0]
            else:
                period_id = existing
                conn.execute(
                    statement_period.update()
                    .where(statement_period.c.id == period_id)
                    .values(**period)
                )
                conn.execute(statement_line.delete().where(statement_line.c.period_id == period_id))

            written_periods += 1
            rows = [
                {"period_id": period_id, "field_name": ln["field_name"], "value": ln["value"]}
                for ln in period_lines
            ]
            for chunk in _chunks(rows):
                conn.execute(
                    sqlite_insert(statement_line)
                    .values(chunk)
                    .on_conflict_do_update(
                        index_elements=["period_id", "field_name"],
                        set_={"value": sqlite_insert(statement_line).excluded.value},
                    )
                )
            written_lines += len(rows)

    return written_periods, written_lines


def company_count(engine: Engine) -> int:
    with engine.connect() as conn:
        return conn.execute(select(company.c.symbol)).rowcount or len(
            conn.execute(select(company.c.symbol)).all()
        )


def counts(engine: Engine) -> dict[str, int]:
    """Row counts for the freshness endpoint and data-quality checks."""
    from sqlalchemy import func

    tables = {
        "companies": company,
        "quotes": quote,
        "statement_periods": statement_period,
        "statement_lines": statement_line,
        "price_days": price_daily,
        "indices": index_master,
        "index_constituents": index_constituent,
        "index_returns": index_return,
    }
    out: dict[str, int] = {}
    with engine.connect() as conn:
        for name, table in tables.items():
            out[name] = conn.execute(select(func.count()).select_from(table)).scalar_one()
    return out

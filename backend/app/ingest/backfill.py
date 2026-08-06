"""Job 6: the per-symbol backfill.

Fetches a company's full endpoint matrix, archives each raw response, and
normalises it into Layer 2 in the same pass.

The full run is ~332,000 calls across 5,630 companies, so it must be:

- **prioritised** - index constituents first, then by market cap, so the product
  is useful after a few hours rather than after the whole run
- **resumable** - checkpointed per (symbol, endpoint, params)
- **budgeted** - a hard call ceiling that stops cleanly
- **dry-runnable** - report the cost before spending it

See docs/prd/06-data-model-and-ingestion.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Engine, select

from app.db.engine import get_engine, get_raw_engine
from app.db.layer2 import (
    basic_financial,
    company,
    corporate_action,
    create_layer2,
    index_constituent,
    metric,
    price_ratio_annual,
    price_ratio_daily,
    quote,
    ratio,
    shareholding,
)
from app.db.models import create_all
from app.finedge.client import (
    FinEdgeClient,
    FinEdgeError,
    FinEdgeParameterError,
)
from app.finedge.endpoints import Call, symbol_endpoint_matrix
from app.ingest import layer2_store as l2
from app.ingest import normalise as nz
from app.ingest.store import finish_run, record_task, start_run, store_raw

logger = logging.getLogger("stocklens.backfill")

# Indices whose members are worth having first. Broad-market and large-cap.
PRIORITY_INDICES = (
    "NIF50",
    "NIFTY50",
    "SNSXLRGCAP",
    "NIF100",
    "NIF500",
    "BSE500",
    "BSE100",
    "BSE200",
)

CALLS_PER_SYMBOL = len(symbol_endpoint_matrix("PLACEHOLDER"))


@dataclass
class BackfillResult:
    run_id: str
    symbols_planned: int = 0
    symbols_done: int = 0
    calls_made: int = 0
    stored: int = 0
    unchanged: int = 0
    skipped: int = 0
    failed: int = 0
    rows_written: int = 0
    bytes_fetched: int = 0
    budget_exhausted: bool = False
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "symbols_planned": self.symbols_planned,
            "symbols_done": self.symbols_done,
            "calls_made": self.calls_made,
            "stored": self.stored,
            "unchanged": self.unchanged,
            "skipped": self.skipped,
            "failed": self.failed,
            "rows_written": self.rows_written,
            "bytes_fetched": self.bytes_fetched,
            "budget_exhausted": self.budget_exhausted,
        }


def prioritised_symbols(engine: Engine, limit: int | None = None) -> list[str]:
    """Order the universe so the names people actually search for land first.

    Index constituents first (ordered by market cap), then everything else by
    market cap descending. Companies with no quote sort last rather than being
    dropped, since a missing quote does not mean a missing company.
    """
    with engine.connect() as conn:
        known = [r[0] for r in conn.execute(select(company.c.symbol)).all()]
        known_set = set(known)

        priority: set[str] = set()
        for index_symbol in PRIORITY_INDICES:
            members = conn.execute(
                select(index_constituent.c.symbol).where(
                    index_constituent.c.index_symbol == index_symbol
                )
            ).all()
            priority.update(m[0] for m in members if m[0] in known_set)

        # Any index membership at all beats none.
        any_index = {
            r[0]
            for r in conn.execute(select(index_constituent.c.symbol)).all()
            if r[0] in known_set
        }

        caps = {
            r.symbol: (r.market_cap or 0.0)
            for r in conn.execute(select(quote.c.symbol, quote.c.market_cap)).all()
        }

    def sort_key(symbol: str) -> tuple[int, float]:
        if symbol in priority:
            tier = 0
        elif symbol in any_index:
            tier = 1
        else:
            tier = 2
        return (tier, -caps.get(symbol, 0.0))

    ordered = sorted(known, key=sort_key)
    return ordered[:limit] if limit else ordered


def dry_run(engine: Engine, symbols: list[str], rps: float = 5.0) -> dict[str, Any]:
    """Report the cost of a run without spending it."""
    calls = len(symbols) * CALLS_PER_SYMBOL
    seconds = calls / rps if rps > 0 else 0
    return {
        "symbols": len(symbols),
        "calls_per_symbol": CALLS_PER_SYMBOL,
        "estimated_calls": calls,
        "estimated_seconds": round(seconds),
        "estimated_hours": round(seconds / 3600, 2),
        "assumed_rps": rps,
        "first_10": symbols[:10],
    }


def _normalise_call(core: Engine, symbol: str, call: Call, payload: Any) -> int:
    """Route one response to its normaliser. Returns rows written.

    Unrecognised endpoints are archived at Layer 1 but not normalised, so adding
    a new endpoint to the matrix cannot silently corrupt Layer 2.
    """
    endpoint, params = call.endpoint, call.params
    st = params.get("statement_type", "")

    if "/company-profile/" in endpoint:
        row = nz.normalise_profile(symbol, payload)
        return l2.update_company_profiles(core, [row]) if row else 0

    if "/financials/" in endpoint:
        periods, lines, _kind = nz.normalise_statements(
            symbol, st, params.get("statement_code", ""), params.get("period", ""), payload
        )
        written_periods, written_lines = l2.store_statements(core, periods, lines)
        return written_periods + written_lines

    if "/basic-financials/" in endpoint:
        rows = nz.normalise_basic_financials(symbol, st, params.get("statement_code", ""), payload)
        return l2.upsert(core, basic_financial, rows)

    if "/financial-metrics/" in endpoint:
        rows = nz.normalise_metrics(symbol, st, params.get("ratio_type", ""), payload)
        return l2.upsert(core, metric, rows)

    if "/ratios/" in endpoint:
        rows = nz.normalise_ratios(symbol, st, params.get("ratio_type", ""), payload)
        return l2.upsert(core, ratio, rows)

    if "/daily-price-ratios/" in endpoint:
        return l2.upsert(
            core, price_ratio_daily, nz.normalise_price_ratios_daily(symbol, st, payload)
        )

    if "/annual-price-ratios/" in endpoint:
        return l2.upsert(
            core, price_ratio_annual, nz.normalise_price_ratios_annual(symbol, st, payload)
        )

    if "/daily-quotes/" in endpoint:
        return l2.upsert_prices(core, nz.normalise_prices(symbol, payload))

    if "/dividend/" in endpoint:
        return l2.upsert(core, corporate_action, nz.normalise_dividends(symbol, payload))

    if "/corporate-actions/" in endpoint:
        action = endpoint.split("/corporate-actions/")[1].split("/")[0]
        return l2.upsert(
            core, corporate_action, nz.normalise_corporate_action(symbol, action, payload)
        )

    if "/shareholdings/distribution/" in endpoint:
        return l2.upsert(core, shareholding, nz.normalise_shareholding(symbol, payload))

    return 0


async def backfill_symbols(
    symbols: list[str],
    *,
    call_budget: int | None = None,
    run_id: str | None = None,
) -> BackfillResult:
    """Fetch and normalise the full matrix for each symbol, in order."""
    core, raw = get_engine(), get_raw_engine()
    create_all(core, raw)
    create_layer2(core)

    run_id = start_run(
        core,
        job_kind="backfill",
        scope={"symbols": len(symbols), "budget": call_budget},
        run_id=run_id,
    )
    result = BackfillResult(run_id=run_id, symbols_planned=len(symbols))
    client = FinEdgeClient()

    try:
        for position, symbol in enumerate(symbols, start=1):
            if call_budget is not None and client.calls_made >= call_budget:
                result.budget_exhausted = True
                logger.warning(
                    "call budget of %d reached after %d symbols; stopping cleanly",
                    call_budget,
                    result.symbols_done,
                )
                break

            for call in symbol_endpoint_matrix(symbol):
                if call_budget is not None and client.calls_made >= call_budget:
                    result.budget_exhausted = True
                    break
                try:
                    response = await client.get(call.endpoint, **call.params)
                except FinEdgeParameterError as exc:
                    # A rejected parameter combination, not a transient fault.
                    result.skipped += 1
                    record_task(
                        core,
                        run_id,
                        symbol=symbol,
                        endpoint=call.endpoint,
                        params=call.params,
                        status="skipped",
                        last_error=str(exc),
                    )
                    continue
                except FinEdgeError as exc:
                    result.failed += 1
                    result.errors.append(f"{symbol} {call.endpoint}: {exc}")
                    record_task(
                        core,
                        run_id,
                        symbol=symbol,
                        endpoint=call.endpoint,
                        params=call.params,
                        status="failed",
                        last_error=str(exc),
                    )
                    continue

                is_new = store_raw(raw, run_id, response)
                result.stored += int(is_new)
                result.unchanged += int(not is_new)

                try:
                    result.rows_written += _normalise_call(core, symbol, call, response.payload)
                except Exception as exc:  # noqa: BLE001 - one bad payload must not kill the run
                    result.failed += 1
                    result.errors.append(f"{symbol} {call.endpoint} normalise: {exc}")
                    logger.exception("normalise failed for %s %s", symbol, call.endpoint)
                    record_task(
                        core,
                        run_id,
                        symbol=symbol,
                        endpoint=call.endpoint,
                        params=call.params,
                        status="failed",
                        last_error=str(exc),
                    )
                    continue

                record_task(
                    core,
                    run_id,
                    symbol=symbol,
                    endpoint=call.endpoint,
                    params=call.params,
                    status="done",
                )

            result.symbols_done += 1
            if position % 10 == 0 or position == len(symbols):
                logger.info(
                    "%d/%d symbols, %d calls, %d rows",
                    result.symbols_done,
                    len(symbols),
                    client.calls_made,
                    result.rows_written,
                )
    finally:
        await client.aclose()

    result.calls_made = client.calls_made
    result.bytes_fetched = client.bytes_fetched
    finish_run(
        core,
        run_id,
        status="completed" if result.failed == 0 else "completed_with_errors",
        calls_made=result.calls_made,
        bytes_fetched=result.bytes_fetched,
        rows_written=result.rows_written,
    )
    return result

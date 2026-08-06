"""Ingestion worker CLI.

Phase 0 supports fetching one symbol's full endpoint matrix and the
universe-wide endpoints, storing every response in the Layer 1 raw archive.

    python -m app.ingest.worker fetch RELIANCE
    python -m app.ingest.worker universe
    python -m app.ingest.worker plan RELIANCE
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from app.db.engine import get_engine, get_raw_engine
from app.db.models import create_all
from app.finedge.client import (
    FinEdgeClient,
    FinEdgeError,
    FinEdgeParameterError,
)
from app.finedge.endpoints import Call, symbol_endpoint_matrix, universe_endpoints
from app.ingest.store import finish_run, record_task, start_run, store_raw
from app.logging_setup import configure_logging

logger = logging.getLogger("stocklens.ingest")


async def run_calls(calls: list[Call], *, job_kind: str, scope: dict | None = None) -> dict:
    """Execute a list of calls, storing each response and checkpointing each task."""
    core_engine = get_engine()
    raw_engine = get_raw_engine()
    create_all(core_engine, raw_engine)

    run_id = start_run(core_engine, job_kind=job_kind, scope=scope)
    stored = skipped = failed = 0

    client = FinEdgeClient()
    try:
        for index, call in enumerate(calls, start=1):
            label = f"{call.endpoint} {call.params or ''}".strip()
            try:
                response = await client.get(call.endpoint, **call.params)
            except FinEdgeParameterError as exc:
                # A 400 is a rejected parameter combination, not a transient
                # failure. Record it and move on rather than burning retries.
                failed += 1
                record_task(
                    core_engine,
                    run_id,
                    symbol=call.symbol or "",
                    endpoint=call.endpoint,
                    params=call.params,
                    status="skipped",
                    last_error=str(exc),
                )
                logger.info("[%d/%d] skipped %s: %s", index, len(calls), label, exc)
                continue
            except FinEdgeError as exc:
                failed += 1
                record_task(
                    core_engine,
                    run_id,
                    symbol=call.symbol or "",
                    endpoint=call.endpoint,
                    params=call.params,
                    status="failed",
                    last_error=str(exc),
                )
                logger.error("[%d/%d] failed %s: %s", index, len(calls), label, exc)
                continue

            is_new = store_raw(raw_engine, run_id, response)
            stored += int(is_new)
            skipped += int(not is_new)
            record_task(
                core_engine,
                run_id,
                symbol=call.symbol or "",
                endpoint=call.endpoint,
                params=call.params,
                status="done",
            )
            logger.info(
                "[%d/%d] %s %s (%d bytes, %.2fs)",
                index,
                len(calls),
                "stored" if is_new else "unchanged",
                label,
                response.size_bytes,
                response.elapsed_seconds,
            )
    finally:
        await client.aclose()

    status = "completed" if failed == 0 else "completed_with_errors"
    finish_run(
        core_engine,
        run_id,
        status=status,
        calls_made=client.calls_made,
        bytes_fetched=client.bytes_fetched,
        rows_written=stored,
    )
    return {
        "run_id": run_id,
        "status": status,
        "planned": len(calls),
        "calls_made": client.calls_made,
        "stored": stored,
        "unchanged": skipped,
        "failed": failed,
        "bytes_fetched": client.bytes_fetched,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stocklens-ingest")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="Fetch one symbol's full endpoint matrix")
    fetch.add_argument("symbol")

    sub.add_parser("universe", help="Fetch the universe-wide endpoints")

    plan = sub.add_parser("plan", help="Print the call plan without fetching")
    plan.add_argument("symbol")

    args = parser.parse_args(argv)
    configure_logging(
        level=logging.INFO if args.verbose or args.command != "plan" else logging.WARNING,
        # -v surfaces httpx's request lines; the redaction filter keeps the
        # token out of them either way.
        quiet_httpx=not args.verbose,
    )

    if args.command == "plan":
        calls = symbol_endpoint_matrix(args.symbol.upper())
        for call in calls:
            print(f"{call.endpoint} {call.params or ''}".strip())
        print(f"\n{len(calls)} calls planned for {args.symbol.upper()}")
        return 0

    if args.command == "fetch":
        symbol = args.symbol.upper()
        calls = symbol_endpoint_matrix(symbol)
        result = asyncio.run(run_calls(calls, job_kind="backfill", scope={"symbols": [symbol]}))
    else:
        calls = universe_endpoints()
        result = asyncio.run(run_calls(calls, job_kind="universe"))

    print("\n".join(f"{k}: {v}" for k, v in result.items()))
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

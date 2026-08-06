"""Ingestion jobs.

Job 1 (universe) and Job 2 (price) from docs/prd/06-data-model-and-ingestion.md.
Both are cheap: the universe sync is four calls and the price refresh is one call
that returns all 5,630 companies.
"""

from __future__ import annotations

import logging
from typing import Any

from app.db.engine import get_engine, get_raw_engine
from app.db.layer2 import create_layer2
from app.db.models import create_all
from app.finedge.client import FinEdgeClient, FinEdgeError
from app.ingest import layer2_store as l2
from app.ingest.normalise import (
    normalise_index_master,
    normalise_index_quotes,
    normalise_index_returns,
    normalise_quotes,
    normalise_symbols,
)
from app.ingest.store import finish_run, record_task, start_run, store_raw

logger = logging.getLogger("stocklens.jobs")


def _prepare() -> tuple[Any, Any]:
    core, raw = get_engine(), get_raw_engine()
    create_all(core, raw)
    create_layer2(core)
    return core, raw


async def _fetch_and_store(
    client: FinEdgeClient, core: Any, raw: Any, run_id: str, endpoint: str, **params: Any
) -> Any | None:
    """One call: fetch, archive the raw response, checkpoint the task."""
    try:
        response = await client.get(endpoint, **params)
    except FinEdgeError as exc:
        record_task(
            core,
            run_id,
            symbol="",
            endpoint=endpoint,
            params=params,
            status="failed",
            last_error=str(exc),
        )
        logger.error("failed %s: %s", endpoint, exc)
        return None
    store_raw(raw, run_id, response)
    record_task(core, run_id, symbol="", endpoint=endpoint, params=params, status="done")
    return response.payload


async def run_universe_sync() -> dict[str, Any]:
    """Job 1: symbol master, index master with constituents, index quotes and returns."""
    core, raw = _prepare()
    run_id = start_run(core, job_kind="universe")
    client = FinEdgeClient()
    written: dict[str, int] = {}

    try:
        payload = await _fetch_and_store(client, core, raw, run_id, "/api/v1/stock-symbols")
        if payload is not None:
            rows = normalise_symbols(payload)
            written["companies"] = l2.upsert_companies(core, rows)
            logger.info("symbol master: %d companies", written["companies"])

        payload = await _fetch_and_store(client, core, raw, run_id, "/api/v1/index/master")
        if payload is not None:
            indices, constituents = normalise_index_master(payload)
            idx, con = l2.replace_index_master(core, indices, constituents)
            written["indices"] = idx
            written["index_constituents"] = con
            logger.info("indices: %d with %d constituent links", idx, con)

        payload = await _fetch_and_store(
            client, core, raw, run_id, "/api/v1/index/market-price/daily-feed"
        )
        if payload is not None:
            written["index_quotes"] = l2.upsert_index_quotes(core, normalise_index_quotes(payload))

        payload = await _fetch_and_store(client, core, raw, run_id, "/api/v1/index/price-returns")
        if payload is not None:
            written["index_returns"] = l2.replace_index_returns(
                core, normalise_index_returns(payload)
            )
    finally:
        await client.aclose()

    finish_run(
        core,
        run_id,
        status="completed",
        calls_made=client.calls_made,
        bytes_fetched=client.bytes_fetched,
        rows_written=sum(written.values()),
    )
    return {"run_id": run_id, "calls_made": client.calls_made, "written": written}


async def run_price_refresh() -> dict[str, Any]:
    """Job 2: the whole universe in one call.

    `/api/v1/quote` with no symbol returns every company. This is what makes a
    daily screener refresh one request instead of 5,630.
    """
    core, raw = _prepare()
    run_id = start_run(core, job_kind="price")
    client = FinEdgeClient()

    written = 0
    try:
        payload = await _fetch_and_store(client, core, raw, run_id, "/api/v1/quote")
        if payload is not None:
            rows = normalise_quotes(payload)
            written = l2.upsert_quotes(core, rows)
            logger.info("quotes refreshed for %d companies", written)
    finally:
        await client.aclose()

    finish_run(
        core,
        run_id,
        status="completed",
        calls_made=client.calls_made,
        bytes_fetched=client.bytes_fetched,
        rows_written=written,
    )
    return {"run_id": run_id, "calls_made": client.calls_made, "quotes": written}

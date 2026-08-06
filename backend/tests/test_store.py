from __future__ import annotations

import json

from sqlalchemy import Engine, select

from app.db.models import ingestion_task, raw_response
from app.finedge.client import FinEdgeResponse
from app.ingest.store import (
    canonical_params,
    finish_run,
    load_raw,
    params_hash,
    raw_summary,
    record_task,
    run_summary,
    start_run,
    store_raw,
)


def _response(endpoint: str, payload: dict, params: dict | None = None) -> FinEdgeResponse:
    raw = json.dumps(payload).encode()
    return FinEdgeResponse(
        endpoint=endpoint,
        params=params or {},
        payload=payload,
        raw_bytes=raw,
        status_code=200,
        elapsed_seconds=0.1,
    )


class TestCanonicalParams:
    def test_key_order_does_not_change_the_hash(self) -> None:
        a = {"statement_type": "c", "period": "annual"}
        b = {"period": "annual", "statement_type": "c"}
        assert params_hash(a) == params_hash(b)

    def test_different_params_hash_differently(self) -> None:
        assert params_hash({"period": "annual"}) != params_hash({"period": "quarterly"})

    def test_canonical_form_is_compact_and_sorted(self) -> None:
        assert canonical_params({"b": 2, "a": 1}) == '{"a":1,"b":2}'


class TestStoreRaw:
    def test_stores_and_reads_back(self, engines: tuple[Engine, Engine]) -> None:
        _core, raw = engines
        run_id = "run-1"
        payload = {"RELIANCE": {"current_price": 1325}}
        assert store_raw(raw, run_id, _response("/api/v1/quote", payload)) is True
        assert load_raw(raw, "/api/v1/quote") == payload

    def test_identical_content_is_not_stored_twice(self, engines: tuple[Engine, Engine]) -> None:
        _core, raw = engines
        response = _response("/api/v1/quote", {"ITC": 1})
        assert store_raw(raw, "run-1", response) is True
        assert store_raw(raw, "run-2", response) is False

        with raw.connect() as conn:
            count = conn.execute(select(raw_response.c.id)).all()
        assert len(count) == 1

    def test_changed_content_is_stored_as_a_new_row(self, engines: tuple[Engine, Engine]) -> None:
        _core, raw = engines
        assert store_raw(raw, "r1", _response("/api/v1/quote", {"ITC": 1})) is True
        assert store_raw(raw, "r2", _response("/api/v1/quote", {"ITC": 2})) is True
        assert load_raw(raw, "/api/v1/quote") is not None

    def test_symbol_is_derived_from_per_symbol_paths(self, engines: tuple[Engine, Engine]) -> None:
        _core, raw = engines
        store_raw(raw, "r1", _response("/api/v1/company-profile/RELIANCE", {"name": "RIL"}))
        with raw.connect() as conn:
            symbol = conn.execute(select(raw_response.c.symbol)).scalar_one()
        assert symbol == "RELIANCE"

    def test_universe_paths_have_no_symbol(self, engines: tuple[Engine, Engine]) -> None:
        _core, raw = engines
        store_raw(raw, "r1", _response("/api/v1/stock-symbols", [{"symbol": "ITC"}]))
        with raw.connect() as conn:
            symbol = conn.execute(select(raw_response.c.symbol)).scalar_one()
        assert symbol == ""

    def test_payload_is_compressed(self, engines: tuple[Engine, Engine]) -> None:
        _core, raw = engines
        big = {"rows": [{"value": i} for i in range(2000)]}
        response = _response("/api/v1/quote", big)
        store_raw(raw, "r1", response)
        with raw.connect() as conn:
            stored, size = conn.execute(
                select(raw_response.c.payload, raw_response.c.size_bytes)
            ).one()
        assert len(stored) < size


class TestRunControl:
    def test_run_lifecycle(self, engines: tuple[Engine, Engine]) -> None:
        core, _raw = engines
        run_id = start_run(core, job_kind="backfill", scope={"symbols": ["ITC"]})
        finish_run(core, run_id, status="completed", calls_made=63, bytes_fetched=1234)

        runs = run_summary(core)
        assert runs[0]["id"] == run_id
        assert runs[0]["status"] == "completed"
        assert runs[0]["calls_made"] == 63

    def test_task_upsert_increments_attempts(self, engines: tuple[Engine, Engine]) -> None:
        core, _raw = engines
        run_id = start_run(core, job_kind="backfill")
        params = {"statement_type": "c"}
        record_task(
            core,
            run_id,
            symbol="ITC",
            endpoint="/x",
            params=params,
            status="failed",
            last_error="boom",
        )
        record_task(core, run_id, symbol="ITC", endpoint="/x", params=params, status="done")

        with core.connect() as conn:
            rows = conn.execute(select(ingestion_task.c.status, ingestion_task.c.attempts)).all()
        assert len(rows) == 1
        assert rows[0].status == "done"
        assert rows[0].attempts == 2

    def test_same_params_in_different_order_is_one_task(
        self, engines: tuple[Engine, Engine]
    ) -> None:
        core, _raw = engines
        run_id = start_run(core, job_kind="backfill")
        record_task(
            core,
            run_id,
            symbol="ITC",
            endpoint="/x",
            params={"a": 1, "b": 2},
            status="done",
        )
        record_task(
            core,
            run_id,
            symbol="ITC",
            endpoint="/x",
            params={"b": 2, "a": 1},
            status="done",
        )
        with core.connect() as conn:
            rows = conn.execute(select(ingestion_task.c.run_id)).all()
        assert len(rows) == 1


class TestSummary:
    def test_empty_summary_is_zeroed(self, engines: tuple[Engine, Engine]) -> None:
        _core, raw = engines
        summary = raw_summary(raw)
        assert summary["raw_responses"] == 0
        assert summary["last_fetched_at"] is None

    def test_summary_counts_responses_and_symbols(self, engines: tuple[Engine, Engine]) -> None:
        _core, raw = engines
        store_raw(raw, "r1", _response("/api/v1/company-profile/ITC", {"a": 1}))
        store_raw(raw, "r1", _response("/api/v1/company-profile/TCS", {"a": 2}))
        summary = raw_summary(raw)
        assert summary["raw_responses"] == 2
        assert summary["distinct_symbols"] == 2
        assert summary["uncompressed_bytes"] > 0

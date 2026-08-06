"""The one-job-at-a-time lock.

SQLite has a single writer, and two backfills would fight over it while doubling
the request rate against FinEdge. The lock has to hold against a job this process
did not start - the CLI, a script, a second worker - which an in-memory flag
cannot do.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.models import ingestion_run
from app.services import ingest
from app.services.errors import Conflict, NotFound


@pytest.fixture
def tmp_engine(engines):
    """The core database only; the lock never touches the raw store."""
    return engines[0]


@pytest.fixture(autouse=True)
def _clear_in_process_flag():
    """Each test starts with nothing claimed in this process."""
    ingest._release()
    yield
    ingest._release()


def _insert_run(engine, run_id: str, *, status: str, started: datetime, kind: str = "backfill"):
    with engine.begin() as conn:
        conn.execute(
            ingestion_run.insert().values(
                id=run_id,
                job_kind=kind,
                status=status,
                started_at=started.isoformat(),
            )
        )


def test_a_job_started_by_another_process_blocks_a_new_one(tmp_engine) -> None:
    # This is the case an in-memory flag misses entirely: the CLI backfill is
    # very much real to FinEdge and to SQLite, but invisible to this process.
    _insert_run(tmp_engine, "from-the-cli", status="running", started=datetime.now(UTC))

    with pytest.raises(Conflict) as caught:
        ingest._claim("new-run", tmp_engine)

    assert caught.value.context["run_id"] == "from-the-cli"
    assert "backfill" in caught.value.message


def test_a_finished_job_does_not_block(tmp_engine) -> None:
    _insert_run(tmp_engine, "done", status="completed", started=datetime.now(UTC))
    ingest._claim("new-run", tmp_engine)
    assert ingest.active_run(tmp_engine) == "new-run"


def test_an_abandoned_job_stops_blocking_after_a_day(tmp_engine) -> None:
    # A process killed mid-run leaves its row saying "running" forever. Without a
    # staleness rule the console would refuse every job from then on.
    long_ago = datetime.now(UTC) - ingest.STALE_RUN_AFTER - timedelta(minutes=1)
    _insert_run(tmp_engine, "killed", status="running", started=long_ago)

    ingest._claim("new-run", tmp_engine)
    assert ingest.active_run(tmp_engine) == "new-run"


def test_a_long_but_live_job_still_blocks(tmp_engine) -> None:
    # A full universe backfill legitimately runs for about eighteen hours, so the
    # staleness rule must not cut in before then.
    seventeen_hours = datetime.now(UTC) - timedelta(hours=17)
    _insert_run(tmp_engine, "still-going", status="running", started=seventeen_hours)

    with pytest.raises(Conflict):
        ingest._claim("new-run", tmp_engine)


def test_active_run_reports_a_job_this_process_did_not_start(tmp_engine) -> None:
    _insert_run(tmp_engine, "elsewhere", status="running", started=datetime.now(UTC))
    assert ingest.active_run(tmp_engine) == "elsewhere"


def test_releasing_a_stuck_run_lets_the_next_one_start(tmp_engine) -> None:
    _insert_run(tmp_engine, "wedged", status="running", started=datetime.now(UTC))

    result = ingest.release_stuck_run("wedged", engine=tmp_engine)
    assert result["cleared"] is True

    with tmp_engine.connect() as conn:
        row = (
            conn.execute(select(ingestion_run).where(ingestion_run.c.id == "wedged"))
            .mappings()
            .first()
        )
    assert row["status"] == "failed"
    assert "administrator" in row["error"]

    ingest._claim("new-run", tmp_engine)


def test_releasing_refuses_a_job_running_in_this_process(tmp_engine) -> None:
    # Marking a live job failed would leave it writing to tables the console
    # believes are free.
    _insert_run(tmp_engine, "mine", status="running", started=datetime.now(UTC))
    ingest._active["run_id"] = "mine"

    with pytest.raises(Conflict, match="not stuck"):
        ingest.release_stuck_run("mine", engine=tmp_engine)


def test_releasing_a_finished_run_is_refused(tmp_engine) -> None:
    _insert_run(tmp_engine, "already-done", status="completed", started=datetime.now(UTC))

    with pytest.raises(Conflict) as caught:
        ingest.release_stuck_run("already-done", engine=tmp_engine)
    assert caught.value.context["status"] == "completed"


def test_releasing_an_unknown_run_is_a_miss(tmp_engine) -> None:
    with pytest.raises(NotFound):
        ingest.release_stuck_run("no-such-run", engine=tmp_engine)

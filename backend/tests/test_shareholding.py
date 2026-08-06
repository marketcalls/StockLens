"""Shareholding pattern.

Two faults have hidden here. Shareholder counts are recorded per group and must
be summed - taking whichever group happened to carry one reported Reliance as
having 47 shareholders, the promoter count, against 4.6 million real ones. And a
group with no data renders as a row of dashes that reads as neither zero nor
unreported.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine

from app.db.engine import build_engine
from app.db.layer2 import create_layer2, shareholding
from app.ingest import layer2_store as l2
from app.services import company
from app.services.company import PERIOD_LIMIT

NOW = "2026-08-06T15:00:00+00:00"


@pytest.fixture
def db(tmp_path) -> Engine:
    engine = build_engine(tmp_path / "core.db")
    create_layer2(engine)
    l2.upsert_companies(engine, [{"symbol": "X", "name": "X Ltd", "updated_at": NOW}])
    return engine


def _hold(period: str, group: str, pct: float | None, holders: float | None = None) -> dict:
    return {
        "symbol": "X",
        "period_label": period,
        "group_name": group,
        "shareholding_pct": pct,
        "total_shareholders": holders,
    }


def test_shareholder_counts_are_summed_across_groups(db: Engine) -> None:
    l2.upsert(
        db,
        shareholding,
        [
            _hold("Jun 2026", "promoterAndPromoterGroup", 50.48, 47),
            _hold("Jun 2026", "publicShareholding", 49.52, 4_651_816),
        ],
    )
    result = company.shareholding_pattern("X", engine=db)
    holders = next(r for r in result["rows"] if r["label"] == "No. of Shareholders")
    assert holders["values"][-1] == 4_651_863


def test_a_group_with_no_data_in_view_is_dropped(db: Engine) -> None:
    # Reliance last reported non-promoter non-public in 2016 and nothing since,
    # so the row is dashes across every quarter anyone sees.
    l2.upsert(
        db,
        shareholding,
        [
            _hold("Jun 2026", "promoterAndPromoterGroup", 50.48),
            _hold("Jun 2026", "publicShareholding", 49.52),
            _hold("Jun 2026", "nonPromoterNonPublic", None),
        ],
    )
    labels = [r["label"] for r in company.shareholding_pattern("X", engine=db)["rows"]]
    assert "Non-promoter non-public" not in labels
    assert "Promoters" in labels


def test_a_group_that_does_report_is_kept(db: Engine) -> None:
    l2.upsert(
        db,
        shareholding,
        [
            _hold("Jun 2026", "promoterAndPromoterGroup", 8.15),
            _hold("Jun 2026", "nonPromoterNonPublic", 0.42),
        ],
    )
    labels = [r["label"] for r in company.shareholding_pattern("X", engine=db)["rows"]]
    assert "Non-promoter non-public" in labels


def test_only_the_most_recent_quarters_are_returned(db: Engine) -> None:
    # Reliance carries 41 quarters back to 2016.
    quarters = [f"{m} {y}" for y in range(2016, 2027) for m in ("Mar", "Jun", "Sep", "Dec")]
    l2.upsert(
        db,
        shareholding,
        [_hold(q, "promoterAndPromoterGroup", 50.0) for q in quarters],
    )
    result = company.shareholding_pattern("X", engine=db)
    assert len(result["headers"]) == PERIOD_LIMIT
    assert result["headers"][-1] == "Dec 2026"
    for row in result["rows"]:
        assert len(row["values"]) == PERIOD_LIMIT


def test_a_company_with_nothing_reports_unavailable(db: Engine) -> None:
    assert company.shareholding_pattern("X", engine=db)["available"] is False

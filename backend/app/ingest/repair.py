"""Re-apply normalisation rules to data already stored.

Normalisation decides what is a measurement and what is an absent figure, but it
only runs when a row is fetched. A rule added later leaves everything downloaded
before it untouched - and a long backfill keeps writing with whatever code it
started with, so a fix landed mid-run does not reach the rest of that run.

Every rule here mirrors one in app/ingest/normalise.py. If you change one, change
both, or the repair will undo what normalisation just did.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, text

# Price and size fields where zero means "not reported" rather than "nothing".
# Volume is deliberately absent: no trades is a real fact about a day.
ZERO_IS_ABSENT = (
    "current_price",
    "open_price",
    "high_price",
    "low_price",
    "high52",
    "low52",
    "market_cap",
    "shares",
)


def repair(engine: Engine) -> dict[str, Any]:
    """Apply every normalisation rule to rows already in the database."""
    changed: dict[str, int] = {}

    with engine.begin() as conn:
        # A share cannot trade at or below nothing. All-zero rows are
        # non-trading sessions; negative OHLC is pre-demerger history.
        changed["price_rows_removed"] = conn.execute(
            text('DELETE FROM price_daily WHERE "close" <= 0 OR "open" < 0 OR high < 0 OR low < 0')
        ).rowcount

        # A -100% change beside a missing price is computed from the price that
        # is not there. Cleared first, while the price is still zero to test.
        changed["quote_changes_cleared"] = conn.execute(
            text(
                "UPDATE quote SET change_pct = NULL"
                " WHERE change_pct = -100 AND (current_price IS NULL OR current_price <= 0)"
            )
        ).rowcount

        sets = ", ".join(f'"{f}" = NULLIF("{f}", 0)' for f in ZERO_IS_ABSENT)
        where = " OR ".join(f'"{f}" = 0' for f in ZERO_IS_ABSENT)
        changed["quote_rows_corrected"] = conn.execute(
            text(f"UPDATE quote SET {sets} WHERE {where}")
        ).rowcount

        # A live index cannot trade at zero times earnings, and none is worth
        # nothing. P/E and P/B absent together mark the whole block as absent.
        changed["index_valuations_cleared"] = conn.execute(
            text(
                "UPDATE index_quote_daily SET pe = NULL, pb = NULL, div_yield = NULL"
                " WHERE pe = 0 AND pb = 0"
            )
        ).rowcount
        changed["index_market_caps_cleared"] = (
            conn.execute(
                text("UPDATE index_quote_daily SET market_cap = NULL WHERE market_cap = 0")
            ).rowcount
            + conn.execute(
                text("UPDATE index_master SET market_cap = NULL WHERE market_cap = 0")
            ).rowcount
        )

    changed["total"] = sum(v for k, v in changed.items() if k != "total")
    return changed

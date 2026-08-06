"""Data quality checks over Layer 2.

Feeds the Admin data-quality dashboard (G1/G2 in the feature catalog) and runs
after every materialisation. Each check returns a count plus a small sample, so
an operator can see what is actually wrong rather than only that something is.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, func, select

from app.db.layer2 import company, index_constituent, price_daily, quote, statement_period

SAMPLE_SIZE = 10


@dataclass(frozen=True)
class Check:
    name: str
    severity: str  # info | warning | error
    count: int
    detail: str
    sample: list[str]

    @property
    def ok(self) -> bool:
        return self.count == 0


def _sample(values: list[str]) -> list[str]:
    return sorted(values)[:SAMPLE_SIZE]


def run_checks(engine: Engine) -> list[Check]:
    checks: list[Check] = []
    with engine.connect() as conn:
        symbols = {r[0] for r in conn.execute(select(company.c.symbol)).all()}
        quote_keys = {r[0] for r in conn.execute(select(quote.c.symbol)).all()}
        bse_codes = {r[0] for r in conn.execute(select(company.c.bse_code)).all() if r[0]}

        # The quote feed is keyed by ticker AND by BSE scrip code, and also
        # carries ETFs and rights entitlements. Treating its keys as the screener
        # universe would double-count every company that appears both ways.
        quote_only = quote_keys - symbols
        numeric = {s for s in quote_only if s.isdigit()}
        duplicates = numeric & bse_codes

        checks.append(
            Check(
                "quote_keys_outside_symbol_master",
                "info",
                len(quote_only),
                "Quote feed carries BSE scrip codes, ETFs and rights entitlements "
                "beyond the symbol master. The screener universe is the symbol "
                "master, so these are ignored rather than screened.",
                _sample(list(quote_only)),
            )
        )
        checks.append(
            Check(
                "companies_quoted_twice",
                "warning",
                len(duplicates),
                "Companies present in the quote feed under both their ticker and "
                "their BSE scrip code. Joining on the symbol master avoids "
                "double-counting them.",
                _sample(list(duplicates)),
            )
        )

        missing_quote = symbols - quote_keys
        checks.append(
            Check(
                "listed_without_a_quote",
                "warning",
                len(missing_quote),
                "In the symbol master but absent from the latest quote feed. "
                "Usually suspended or newly delisted.",
                _sample(list(missing_quote)),
            )
        )

        constituents = {r[0] for r in conn.execute(select(index_constituent.c.symbol)).all()}
        orphan_constituents = constituents - symbols
        checks.append(
            Check(
                "index_members_missing_from_symbol_master",
                "warning",
                len(orphan_constituents),
                "Index constituents with no symbol-master entry, so no "
                "fundamentals can be attached and index-scoped screens will "
                "silently omit them.",
                _sample(list(orphan_constituents)),
            )
        )

        no_classification = {
            r[0]
            for r in conn.execute(select(company.c.symbol).where(company.c.sector.is_(None))).all()
        }
        checks.append(
            Check(
                "companies_without_a_sector",
                "info",
                len(no_classification),
                "No sector classification yet. Populated by the company-profile "
                "call during backfill, so a high count before backfill is expected.",
                _sample(list(no_classification)),
            )
        )

        unknown_schema = conn.execute(
            select(func.count())
            .select_from(statement_period)
            .where(
                statement_period.c.statement_code == "pl",
                statement_period.c.schema_kind == "unknown",
            )
        ).scalar_one()
        checks.append(
            Check(
                "unclassified_statement_schema",
                "error",
                unknown_schema,
                "P&L periods whose schema family could not be determined. Each is "
                "a company whose statements cannot be rendered correctly.",
                [],
            )
        )

        # `<= 0` rather than `< 0`. Zero passed the original check and drew a
        # spike to the axis on every affected price chart.
        bad_prices = conn.execute(
            select(func.count()).select_from(price_daily).where(price_daily.c.close <= 0)
        ).scalar_one()
        checks.append(
            Check(
                "non_positive_close_price",
                "error",
                bad_prices,
                "A close price of zero or below is not a price. FinEdge emits "
                "all-zero rows for non-trading sessions; they are dropped at "
                "normalisation rather than stored.",
                [],
            )
        )

        implausible_change = conn.execute(
            select(func.count()).select_from(quote).where(func.abs(quote.c.change_pct) > 50)
        ).scalar_one()
        checks.append(
            Check(
                "implausible_daily_change",
                "warning",
                implausible_change,
                "Daily move beyond 50 percent. Legitimate for a newly listed or "
                "illiquid counter, worth a look otherwise.",
                [],
            )
        )

    return checks


def summary(engine: Engine) -> dict[str, Any]:
    checks = run_checks(engine)
    return {
        "checks": [
            {
                "name": c.name,
                "severity": c.severity,
                "count": c.count,
                "ok": c.ok,
                "detail": c.detail,
                "sample": c.sample,
            }
            for c in checks
        ],
        "errors": sum(1 for c in checks if c.severity == "error" and not c.ok),
        "warnings": sum(1 for c in checks if c.severity == "warning" and not c.ok),
    }

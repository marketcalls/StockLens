"""Statement schema discovery.

docs/prd/09-open-questions.md Q5 asks how many distinct statement schemas FinEdge
really has. The PRD assumed three (general, bank, insurance). This clusters
companies by the field set they actually return, so `schema_kind` is driven by
observed structure rather than a hardcoded industry list.

    python -m app.ingest.discover --sample-file symbols.txt
    python -m app.ingest.discover RELIANCE HDFCBANK HDFCLIFE

Uses the production FinEdge client, so requests are paced and retried. A
throwaway script without those protections produced false "no data" results by
reading transient failures as empty responses.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from app.finedge.client import FinEdgeClient, FinEdgeError
from app.logging_setup import configure_logging

logger = logging.getLogger("stocklens.discover")

STATEMENT_CODES = ("pl", "bs", "cf")

# Fields present in every schema, so they carry no signal about which one a
# company uses. Measured, not assumed - see the docstring above.
NON_DISCRIMINATING = frozenset(
    {"eps", "income", "period_end", "period_start", "result_date", "year"}
)


@dataclass
class SymbolSchema:
    """The field sets one company actually returns."""

    symbol: str
    fields: dict[str, frozenset[str]] = field(default_factory=dict)
    periods: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def signature(self, code: str = "pl") -> frozenset[str]:
        """Discriminating fields only, so incidental gaps do not split clusters."""
        return frozenset(self.fields.get(code, frozenset())) - NON_DISCRIMINATING

    @property
    def complete(self) -> bool:
        return not self.errors and all(self.periods.get(c, 0) > 0 for c in STATEMENT_CODES)


async def probe_symbol(client: FinEdgeClient, symbol: str) -> SymbolSchema:
    """Fetch each statement for one company, falling back standalone->consolidated.

    A company with no consolidated statements is normal (only 2,510 of 5,630
    carry `consolidated_ind`), so an empty consolidated response is a reason to
    try standalone, not a failure.
    """
    result = SymbolSchema(symbol=symbol)
    for code in STATEMENT_CODES:
        rows: list[dict[str, Any]] = []
        for statement_type in ("c", "s"):
            try:
                response = await client.get(
                    f"/api/v1/financials/{symbol}",
                    statement_type=statement_type,
                    statement_code=code,
                    period="annual",
                )
            except FinEdgeError as exc:
                # Record it rather than silently treating it as "no data".
                result.errors.append(f"{code}/{statement_type}: {exc}")
                continue
            payload = response.payload
            rows = payload.get("financials") or [] if isinstance(payload, dict) else []
            if rows:
                break
        result.periods[code] = len(rows)
        if rows:
            # Union across periods: early years can omit fields that later ones carry.
            keys: set[str] = set()
            for row in rows:
                keys.update(row.keys())
            result.fields[code] = frozenset(keys)
    return result


async def discover(symbols: list[str]) -> dict[str, Any]:
    client = FinEdgeClient()
    try:
        results = [await probe_symbol(client, s) for s in symbols]
    finally:
        await client.aclose()

    clusters: dict[frozenset[str], list[str]] = defaultdict(list)
    for r in results:
        if r.fields.get("pl"):
            clusters[r.signature("pl")].append(r.symbol)

    ordered = sorted(clusters.items(), key=lambda kv: -len(kv[1]))
    return {
        "symbols_probed": len(results),
        "symbols_with_pl": sum(1 for r in results if r.fields.get("pl")),
        "errors": {r.symbol: r.errors for r in results if r.errors},
        "field_counts": {
            r.symbol: {c: len(r.fields.get(c, ())) for c in STATEMENT_CODES} for r in results
        },
        "period_counts": {r.symbol: dict(r.periods) for r in results},
        "clusters": [
            {"size": len(members), "members": sorted(members), "fields": sorted(sig)}
            for sig, members in ordered
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stocklens-discover")
    parser.add_argument("symbols", nargs="*", help="Symbols to probe")
    parser.add_argument("--sample-file", help="File with one symbol per line")
    parser.add_argument("--out", help="Write the full report as JSON here")
    args = parser.parse_args(argv)

    configure_logging()
    symbols = [s.upper() for s in args.symbols]
    if args.sample_file:
        with open(args.sample_file) as fh:
            symbols += [line.strip().upper() for line in fh if line.strip()]
    if not symbols:
        parser.error("give at least one symbol or --sample-file")

    report = asyncio.run(discover(symbols))

    print(f"probed {report['symbols_probed']}, with P&L: {report['symbols_with_pl']}")
    if report["errors"]:
        print(f"errors on {len(report['errors'])} symbols:")
        for symbol, errs in report["errors"].items():
            print(f"  {symbol}: {errs[0]}")
    print(f"\ndistinct P&L schemas: {len(report['clusters'])}")
    for i, cluster in enumerate(report["clusters"], start=1):
        members = ", ".join(cluster["members"][:8])
        more = "" if len(cluster["members"]) <= 8 else f" (+{len(cluster['members']) - 8})"
        print(
            f"  {i}. {len(cluster['fields']):3d} fields, "
            f"{cluster['size']:3d} companies: {members}{more}"
        )

    if args.out:
        with open(args.out, "w") as fh:
            json.dump(report, fh, indent=1)
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

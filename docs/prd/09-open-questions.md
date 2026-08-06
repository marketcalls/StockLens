# 09 - Open Questions

Things that need a decision or an experiment before or during build. Ordered by how much
they would cost to get wrong.

---

## Blocking - resolve before the first full backfill

### Q1. What are the FinEdge rate limits?
**Unknown.** No documented limit, and no `X-RateLimit-*` headers on any response tested.
The full backfill is ~240,000 to 355,000 calls
([06 Job 6](06-data-model-and-ingestion.md#job-6---full-backfill-super-admin-on-demand)).
Running that at the wrong rate could get the key throttled or suspended.

**Action:** ask FinEdge directly, and independently run a controlled ramp test (1, then 5,
then 10, then 20 rps for short bursts) recording latency and error rate. Set the default
concurrency at half the observed ceiling. Until answered, default to 5 rps.

### Q2. Does the plan have a monthly call quota?
Related to Q1 but separate: a rate limit constrains speed, a quota constrains total volume.
If there is a monthly cap, a full backfill might consume it entirely and starve the daily
delta jobs.

**Action:** confirm with FinEdge. If a quota exists, the Super Admin call-budget control
(H4) becomes a hard requirement rather than a safety feature, and the backfill must be
splittable across billing periods.

### Q3. Is redistributing FinEdge data through a public website permitted?
StockLens serves FinEdge-derived data to anonymous visitors. That is redistribution.
Licence terms were not in the offline documentation set.

**Action:** confirm the licence terms before the site is publicly reachable. If
redistribution is restricted, the public tier may need to be narrowed - which would change
the entire access model in [04](04-roles-and-access.md).

---

## Important - resolve during Phase 1

### Q4. How many companies actually have complete data?
Verified on RELIANCE and HDFCBANK only. 2,510 of 5,630 carry `consolidated_ind = true`, but
we do not know how many of the remaining 3,120 have usable standalone statements, or how
sparse the small-cap tail is.

**Action:** during the backfill, record per-symbol completeness. If a large fraction of the
universe is empty, the screener should default to a minimum-data filter rather than showing
thousands of blank rows.

### Q5. How many distinct statement schemas are there really?
Confirmed: general (44 P&L fields) and bank (32 fields, entirely different). The field
reference guide mentions insurance as a third. There may be more - NBFCs, for example, may
follow the general schema, the bank schema, or a fourth.

**Action:** during normalisation, cluster companies by the field set actually returned rather
than assuming three variants. Drive `schema_kind` off observed structure, not a hardcoded
industry list.

### Q6. How stable is the sector classification naming?
FinEdge returns `sector = "Refineries & Marketing"` and `industry = "Petroleum Products"` for
RELIANCE, which inverts the conventional hierarchy. It is not clear whether this is
consistent across the universe or varies.

**Action:** extract the full distinct set of macro_sector / sector / industry / sub_industry
combinations during backfill and build the normalisation mapping from the actual data.
Admin override (G8) exists for the residue.

### Q7. What is the right peer set?
`/api/v1/peers/ITC` returned 4 entries, some obscure. `stock-search` by sector returned 6 for
Refineries & Marketing where the reference showed 9. Neither matches expectation.

**Action:** build peers from sub-industry plus market-cap band plus a liquidity floor, and
compare against the reference for 20 well-known companies before settling the rule.

### Q8. Do result-filing PDFs reliably match to quarters?
The reference shows a "Raw PDF" link per quarter. We have `corp-announcements` with symbol
and date filters, but no explicit quarter association.

**Action:** sample 50 companies and measure the match rate using announcement category plus
date proximity to `result_date`. If it is below ~80%, present the documents as a list rather
than a per-quarter link.

---

## Product decisions - needed before Phase 4

### Q9. Is the 25-row public cap the right number?
Chosen by analogy, not by evidence. Too low and public users bounce; too high and nobody
signs up.

**Action:** instrument it. Ship at 25, measure the signup rate against scroll depth, and
tune. Keep it a configuration value, not a constant.

### Q10. Should public users get any saved state at all?
An anonymous "session screen" that survives a page refresh via localStorage might increase
engagement enough to improve conversion, or might remove the reason to sign up.

**Recommendation:** allow localStorage-backed recently-viewed and one unsaved draft screen.
Everything durable requires an account.

### Q11. Email delivery provider?
Alerts and digests need transactional email. Not chosen.

**Action:** decide in Phase 4. Options are a hosted API (Resend, SES, Postmark) or SMTP.
Alerts are the main registered-user value, so this cannot be deferred past Phase 6.

### Q12. Does the account system need email verification at signup?
Adds friction to the conversion funnel, but alerts are useless without a verified address.

**Recommendation:** allow immediate signup with an unverified address, and require
verification only when the user first creates an alert or requests an export.

---

## Technical - resolve as encountered

### Q13. Where does the raw response archive live long-term?
The compressed archive is a few GB in `stocklens_raw.db`. It is valuable for re-derivation
and audit, but it will grow with every run.

**Current plan:** separate database file, prune to the last two versions per (symbol,
endpoint) weekly. Revisit if it exceeds 10 GB.

### Q14. What is the backup strategy for a SQLite deployment?
A single file is easy to back up but also a single point of failure.

**Action:** use SQLite's online backup API or `VACUUM INTO` on a schedule, to a separate
volume, plus a copy retained off-host. Test a restore before launch, not after an incident.

### Q15. Which `period` values are valid for which `statement_code`?
`period=ytd` is documented as allowed but returns `combination pl, ytd is invalid`.
`halfyearly` works for `pl`. The full valid matrix is unmapped.

**Action:** probe all 12 combinations per statement code during Phase 1 and encode the valid
matrix in `finedge/endpoints.py` so the backfill never wastes calls on invalid combinations.

### Q16. Can `daily-price-ratios` be fetched for the whole universe cheaply?
It is per-symbol only. Daily valuation for 5,630 companies means 5,630 calls per day, which
is far more expensive than the single-call quote refresh.

**Action:** ingest the historical series once during backfill, then compute daily P/E, P/B
and P/S ourselves from the universe quote plus our stored fundamentals. Only re-fetch the
FinEdge series periodically to check our computation has not drifted.

### Q17. Does the `quote` endpoint's no-symbol behaviour depend on plan tier?
The documentation says "Premium users get all symbols (no need to send this query
parameter)". Our key has it. The entire ingestion design depends on it.

**Action:** confirm this is a durable entitlement of the plan, not a trial. If it could be
withdrawn, design a fallback that batches 100 symbols per call (57 calls for the universe -
still workable, but worth knowing in advance).

### Q18. Timezone handling.
`tradetime` comes back as UTC (`2026-08-06T15:51:08Z`), announcement timestamps as naive
local strings (`2026-08-06 19:27:07`), and dates in several formats (`27-May-2026`,
`2026-08-06`, `20260331`).

**Action:** normalise everything to UTC at ingestion, store as ISO-8601 text, and render in
IST. Do not let more than one date format past the normalisation layer.

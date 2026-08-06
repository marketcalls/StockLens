# 08 - Roadmap

Six phases. Each ends with something demonstrable. The ordering is driven by one rule:
**get real data into SQLite before building anything on top of it**, because every later
decision depends on what the normalised data actually looks like.

---

## Phase 0 - Foundation

**Goal:** the repository runs, the API key works from code, one company's data is in SQLite.

- Project scaffold: FastAPI backend, Vite + React + TypeScript frontend, shadcn/ui installed
  with the light/dark theme provider working
- `.gitignore` covering `.env`, `*.db`, `__pycache__`, `node_modules`, `dist`
- Config layer reading `FINEDGE_API_KEY` from `.env` via Pydantic Settings
- FinEdge async client: auth, retry with backoff, 503 handling, token redaction in logs
- SQLite engine with the PRAGMA setup from [07](07-architecture-and-api.md), Alembic
  initialised
- Layer 1 `raw_response` table, and a CLI that fetches and stores one symbol's full endpoint
  matrix
- Health endpoint that reports FinEdge connectivity and database freshness

**Done when:** `python -m app.ingest.worker fetch RELIANCE` stores ~63 raw responses and
`GET /api/meta/freshness` reports them.

---

## Phase 1 - Data layer

**Goal:** all 5,630 companies present with quotes; a meaningful subset with full fundamentals.

- Layer 2 normalisation for every endpoint, including the general / bank / insurance schema
  split. This is the largest single piece of work in the project.
- Sector classification normalisation (fixing the inverted FinEdge naming from
  [02 §8](02-data-source-inventory.md#8-gaps-against-the-screenerin-reference-screenshots))
- Job 1 (universe), Job 2 (price), Job 4 (feeds and calendars) - all cheap, all daily
- Job 6 (backfill) with checkpointing, resume, rate control, call budget and dry-run
- Prioritised backfill: Nifty 500 and BSE 500 first, then by market cap descending
- Data quality checks feeding a plain report
- Layer 3 materialisation into `company_snapshot`

**Done when:** the backfill has completed for the top 500 companies and `company_snapshot`
has ~180 populated columns for them, with all 5,630 carrying live quote data.

**Risk:** FinEdge rate limits are unknown. Start the first backfill deliberately slow, watch
for 429s and sustained 5xx, and record the observed ceiling before increasing concurrency.

---

## Phase 2 - Public read surface

**Goal:** a stranger can look up any company and read its fundamentals. No accounts yet.

- Company search with FTS5 autocomplete
- Company page: header, key ratios strip, Pros/Cons, peer comparison, Quarterly Results,
  P&L with growth cards, Balance Sheet, Cash Flows, Ratios, Shareholding aggregates,
  Documents, corporate actions, segment revenue, price chart
- The shared `StatementTable` component with pinned first column, expandable rows,
  consolidated/standalone toggle and the three schema variants
- Market pages: index dashboard, index detail, results calendar, IPO calendar, corporate
  action calendar, holidays, announcement feed, movers, sector heatmap
- Freshness footer on every page

**Done when:** every section of the reference screenshots that our data supports renders
correctly for a general company, a bank, and a company with no consolidated statements.

---

## Phase 3 - Screener

**Goal:** the core product. Public, working, fast.

- Column catalog with names, aliases, units, types and sources
- Query parser and SQL compiler with strict identifier whitelisting
- StockLens computed columns (dividend yield, EV/EBITDA, price CAGR, DMAs, promoter pledge,
  Piotroski, Altman)
- ScreenerGrid: virtualised, sortable, column-configurable
- QueryEditor with autocomplete, plus the visual builder
- Index and sector universe filters
- 12 launch preset screens
- Result caching by normalised query hash, pre-warmed for presets
- Public 25-row cap enforced server-side, with the true total disclosed

**Done when:** p95 screener latency is under 400 ms on the full universe and every preset
returns a sensible list.

---

## Phase 4 - Accounts and workflow

**Goal:** the reason to sign up.

- Signup, login, sessions, password reset, argon2 hashing
- Role model with the `require_role` dependency and server-side result limits
- CLI bootstrap for the first Super Admin
- Saved screens with version history and public sharing
- Watchlists, private notes and tags, saved column preferences
- Comparison of up to 10 companies
- CSV and Excel export with per-role limits
- Registered-user depth unlocks: full 31 ratios, named shareholders, SBO, notes to accounts,
  valuation band charts
- Custom derived columns
- Personal read-only API keys

**Done when:** the permission matrix in [04](04-roles-and-access.md) is enforced end to end
and a modified client request cannot retrieve row 26 of a public screen.

---

## Phase 5 - Operations consoles

**Goal:** the platform runs itself, and Super Admin owns the data.

- Admin console: data quality matrix, stale report, targeted re-fetch, run history and task
  detail, user management, classification override, preset curation
- Super Admin console: full and scoped backfill with dry-run, run pause/resume/abort, live
  progress over server-sent events, schedule configuration, credential rotation with masked
  fingerprint, call budget and hard stops, raw response inspector, role assignment,
  re-materialisation, usage analytics
- Audit log for role changes and data-platform actions
- Job 3 (delta fundamentals) and Job 5 (staggered shareholding) running on schedule

**Done when:** a Super Admin can trigger, monitor, pause and resume a full universe backfill
from the browser, and the daily delta job keeps everything current without intervention.

---

## Phase 6 - Automation and depth

**Goal:** the product works for the user while they are not looking at it.

- All ten alert types, evaluated on the post-ingestion hook
- In-app alert inbox and email delivery
- Weekly digest
- Scheduled screen runs with entrant/exit diffs
- Screen backtesting, with the survivorship-bias caveat shown on every result
- Concall transcript search across the PDF corpus

---

## Sequencing rationale

**Why the data layer comes before any UI.** The bank/general/insurance schema split, the
inverted sector naming, and the 8-year rather than 12-year history are all things that change
component design. Discovering them while building the P&L table would mean rebuilding it.

**Why the screener comes after the company page.** The company page exercises every part of
the normalised model at depth for one symbol. Bugs surface there far more cheaply than in a
5,630-row grid.

**Why accounts come fourth, not first.** Nothing before Phase 4 needs a user. Building auth
early would mean building it against unfinished features.

**Why the full backfill is prioritised by index membership.** 500 companies cover the
overwhelming majority of what anyone searches for. The product is genuinely useful after a
few hours of backfill rather than after thirteen.

## Cross-phase, always on

- Every phase ships with tests for what it added
- Every FinEdge behaviour discovered in development gets written back into
  [02](02-data-source-inventory.md), which is the living record of what the API actually does
- No feature ships that implies data is fresher or deeper than it is

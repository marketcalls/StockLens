# 06 - Data Model and Ingestion

## Principle

FinEdge is a build-time dependency, never a read-time one. Every user request is served from
SQLite. If FinEdge is down, StockLens serves stale data with a freshness banner rather
than an error.

---

## Storage layout

Three layers.

### Layer 1 - Raw
Exactly what FinEdge returned, unmodified, one row per (symbol, endpoint, params, fetch time).

```sql
CREATE TABLE raw_response (
  id           INTEGER PRIMARY KEY,
  endpoint     TEXT NOT NULL,
  symbol       TEXT,
  params       TEXT NOT NULL,          -- JSON
  payload      BLOB NOT NULL,          -- zstd-compressed JSON
  content_hash TEXT NOT NULL,
  fetched_at   TEXT NOT NULL,          -- ISO-8601 UTC
  run_id       TEXT NOT NULL REFERENCES ingestion_run(id)
) STRICT;
CREATE INDEX idx_raw_symbol_endpoint ON raw_response (symbol, endpoint, fetched_at DESC);
CREATE UNIQUE INDEX idx_raw_dedupe ON raw_response (endpoint, symbol, content_hash);
```

Why keep raw: it makes the Super Admin response inspector (H8) trivial, lets us re-derive
everything after a mapping bug without re-fetching, and gives an audit trail for any number
a user disputes. The `content_hash` unique index means an unchanged re-fetch costs no storage.

**SQLite note.** Payloads are compressed before storage. The uncompressed raw corpus for a
full backfill is roughly 15 to 25 GB (dominated by `ownership-history` at up to 2.6 MB per
symbol); zstd brings that to a few GB. Raw responses live in a **separate database file**
(`stocklens_raw.db`) attached only by the ingestion worker, so the serving database stays
small and its page cache stays hot. Raw rows older than the last two runs per (symbol,
endpoint) are pruned on a weekly job.

### Layer 2 - Normalised
Typed, per-period tables. This is where the bank / general / insurance schema divergence is
resolved into a common surface plus schema-specific extension tables.

```
company                  symbol, name, nse_code, bse_code, consolidated_ind,
                         macro_sector, sector_normalised, industry, sub_industry,
                         schema_kind, website, description
statement_period         symbol, statement_type, statement_code, period_kind,
                         period_start, period_end, result_date, header, year
statement_line           period_id, field_name, value          -- long format, schema-agnostic
basic_financial          period_id, field_name, value
ratio                    symbol, statement_type, family, header, year, field_name, value
metric                   symbol, statement_type, family, field_name, value
price_daily              symbol, quote_date, open, high, low, close, volume
price_ratio_daily        symbol, quote_date, pe, pb, ptb, ps, pfcf
price_ratio_annual       symbol, statement_type, header, year, average_price, pe, pb, ptb, ps, pfcf
shareholding_pattern     symbol, period_label, group_name, holder_name, pct, shares, ...
shareholding_summary     symbol, period_label, total_shareholders, locked_in_pct, ...
corporate_action         symbol, action, ex_date, amount, subject, dividend_type
document                 symbol, category, description, announced_at, pdf_url, doc_kind
index_master             index_symbol, index_name, exchange, index_type, sub_type, market_cap
index_constituent        index_symbol, symbol
index_quote_daily        index_symbol, quote_date, close, change_pct, pe, pb, div_yield, ...
index_return             index_symbol, horizon, return_pct, as_of
segment_revenue          symbol, period_label, segment_name, field_name, value
calendar_result          symbol, expected_date
calendar_ipo             symbol, company_name, status, start_date, end_date, price_range, ...
calendar_holiday         trading_date, description, week_day
```

`statement_line` in long format (field_name, value) rather than a wide table is deliberate:
FinEdge has three schemas with 44, 32 and a third field set, and adding an insurance-only
field must not require a migration.

### Layer 3 - Serving
`company_snapshot` - the wide, one-row-per-symbol table the screener queries, described in
[05](05-screener-engine.md#storage). Rebuilt from Layer 2 by a materialisation step at the
end of every ingestion run. It is a cache; it can always be rebuilt.

---

## Ingestion jobs

### Job 1 - Universe sync (daily, ~4 calls)

| Step | Endpoint | Calls |
| --- | --- | --- |
| Symbol master | `/api/v1/stock-symbols` | 1 |
| Index master with constituents | `/api/v1/index/master` | 1 |
| Index daily quotes | `/api/v1/index/market-price/daily-feed` | 1 |
| Index returns | `/api/v1/index/price-returns` | 1 |

Runs weekly for the symbol and index master, daily for the quote and return feeds.

### Job 2 - Price refresh (daily, 1 call)

```
GET /api/v1/quote          # no symbol -> all 5,630 companies, 1.4 MB, 0.39 s
```

One call. Schedule for 30 minutes after market close, with a second run at 21:00 IST to
catch late settlement adjustments. This is the job that keeps the screener current.

### Job 3 - Delta fundamentals (daily)

The core efficiency mechanism.

```
GET /api/v1/refreshed-stocks?days=2
```

Returns only symbols whose `profit-loss`, `balance-sheet`, `cash-flow` or `quarterly` data
changed, with per-statement `last_updated_unix`. For each changed symbol, re-fetch only the
statements that actually moved:

```
for symbol, statements in refreshed:
    for stmt in statements:                    # pl | bs | cf | quarterly
        if stmt.last_updated_unix > our_last_ingested(symbol, stmt):
            fetch financials(symbol, stmt, both statement_types, relevant periods)
            fetch basic-financials(symbol, stmt, both statement_types)
    if any statement changed:
        fetch ratios(symbol, all 4 families)
        fetch financial-metrics(symbol, all 3 families)
        fetch annual-price-ratios(symbol)
```

Observed volume: `days=1` returned 62 KB - a small number of symbols. During peak results
season this will be hundreds per day; outside it, a handful. Either way it is two orders of
magnitude cheaper than a full sweep.

### Job 4 - Feeds and calendars (daily)

| Endpoint | Window |
| --- | --- |
| `/api/v1/corp-announcements` | `from_date` = yesterday |
| `/api/v1/credit-ratings` | daily feed |
| `/api/v1/investor-call-transcripts` | daily feed |
| `/api/v1/investor-presentations` | daily feed |
| `/api/v1/corporate-actions/all` | daily feed |
| `/api/v1/results-calendar` | daily |
| `/api/v1/ipo-calendar` | daily |
| `/api/v1/holidays-calendar` | monthly |

8 calls per day.

### Job 5 - Shareholding refresh (quarterly cadence, staggered)

Shareholding filings arrive in a burst 21 to 45 days after each quarter end. Rather than
polling all 5,630 symbols, poll on a staggered schedule during the filing window:
`shareholdings/pattern`, `/summary`, `/distribution`, `/ownership-current` per symbol.

`ownership-history` and `beneficial-owners` are heavy (2.6 MB and 476 KB for RELIANCE) and
are fetched **on demand and cached**, not swept. They back a registered-user feature with
low traffic; sweeping them for 5,630 companies would move gigabytes for little benefit.

### Job 6 - Full backfill (Super Admin, on demand)

The H1 capability. Runs the complete per-symbol matrix.

Per-symbol call budget:

| Endpoint | Variants | Calls |
| --- | --- | --- |
| company-profile | 1 | 1 |
| financials | 3 statement_codes x 2 types x 3 periods (annual, quarterly, ttm) | 18 |
| basic-financials | 3 codes x 2 types | 6 |
| ratios | 4 families x 2 types | 8 |
| financial-metrics | 3 families x 2 types | 6 |
| annual-price-ratios | 2 types | 2 |
| daily-price-ratios | 2 types | 2 |
| daily-quotes (2013+) | 1 | 1 |
| segment-revenue | 2 codes x 2 types x 2 periods | 8 |
| shareholdings pattern/summary/distribution/ownership-current | 4 | 4 |
| dividend + split/bonus/rights | 4 | 4 |
| peers | 1 | 1 |
| notes | 2 | 2 |
| **Total per symbol** | | **~63** |

Across 5,630 symbols: **~355,000 calls**. Restricting the consolidated variants to the 2,510
companies that actually have them cuts this to roughly **240,000**.

This is why the full backfill is Super Admin only and why it must be:

- **Resumable** - checkpointed per (symbol, endpoint), so a crash resumes rather than restarts
- **Rate-controlled** - configurable concurrency and inter-request delay, defaulting
  conservative because FinEdge publishes no rate limit and returns no rate-limit headers
- **Budgeted** - a hard call ceiling per run that aborts cleanly when hit
- **Prioritised** - Nifty 500 and BSE 500 constituents first, then by market cap descending,
  so the product becomes useful long before the run finishes
- **Dry-runnable** - report the call count and estimated duration before executing
- **Observable** - live progress, calls made, failures, current symbol, ETA

At a conservative 5 requests per second the full run is roughly 13 hours. It is a one-time
operation; after it, Job 3 keeps everything current.

---

## Job control model

```sql
CREATE TABLE ingestion_run (
  id             TEXT PRIMARY KEY,       -- uuid4 as text
  job_kind       TEXT NOT NULL,          -- universe | price | delta | feeds | shareholding | backfill
  scope          TEXT,                   -- JSON: symbol list, index, sector, cap band
  triggered_by   INTEGER REFERENCES app_user(id),
  status         TEXT NOT NULL,          -- queued | running | paused | completed | failed | aborted
  calls_made     INTEGER NOT NULL DEFAULT 0,
  call_budget    INTEGER,
  bytes_fetched  INTEGER NOT NULL DEFAULT 0,
  rows_written   INTEGER NOT NULL DEFAULT 0,
  started_at     TEXT,
  finished_at    TEXT,
  error          TEXT
) STRICT;

CREATE TABLE ingestion_task (
  run_id       TEXT NOT NULL REFERENCES ingestion_run(id) ON DELETE CASCADE,
  symbol       TEXT NOT NULL DEFAULT '',
  endpoint     TEXT NOT NULL,
  params_hash  TEXT NOT NULL,           -- sha256 of canonical params JSON
  params       TEXT,                    -- JSON, for display
  status       TEXT NOT NULL,           -- pending | in_flight | done | failed | skipped
  attempts     INTEGER NOT NULL DEFAULT 0,
  last_error   TEXT,
  completed_at TEXT,
  PRIMARY KEY (run_id, symbol, endpoint, params_hash)
) STRICT, WITHOUT ROWID;
CREATE INDEX idx_task_pending ON ingestion_task(run_id, status);
```

The task table is the checkpoint. Resume = select `pending` and `failed` tasks for the run.
The primary key uses `params_hash` rather than the raw JSON because SQLite compares TEXT
byte-wise and key ordering in a serialised JSON object is not guaranteed stable.

**Write concurrency.** SQLite allows one writer at a time. The backfill worker therefore
batches: fetch N responses concurrently in memory, then commit them in a single transaction.
A commit every 200 tasks keeps transactions short enough that the web tier's readers are
never blocked under WAL.

## FinEdge client requirements

1. **Retry with exponential backoff and jitter.** Transient `503`s were observed on
   `/api/v1/commodity-list` and `/api/v1/name-changes`. Retry 5xx and network errors; do not
   retry `400` or `401`.
2. **Do not retry parameter errors.** A `400` means a missing or invalid parameter. Log it
   as a task-level failure with the exact message and move on.
3. **No keep-alive assumption.** Responses carry `Connection: close`.
4. **Never log the token.** Redact the query string in all logging.
5. **Adaptive throttle.** Since no rate-limit headers exist, back off automatically on any
   429 or sustained 5xx and record the observed ceiling for the Super Admin dashboard.
6. **Content-hash short-circuit.** If the response hash matches the last stored one, skip
   the normalisation and materialisation work for that symbol.
7. **Timeout budget.** `ownership-history` took 0.61 s for 2.6 MB; set a generous per-request
   timeout (60 s) but a strict per-task one.

## Data quality checks (feed the Admin dashboard)

Run after every materialisation:

| Check | Failure surfaces as |
| --- | --- |
| Symbol has quote but no P&L | Incomplete on the data quality matrix |
| `consolidated_ind = true` but consolidated statements empty | Warning |
| Balance sheet does not balance (assets != equity + liabilities) | Error, block materialisation for that symbol |
| Latest `result_date` older than expected given `results-calendar` | Stale data report |
| Ratio present but underlying statement missing | Warning |
| Market cap differs materially from `shares` x `current_price` | Warning |
| Sector classification missing or unmapped | Admin override queue (G8) |
| Percent field outside plausible range | Error |

## Freshness contract shown to users

Every page footer states the actual timestamp of the data it shows:

- Price data: as of `tradetime` from the quote feed
- Fundamentals: as of the latest `result_date` for that company
- Shareholding: as of the latest filed quarter label

No page implies data is fresher than it is.

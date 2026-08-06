# 05 - Screener Engine

## Model

A screen is a boolean expression over per-company scalar values, evaluated against a
denormalised "latest snapshot" table in SQLite. Every column in that table is one of:

- a **quote** field, refreshed daily from one API call
- a **fundamental** field, refreshed when the company files
- a **derived** field, computed by us at ingestion time

No screener query touches FinEdge. Query latency is a SQLite problem, not a network one.

## Query language

Modelled on the reference product's syntax, which users already know.

```
Market Capitalization > 5000 AND
Price to Earning < 20 AND
Return on capital employed > 15 AND
Debt to equity < 0.5 AND
Sales growth 5Years > 12
```

### Grammar

```
query      := expr
expr       := term (("AND" | "OR") term)*
term       := "(" expr ")" | "NOT" term | comparison | membership
comparison := operand op operand
operand    := column | number | arithmetic
arithmetic := operand ("+" | "-" | "*" | "/") operand
op         := ">" | "<" | ">=" | "<=" | "=" | "!="
membership := column "IN" "(" value ("," value)* ")"
column     := <identifier from the column catalog, case-insensitive, space-tolerant>
```

### Supported forms

| Form | Example |
| --- | --- |
| Threshold | `Return on equity > 15` |
| Range | `Price to Earning > 10 AND Price to Earning < 25` |
| Column-to-column | `Current price < Book value` |
| Arithmetic | `Market Capitalization / Sales < 3` |
| Cross-period | `Net profit latest quarter > Net profit preceding year quarter` |
| Set membership | `Sector IN ("Banks", "Finance")` |
| Index scope | `Index = "Nifty 50"` |
| Negation | `NOT (Promoter pledge > 0)` |

### Units convention

Follows the reference product so pasted queries work:
- Money columns are in **Rs. Crore**
- Percentage columns are in **percent**, not fractions - `Return on equity > 15` means 15%.
  FinEdge returns `0.0827`; ingestion multiplies by 100 and stores percent.
- Ratio columns are unitless - `Debt to equity < 0.5`

## Column catalog

Roughly 180 screenable columns. Full field names are enumerated in
[02 §6](02-data-source-inventory.md#6-field-catalog); this is the grouping and count.

| Group | Columns | Source | Refresh |
| --- | ---: | --- | --- |
| Price and market | 11 | `quote` | Daily |
| Valuation | 5 | `daily-price-ratios` | Daily |
| Valuation, historical percentile | 5 | computed from daily series | Daily |
| P&L, latest annual | 44 | `financials` pl annual | On filing |
| P&L, latest quarter | 44 | `financials` pl quarterly | On filing |
| P&L, TTM | 44 | `financials` pl ttm | On filing |
| Balance sheet | ~40 | `financials` bs | On filing |
| Cash flow | ~35 | `financials` cf | On filing |
| Derived aggregates | 47 | `basic-financials` | On filing |
| Profitability ratios | 11 | `ratios` pr | On filing |
| Leverage ratios | 7 | `ratios` le | On filing |
| Liquidity ratios | 3 | `ratios` li | On filing |
| Efficiency ratios | 10 | `ratios` ef | On filing |
| Growth metrics 3Y / 5Y | 28 | `financial-metrics` gr | On filing |
| Average metrics 3Y / 5Y | 24 | `financial-metrics` av | On filing |
| Cumulative metrics | 4 | `financial-metrics` cu | On filing |
| Shareholding | ~12 | `shareholdings/*` | Quarterly |
| Classification and membership | 6 | `company-profile`, `index/master` | Weekly |
| StockLens computed | ~15 | our own | Daily |

Bank and insurance companies expose a different P&L column set. Screener columns that do not
apply to a company's schema evaluate as NULL and the company is excluded from that
comparison, not silently treated as zero.

### StockLens computed columns

Columns FinEdge does not provide but we can derive, which are worth having because they are
commonly screened on:

| Column | Derivation |
| --- | --- |
| Dividend Yield | latest 12-month dividend / current price |
| Enterprise Value | market cap + `totalDebt` - `totalCash` |
| EV / EBITDA | derived from the above and `ebitda` |
| Earnings Yield | inverse of P/E |
| Price CAGR 1Y / 3Y / 5Y / 10Y | from `daily-quotes` |
| Distance from 52-week high | `(high52 - price) / high52` |
| Distance from 52-week low | `(price - low52) / low52` |
| 50 DMA, 200 DMA, and price relative to each | from `daily-quotes` |
| Average daily traded value, 30 day | from `daily-quotes` |
| P/E percentile vs own 5-year history | from `daily-price-ratios` |
| Promoter holding change QoQ / YoY | from `shareholdings/distribution` |
| Promoter pledge % | from `shareholdings/ownership-current` |
| FII / DII holding change | from `shareholdings/distribution` |
| CFO / PAT | `operatingCashFlow` / `profitLossForPeriod` |
| Piotroski F-Score | 9 binary tests, all inputs available |
| Altman Z-Score | all inputs available |

The Piotroski and Altman scores are worth building because they are single-number screens
that beginners recognise and every input is already ingested.

## Execution

### Storage
One wide table, `company_snapshot`, one row per symbol, one column per screenable field.
5,630 rows. At ~180 REAL columns this is a few megabytes - the whole table sits in SQLite's
page cache after the first query.

```sql
CREATE TABLE company_snapshot (
  symbol            TEXT PRIMARY KEY,
  name              TEXT NOT NULL,
  macro_sector      TEXT,
  sector_normalised TEXT,
  industry          TEXT,
  sub_industry      TEXT,
  schema_kind       TEXT NOT NULL,   -- 'general' | 'bank' | 'insurance'
  market_cap        REAL,
  current_price     REAL,
  pe                REAL,
  roe               REAL,
  -- ... ~180 columns
  updated_at        TEXT NOT NULL    -- ISO-8601 UTC
) STRICT;

-- SQLite has no array type; index membership is a junction table
CREATE TABLE snapshot_index_membership (
  symbol       TEXT NOT NULL REFERENCES company_snapshot(symbol) ON DELETE CASCADE,
  index_symbol TEXT NOT NULL,
  PRIMARY KEY (symbol, index_symbol)
) STRICT, WITHOUT ROWID;
CREATE INDEX idx_membership_by_index ON snapshot_index_membership(index_symbol);
```

### Compilation
The parser produces an AST; the compiler emits a parameterised SQL `WHERE` clause against
`company_snapshot`. Column identifiers resolve through a catalog table so no user input ever
reaches SQL as an identifier - only bound parameters and whitelisted column names. Arithmetic
is emitted as SQL arithmetic with explicit NULL guards. `Index = "Nifty 50"` compiles to an
`EXISTS` against `snapshot_index_membership` rather than an array containment operator.

### Indexing
Indexes on the 25 most-screened columns (`market_cap`, `pe`, `pb`, `roe`, `roce`,
`debt_to_equity`, growth columns), plus a partial index `WHERE market_cap IS NOT NULL`.
A full scan of 5,630 rows in SQLite is roughly 2 ms, so most queries need no index at all -
over-indexing would cost more on write than it saves on read.

### SQLite configuration
```
PRAGMA journal_mode = WAL;       -- concurrent readers during ingestion writes
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA cache_size = -64000;      -- 64 MB page cache
PRAGMA mmap_size = 268435456;    -- 256 MB
```

WAL mode is what makes SQLite viable here: the nightly ingestion writes while the web tier
keeps serving reads. There is exactly one writer (the ingestion worker) and many readers
(the API), which is precisely SQLite's sweet spot. See
[07 §Why SQLite works](07-architecture-and-api.md#why-sqlite-works-for-this) for the sizing
argument and the migration trigger.

### Caching
Normalise the query (whitespace, case, operand ordering), hash it, and cache the result
symbol list. Preset screens are pre-warmed after each daily refresh. Cache invalidates on
snapshot update.

### Result payload
The result grid returns the symbol list plus the requested display columns. Column selection
is separate from the filter expression, so changing displayed columns does not re-run the
filter.

### Limits enforced server-side
- Public: 25 rows returned, total count disclosed truthfully, 20 queries per session per IP
- User: uncapped rows, paginated at 100 per page
- Query complexity ceiling: 40 comparison nodes, to bound worst-case planning cost

## Preset screens for launch

Each is a real query over columns confirmed available.

| Name | Query sketch |
| --- | --- |
| Low PE, high ROCE | `Price to Earning < 20 AND Return on capital employed > 20 AND Market Capitalization > 1000` |
| Debt-free compounders | `Debt to equity < 0.1 AND Sales growth 5Years > 15 AND Profit growth 5Years > 15` |
| Dividend champions | `Dividend Yield > 3 AND Dividend payout 3Yr Avg > 25 AND Return on equity > 15` |
| Quality at a reasonable price | `Return on equity 5Yr Avg > 18 AND Price to Earning < 25 AND Debt to equity < 0.5` |
| Cash generators | `CFO / PAT > 1 AND Free cash flow > 0 AND FCF as pct of revenue 3Yr Avg > 8` |
| Improving working capital | `Cash conversion cycle < 0 AND Sales growth 3Years > 10` |
| Near 52-week low, still profitable | `Distance from 52 week low < 10 AND Return on equity > 12 AND Debt to equity < 1` |
| Promoter pledge risk | `Promoter pledge > 10` |
| High Piotroski | `Piotroski F-Score >= 8` |
| Turnaround candidates | `Net profit latest quarter > 0 AND Net profit preceding year quarter < 0` |
| Nifty 50 value | `Index = "Nifty 50" AND Price to Earning < Sector median PE` |
| Small cap growth | `Market Capitalization < 5000 AND Market Capitalization > 500 AND Sales growth 3Years > 20` |

## Backtesting (registered users, later phase)

Because we hold dated fundamentals (`period_end`, `result_date` on every row) and 13 years of
daily prices, a screen can be re-evaluated as of a past date.

Mechanics:
1. Reconstruct `company_snapshot` as of date D using only rows with `result_date <= D` and
   the price series value on D
2. Evaluate the query against that reconstruction
3. Compute forward returns for the resulting basket at 1, 3, 6 and 12 months

Honest constraints to surface in the UI:
- Fundamentals only reach back 8 years for annual and 5 for cash flow, so backtests before
  FY2019 are not possible on P&L-based screens
- Survivorship: delisted companies are not in the current symbol master, so historical
  baskets are biased upward. This must be stated on every backtest result, not buried.

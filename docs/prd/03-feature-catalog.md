# 03 - Feature Catalog

Every feature listed here is backed by data verified present in FinEdge. Features that the
reference product has but our data cannot support are recorded in
[02, section 8](02-data-source-inventory.md#8-gaps-against-the-screenerin-reference-screenshots)
rather than promised here.

Access column key: **P** = public, **U** = registered user, **A** = admin, **S** = super admin.

---

## A. Discovery and search

| # | Feature | Data source | Access |
| --- | --- | --- | --- |
| A1 | Instant company autocomplete - type "rel", get ranked matches by name and symbol | `stock-symbols` (5,630, cached in SQLite + FTS5 index) | P |
| A2 | "Search everywhere" - fall through to matching announcements, sectors, and screen names | local index | P |
| A3 | Landing page "Or analyse:" chips - rotating set of interesting companies | curated + computed (largest movers, results today) | P |
| A4 | Browse by sector / industry / sub-industry / macro-sector | `company-profile` classifications, `stock-search` | P |
| A5 | Browse by index - all 239 indices with constituent lists | `index/master.constituents` | P |
| A6 | Recently viewed companies | localStorage for public, server-side for users | P / U |

**A1 detail.** The whole symbol master is 649 KB. It is loaded into SQLite once and served
from an FTS5 index, so autocomplete never touches FinEdge. Ranking: exact symbol match,
then prefix match on name, then trigram similarity, tie-broken by market cap descending.

---

## B. Company analysis page

This is the deepest surface and mirrors the reference screenshots section by section.

### B1. Header block
- Company name, symbol, NSE and BSE codes, website link
- Current price, day change %, day open/high/low, volume
- Market cap, 52-week high and low with a position marker
- Sector breadcrumb: macro-sector > industry > sector > sub-industry (normalised, see 02 §8)
- Index membership badges: "BSE Sensex", "Nifty 50", "BSE 500", "show all"
- Business description from `company-profile`

Sources: `quote`, `company-profile`, `index/master`. Access: **P**

### B2. Key ratios strip
Market Cap, Current Price, High/Low, Stock P/E, Book Value, Dividend Yield, ROCE, ROE,
Face Value, Price to Book, Price to Sales, EV/EBITDA.

Sources: `quote`, `daily-price-ratios` (pe, pb, ps, pfcf), `basic-financials` bs
(`bookValuepershare`, `adjustedFaceValue`), `ratios` pr (`returnOnCapital`, `returnOnEquity`),
`dividend`. Access: **P**

### B3. Pros and Cons (machine generated)
Deterministic rule engine over ingested ratios. Every statement carries the rule that fired
and the value that triggered it. Labelled as machine-generated, matching the reference.

Example rules, all computable from ingested fields:

| Type | Rule | Field |
| --- | --- | --- |
| Con | Low return on equity of X% over last 3 years | `roe3yearsAvg` < 0.12 |
| Con | Dividend payout has been low at X% of profits | `dividendPayoutPct3YrsAvg` < 0.15 |
| Con | Promoter holding has decreased over last N quarters | shareholding distribution trend |
| Con | High debtor days of X | `debtorDays` > 90 |
| Con | Company has high debt to equity of X | `totalDebtToEquity` > 1.5 |
| Con | Promoters have pledged X% of their holding | `pledgedSharesPct` > 0 |
| Con | Interest coverage is low at X | `interestCoverage` < 2 |
| Pro | Almost debt free | `totalDebtToEquity` < 0.1 |
| Pro | Healthy dividend payout of X% | `dividendPayoutPct3YrsAvg` > 0.30 |
| Pro | Good profit growth of X% CAGR over 5 years | `netIncomeGrowth5years` > 0.20 |
| Pro | Strong ROE track record, 5-year average X% | `roe5yearsAvg` > 0.20 |
| Pro | Company has been maintaining healthy CFO/PAT | `operatingCashFlow` vs `profitLossForPeriod` |
| Pro | Improving working capital cycle | `cashConversionCycle` trend |

Access: **P**

### B4. Peer comparison table
Sortable table of sector peers with S.No, Name, CMP, P/E, Market Cap, Div Yield,
NP Qtr, Qtr Profit Var %, Sales Qtr, Qtr Sales Var %, ROCE %, plus a median row.

Peer set is **our own** construction (same sub-industry, market-cap band, minimum liquidity),
seeded by `peers/{symbol}` - see the caveat in 02 §8.

"Edit columns" lets the viewer swap in any screener column. Public users get the default
column set; registered users can save their column preference per sector.

Sources: `quote`, `daily-price-ratios`, `financials` quarterly, `ratios`, `dividend`.
Access: **P** (edit columns transient) / **U** (saved column sets)

### B5. Quarterly Results
33 quarters of Sales, Expenses, Operating Profit, OPM %, Other Income, Interest,
Depreciation, Profit before tax, Tax %, Net Profit, EPS.

Field mapping (general schema):

| Row | FinEdge field |
| --- | --- |
| Sales | `revenueFromOperations` |
| Expenses | `operatingExpenses` (basic-financials) |
| Operating Profit | `operatingProfit` / `ebit` |
| OPM % | `operatingMargin` |
| Other Income | `otherIncome` |
| Interest | `financeCosts` |
| Depreciation | `depreciationAndAmortisation` |
| Profit before tax | `profitBeforeTax` |
| Tax % | `effectiveTaxRate` |
| Net Profit | `profitLossForPeriod` |
| EPS in Rs | `eps` |

Controls: Consolidated / Standalone toggle (`statement_type` c or s), expandable "+" rows
that drill into constituent lines, "Product Segments" button, per-quarter Raw PDF link.

Bank and insurance companies render a different row set (see 02 §6.3).

Sources: `financials` pl quarterly, `basic-financials`, `ratios` pr. Access: **P**

### B6. Profit & Loss (annual)
8 years plus TTM, same row structure as B5 with Dividend Payout % added.
Followed by the four growth cards:

| Card | Available horizons | Source |
| --- | --- | --- |
| Compounded Sales Growth | 5Y, 3Y, TTM | `revenueGrowth5years`, `revenueGrowth3years`, computed TTM |
| Compounded Profit Growth | 5Y, 3Y, TTM | `netIncomeGrowth5years`, `netIncomeGrowth3years`, computed |
| Stock Price CAGR | 10Y, 5Y, 3Y, 1Y | computed from `daily-quotes` (13 years available) |
| Return on Equity | 5Y, 3Y, Last Year | `roe5yearsAvg`, `roe3yearsAvg`, `returnOnEquity` |

The 10-year fundamental horizons in the reference are not shown, because the data does not
exist. This is a deliberate, labelled omission.

Sources: `financials` pl annual, `basic-financials` pl, `financial-metrics` gr and av.
Access: **P**

### B7. Balance Sheet
8 years of Equity Capital (`shareCapital`), Reserves (`totalReserves`), Borrowings
(`borrowingsCurrent` + `borrowingsNoncurrent`), Other Liabilities, Total Liabilities,
Fixed Assets, CWIP (`capitalWorkInProgress`), Investments, Other Assets, Total Assets,
with expandable "+" detail rows and a Corporate Actions button.

Sources: `financials` bs, `basic-financials` bs. Access: **P**

### B8. Cash Flows
5 years of Cash from Operating / Investing / Financing Activity, Net Cash Flow,
Free Cash Flow (`fcf`), CFO/OP ratio.

Sources: `financials` cf, `basic-financials` cf. Access: **P**

### B9. Ratios table
Debtor Days, Inventory Days, Days Payable, Cash Conversion Cycle, Working Capital Days -
a direct one-to-one mapping onto `ratios?ratio_type=ef`. Extended with the profitability,
leverage and liquidity families behind a "show all ratios" expander.

Access: **P** (core rows) / **U** (full 31-ratio expansion)

### B10. Shareholding Pattern
41 quarters of Promoters %, FIIs %, DIIs %, Government %, Public %, No. of Shareholders,
with a Quarterly / Yearly toggle and expandable "+" rows into named holders.

Additional depth FinEdge gives us that the reference does not surface prominently:
- **Promoter pledge %** (`pledgedSharesPct`) - a genuinely useful screening signal
- Locked-in shares %
- Significant Beneficial Owners disclosures
- Full named-holder history

Sources: `shareholdings/pattern`, `/summary`, `/distribution`, `/ownership-current`,
`/ownership-history`, `/beneficial-owners`. Access: **P** (aggregate) / **U** (named holders,
SBO, full history)

### B11. Documents
- Announcements, filterable by Recent / Important / Search / All
- Credit rating actions with the rating agency PDF
- Concall transcripts and investor presentations by quarter
- Annual reports (best-effort, derived from announcement categories)

Every row carries a direct PDF link from the exchange archive.

Sources: `corp-announcements?symbol=X&from_date&to_date`, `credit-ratings`,
`investor-call-transcripts`, `investor-presentations`. Access: **P**

### B12. Price chart
13 years of daily OHLCV with volume, overlays for 50/200 DMA, and event markers for
dividends, splits, bonuses and result dates.

A second chart mode plots **valuation over time** - the daily P/E, P/B, P/S and P/FCF series
against their own 5-year median band. This is a differentiator: FinEdge gives us a daily
valuation series, which most free tools do not have.

Sources: `daily-quotes`, `daily-price-ratios`, `corporate-actions`. Access: **P** (price) /
**U** (valuation bands, overlays)

### B13. Revenue by segment
Per-segment revenue and PBT with a share-of-total chart across periods.

Source: `segment-revenue`. Access: **P**

### B14. Notes to accounts
Management notes attached to filed results, rendered from the filing text.

Source: `notes`. Access: **U** - low traffic value, high page weight, good signup incentive

### B15. Corporate actions history
Dividend history with amounts, types and ex-dates; split, bonus and rights history.

Sources: `dividend`, `corporate-actions/{split|bonus|rights}`. Access: **P**

---

## C. Screener

The full query language, column catalog and execution model are specified in
[05 - Screener engine](05-screener-engine.md). Feature-level summary:

| # | Feature | Access |
| --- | --- | --- |
| C1 | Free-text query language: `Market Capitalization > 500 AND Return on equity > 15 AND Debt to equity < 0.5` | P |
| C2 | ~180 screenable columns across price, valuation, P&L, balance sheet, cash flow, ratios, growth, shareholding | P |
| C3 | Results grid with sortable columns and pagination | P (capped) / U (uncapped) |
| C4 | Preset public screens - "Low PE high ROCE", "Debt free growth", "Piotroski style", "Dividend champions", "52-week low value", "Promoter pledge risk" | P |
| C5 | Query builder UI for users who do not want to write the query text | P |
| C6 | Restrict universe to an index (Nifty 50, BSE 500, ...) or a sector | P |
| C7 | Custom columns - define a derived column with an expression, e.g. `EBITDA / Enterprise Value` | U |
| C8 | Save a screen with a name and description | U |
| C9 | Screen versioning and change history | U |
| C10 | Export results to CSV or Excel | U |
| C11 | Share a screen by public link | U |
| C12 | Run a saved screen on a schedule and get emailed the diff (entrants and exits) | U |
| C13 | Backtest a screen: what did this screen return 1 / 3 / 5 years ago, and how did those names perform | U |
| C14 | Feature a screen on the public presets list | A |

**C13 note.** This is only possible because FinEdge gives daily price history from 2013 and
annual fundamentals with `period_end` on every row. It is the single most compelling reason
a serious user would create an account. It is also the most expensive feature to build -
scheduled for a later phase in [08](08-roadmap.md).

---

## D. Watchlists and portfolio tracking (registered only)

| # | Feature | Access |
| --- | --- | --- |
| D1 | Multiple named watchlists | U |
| D2 | Watchlist as a screener result set - apply any column set to it | U |
| D3 | Per-company private notes and tags | U |
| D4 | Side-by-side comparison of up to 10 companies across any columns | U |
| D5 | Watchlist results-calendar view - who reports when | U |
| D6 | Import a watchlist from CSV | U |
| D7 | Consolidated document feed for watchlist companies only | U |

D4 is worth calling out: comparing arbitrary companies (not just sector peers) across any of
180 columns is straightforward for us because everything is one table in SQLite, and it is
a feature the reference product gates.

---

## E. Alerts and notifications (registered only)

All alert evaluation runs against our own database on the post-ingestion hook, so alerts
cost nothing extra in FinEdge calls.

| # | Alert | Trigger source |
| --- | --- | --- |
| E1 | Results declared for a watchlist company | `financials` new `result_date` |
| E2 | Upcoming results date for a watchlist company | `results-calendar` |
| E3 | New announcement in a chosen category | `corp-announcements` |
| E4 | Credit rating action | `credit-ratings` |
| E5 | Concall transcript or investor presentation published | `investor-call-transcripts`, `investor-presentations` |
| E6 | Dividend / split / bonus ex-date approaching | `corporate-actions` |
| E7 | Shareholding pattern changed - promoter stake or pledge moved | `shareholdings/distribution`, `ownership-current` |
| E8 | Price crossed a level, or hit a 52-week high or low | `quote` |
| E9 | Valuation alert - P/E fell below its own 5-year median | `daily-price-ratios` |
| E10 | A saved screen's membership changed | screener diff |

Delivery: in-app inbox and email. Digest frequency configurable per alert type.

---

## F. Market-wide pages

| # | Feature | Data source | Access |
| --- | --- | --- | --- |
| F1 | Index dashboard - 229 indices with close, change, P/E, P/B, dividend yield, market cap, turnover | `index/market-price/daily-feed` | P |
| F2 | Index returns table - 1M to 10Y for 239 indices | `index/price-returns` | P |
| F3 | Index valuation history charts | `index/valuation/historical` | P |
| F4 | Results calendar - 2,006 companies with expected dates | `results-calendar` | P |
| F5 | IPO calendar including SME issues, with price band, issue size, dates | `ipo-calendar` | P |
| F6 | Corporate actions calendar by ex-date | `corporate-actions/all` | P |
| F7 | Exchange holiday calendar | `holidays-calendar` | P |
| F8 | Live announcement feed across the market | `corp-announcements` | P |
| F9 | Sector heatmap - aggregate valuation and growth by sector | computed from our tables | P |
| F10 | Market movers - top gainers, losers, volume spikes, 52-week breakouts | computed from `quote` | P |

F9 and F10 are computed entirely from data we already hold, cost zero additional API calls,
and are strong SEO landing pages.

---

## G. Admin console

| # | Feature | Access |
| --- | --- | --- |
| G1 | Data quality dashboard - per-symbol completeness matrix across pl/bs/cf/ratios/shareholding | A |
| G2 | Stale data report - symbols whose fundamentals are older than expected given their result date | A |
| G3 | Targeted re-fetch for a specific symbol or a small set | A |
| G4 | Ingestion job history: run, duration, calls made, rows written, failures | A |
| G5 | Curate and feature preset public screens | A |
| G6 | User management - view, suspend, reset; cannot create or modify admins | A |
| G7 | Content moderation for shared screens and user-submitted names | A |
| G8 | Company classification override - fix the sector/industry naming inversion per symbol | A |

---

## H. Super Admin console

| # | Feature | Access |
| --- | --- | --- |
| H1 | **Full universe download** - orchestrate the complete fundamentals backfill for all 5,630 symbols | S |
| H2 | Ingestion scheduler configuration - what runs when, with what concurrency | S |
| H3 | FinEdge credential management, key rotation, connectivity test | S |
| H4 | API budget and quota controls - max calls per run, per day, hard stop | S |
| H5 | Selective backfill: by index, sector, market-cap band, or symbol list | S |
| H6 | Delta sync control using `refreshed-stocks` - preview what would change before running | S |
| H7 | Role assignment, including promoting a user to Admin | S |
| H8 | Raw response inspector - view the exact FinEdge payload stored for any symbol and endpoint | S |
| H9 | Danger zone: purge and rebuild a table, roll back an ingestion run | S |
| H10 | Cost and usage analytics - calls by endpoint, bytes transferred, time spent | S |

H1 is the headline Super Admin capability from the requirement. Its mechanics -
job graph, ordering, concurrency, resumability - are specified in
[06 - Data model and ingestion](06-data-model-and-ingestion.md).

---

## Feature count by access level

| Level | Features available |
| --- | --- |
| Public | 48 |
| Registered user | 48 + 31 additional |
| Admin | all user features + 8 operational |
| Super Admin | everything + 10 data-platform controls |

# 01 - Product Overview

## Vision

StockLens gives Indian retail investors a fast, honest, free way to find and understand
listed companies. Anyone can screen the market and read a company's fundamentals without
signing up. Signing up turns a one-off lookup into an ongoing research workflow: saved
screens, watchlists, alerts, comparisons and exports that persist across sessions.

## Why this is buildable

The hard part of a screener is not the UI, it is having consistent, normalised fundamentals
for the whole market. FinEdge already solves that: standardised field names across all
5,630 companies, separate correct schemas for banks and insurers, and pre-computed ratios,
growth rates and multi-year averages. StockLens does not need to derive ROCE or CAGR from
raw statements - it ingests them.

See [02 - Data source inventory](02-data-source-inventory.md) for exactly what is available
and what is not.

## Personas

### Public visitor (not signed in)
Arrives from a Google search for "Reliance share price" or "low PE high ROCE stocks".
Wants an answer in one page load. Will not sign up to find out whether the site is useful.
Must be given a genuinely complete company page and a genuinely working screener, because
that is the acquisition funnel.

### Registered investor (free account)
Screens the market weekly, tracks 20 to 60 companies, wants their screens to still be there
next Sunday. Wants to be told when a company they follow declares results, changes its
shareholding pattern, or gets a rating action. This is the core persona.

### Admin
Operations staff. Watches ingestion health, fixes bad or missing data for specific symbols,
curates the public preset screens, handles user reports. Does not touch credentials or
run mass jobs.

### Super Admin
Owns the FinEdge integration. Runs and schedules the full-universe download, manages the
API key and quota, assigns roles, and owns the cost and correctness of the data layer.

## Scope

### In scope for v1
- Company search and company analysis page (all sections in the reference screenshots that
  the data supports)
- Screener with a query language over ~180 fundamental and price columns
- Preset public screens
- Accounts, roles, saved screens, watchlists, exports, alerts
- Super Admin data download and job console
- Admin data quality and user management console

### Explicitly out of scope for v1
- Real-time or intraday tick data. FinEdge quotes are end-of-day / last-traded snapshots.
- Mutual funds. FinEdge lists this as "coming soon".
- Derivatives, options chains, F&O data.
- Broking, order placement, or portfolio P&L against real holdings.
- Paid tiers and payment collection. The role model is designed to allow this later
  (see [04](04-roles-and-access.md)) but v1 monetises nothing.
- Machine-learning price prediction or buy/sell recommendations.

## Non-goals worth stating explicitly

**We are not going to fake data depth.** Screener.in shows 12 years of annual P&L. FinEdge
provides 8. StockLens will show 8 and label the range honestly rather than pad the table.
The same applies to 10-year growth figures: FinEdge provides 3-year and 5-year growth only,
so StockLens shows 3Y and 5Y, plus TTM and price CAGR which we can compute ourselves from
13 years of daily prices.

**We are not going to present derived opinions as facts.** The Pros/Cons block is generated
from deterministic ratio thresholds and will be labelled as machine-generated, with the
underlying rule visible on hover.

## Success measures for v1

| Measure | Target |
| --- | --- |
| Screener query latency, p95, full universe | Under 400 ms |
| Company page first paint | Under 1.5 s |
| Universe price freshness | Refreshed within 60 min of market close |
| Fundamentals freshness | New filings reflected within 24 h of FinEdge refresh |
| Signup conversion from screener use | 5% of sessions that run 3+ screens |
| Data completeness | 95%+ of the 2,510 consolidated-statement companies fully populated |

## Product principles

1. **Public first.** Every gate must have a real reason. If a feature does not cost us
   materially more to serve, it should not be behind login.
2. **The database is the product.** Serve everything from SQLite, never proxy a user
   request to FinEdge at read time. The API key is a build-time input, not a runtime one.
3. **Show the working.** Every number links back to the statement line it came from and
   the period it belongs to.
4. **Fail visibly to operators, gracefully to users.** A company with missing cash flow
   shows a labelled gap to the user and a red row on the Admin data quality dashboard.

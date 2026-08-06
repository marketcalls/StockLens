# Phase 1 - Schema discovery, normalised tables, universe and price sync

**Date:** 2026-08-06
**Roadmap item:** [Phase 1 - Data layer](../prd/08-roadmap.md), first slice
**Result:** Working. 126 backend tests pass. All 5,630 companies and 239 indices are loaded.

---

## What I set out to do

Phase 1 turns the raw stored responses into proper tables that can be queried. Before
writing any of that, one question had to be answered: **how many different shapes do these
financial statements come in?**

The plan assumed three - ordinary companies, banks, and insurers. Guessing wrong here would
mean rebuilding the tables later, so I measured it instead.

---

## The measurement, and the mistake I made first

I wrote a quick script to fetch the profit and loss statement for 18 companies and compare
which fields each returned.

The result looked alarming: two thirds of the companies appeared to have **no balance sheet
at all**. NTPC, Tata Steel, Bajaj Finance - all apparently blank.

That would have been a serious finding, so I checked one directly before believing it. Every
single one had a full balance sheet with 72 fields.

**What went wrong:** my quick script fired 126 requests back to back with no pacing and no
retry. Some failed. And when a request failed, my script quietly recorded it as "no data"
rather than "I could not tell". So temporary failures looked exactly like missing balance
sheets.

The proper client built in Phase 0 already handles this - it paces requests and retries the
ones that fail. I threw the script away and rewrote the discovery to use it. That version is
now a permanent command rather than a throwaway, because the same question comes up again
whenever FinEdge adds companies:

```
python -m app.ingest.discover RELIANCE HDFCBANK HDFCLIFE ICICIGI
```

The lesson worth keeping: **a check that treats "I could not find out" the same as "the
answer is no" will lie to you.** The rewrite records failures separately.

---

## What the measurement actually found

Three things, all of which contradict the plan.

### 1. There are four statement shapes, not three

| Shape | Who uses it |
| --- | --- |
| Ordinary companies | Reliance, ITC, TCS, Maruti, Sun Pharma, NTPC, Tata Steel |
| Banks | HDFC Bank, SBI, Bank of Baroda, AU Small Finance Bank |
| Life insurers | HDFC Life, LIC, SBI Life, ICICI Prudential |
| General insurers | ICICI Lombard |

Life insurers and general insurers share only 14 of their fields. Life insurance reports on
premiums, actuarial liabilities and bonuses to policyholders; general insurance reports on
claims incurred and underwriting profit. Treating them as one "insurance" shape, as the plan
did, would have rendered both incorrectly.

### 2. Finance companies are not banks

This was the genuinely useful surprise. Bajaj Finance, Cholamandalam, LIC Housing Finance,
HDFC AMC, Angel One and even the BSE exchange itself all use the **ordinary company** shape,
not the bank shape.

That matters because it would have been very natural to assume otherwise and route every
lender through the bank renderer.

One trap: the field `interestEarned` appears in *both* ordinary companies and banks. Anything
classifying on that field alone would drag every NBFC into the bank category. There is a test
pinning exactly that case.

### 3. Matching has to be forgiving

AU Small Finance Bank returns 25 of the bank shape's 26 fields. The missing one is the line
for profit attributable to minority shareholders - it has no subsidiaries, so it has nothing
to report there.

If the rule were "the fields must match exactly", AU Bank would become a category of one and
its statements would render wrongly. So the classifier scores how well a company matches each
shape and picks the best fit, rather than demanding an exact match.

**All 22 companies now classify correctly, every one at full confidence.**

---

## The second surprise: the price feed is not a list of companies

The single call that fetches prices for the whole market returned **6,747 entries**. The
company list has **5,630**.

I looked into the extra 1,117 rather than assuming they were simply more companies. They are
not:

- **242 are companies we already have, listed a second time under their BSE numeric code**
  instead of their ticker. The same company, counted twice.
- 376 are BSE-only listings with no entry in the company list, so no financial statements
  exist for them
- 528 are not companies at all - they are ETFs and rights entitlements

**Why this matters:** if the screener had used the price feed as its list of companies, 242
companies would appear twice in every result, and 528 rows would be funds and entitlements
with no fundamentals behind them. The screener's universe is the company list, joined by
ticker. A permanent check now watches this.

---

## What got built

### Four schema families and a classifier
Scores a company's fields against each shape and reports both the answer and how confident it
is. Anything it cannot place is marked "unknown" rather than guessed at, so it shows up on the
quality report instead of rendering wrongly.

### Normalised tables
Companies, quotes, statement periods and lines, daily prices, indices, index membership,
index quotes and index returns.

Statement figures are stored one row per figure rather than one column per figure. With four
shapes whose fields barely overlap, and life insurers alone carrying 67, a wide table would
need several hundred mostly-empty columns and a schema change every time FinEdge adds a line.

### Translation from FinEdge's formats
Dates arrive in four different formats (`2026-08-06`, `20260331`, `27-May-2026`,
`2026-08-06 19:27:07`); all become one. Anything unrecognised becomes empty rather than a
guessed date.

Missing numbers stay missing. They are never turned into zero - on a financial screen "we do
not have this figure" and "this figure is zero" mean completely different things.

### Two jobs
- **Universe sync** (4 requests): the company list, all 239 indices with their members, index
  prices and index returns
- **Price refresh** (1 request): every company's price, market cap, 52-week range and volume

Both ran successfully: 5,630 companies, 239 indices, 23,367 index memberships, 1,384 index
returns, 6,747 quotes.

### Three decisions about overwriting
- **Index membership is replaced, not added to.** Indices rebalance. Merging would leave a
  removed company as a member forever.
- **Restated results replace the old figures entirely.** Merging would leave a deleted line
  sitting there as a stale number.
- **Company identity and company classification never overwrite each other.** They come from
  different requests and own different columns; a careless save would blank whichever arrived
  first.

### A quality report
Eight checks, at `/api/meta/quality`. Currently: no errors, four warnings, all understood and
documented above.

---

## How I checked it works

| Check | Result |
| --- | --- |
| Backend tests | 126 pass |
| Code style | clean |
| Classifier against all 22 real companies | 22 correct, 0 wrong, all at full confidence |
| Universe sync against the live API | 5,630 companies, 239 indices, 23,367 memberships |
| Price refresh against the live API | 6,747 quotes in one request |
| Quality report | 0 errors, 4 warnings, each explained |

---

## Corrections to the plan

Both findings are now written into
[the data inventory](../prd/02-data-source-inventory.md), sections 6.3a and 6.3b, so the
next person does not have to rediscover them.

## What's next

Normalising the per-company statements that Phase 0 already stores as raw responses, then
building the wide table the screener queries. After that, the full download of all 5,630
companies - prioritised so the well-known names land first and the product becomes useful
after a few hours rather than after the whole run.

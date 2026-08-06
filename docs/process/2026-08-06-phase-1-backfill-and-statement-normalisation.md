# Phase 1 - Statement normalisation and the prioritised backfill

**Date:** 2026-08-06
**Roadmap item:** [Phase 1 - Data layer](../prd/08-roadmap.md), second slice
**Result:** Working. 147 backend tests pass. Eight companies fully loaded, 122,696 rows.

---

## What I set out to do

The previous slice loaded the company list, indices and prices. What it did not do was turn
a *company's* stored responses into tables you can query.

This slice does that, and adds the machinery to run it across all 5,630 companies without
either flooding FinEdge or losing progress if something goes wrong.

---

## What got built

### 1. Seven more tables
Derived figures (EBITDA, free cash flow, book value), the four ratio families, growth and
average metrics, daily and annual valuation ratios, shareholding by group, and corporate
actions.

### 2. Translators for each of them
Each takes one FinEdge response and produces rows. Two decisions worth recording:

**Zero is not the same as "could not calculate."** The annual valuation data returns `pb: 0`
for years where price-to-book could not be worked out. Stored as-is, a screener searching for
"price to book under 1" would return every one of those companies as an apparent bargain.
Zeros in that data now become blanks.

**We store FinEdge's own derived figures rather than recomputing them.** If we calculated
EBITDA ourselves and FinEdge calculated it slightly differently, the company page and the
screener would disagree with each other. Better one consistent source.

### 3. The backfill
Fetches all 59 requests for a company, stores each raw, and files it into the right table in
the same pass. Four properties it needed:

**It goes in a sensible order.** Not alphabetical. Members of the major indices first,
largest first, then everything else by size. The whole run takes about 18 hours; this way the
companies people actually search for are ready within the first few minutes.

There is a test for a specific trap: a very large company that is *not* in a major index must
not jump ahead of a small company that is. Index membership is the stronger signal of "someone
will look this up".

**It can be stopped.** A call budget that ends the run cleanly rather than being killed
halfway.

**It can be resumed.** Every request is checkpointed, so a crash picks up where it stopped.

**It can be costed before it is run.** A dry run reports the price without paying it:

```
symbols: 5630          estimated_calls: 332170
calls_per_symbol: 59   estimated_hours: 18.45
```

**One bad response cannot kill the run.** If a response fails to translate, that one request
is recorded as failed and the run continues. Losing one figure for one company is much better
than losing eighteen hours.

### 4. New responses cannot corrupt anything
If FinEdge adds an endpoint we do not recognise, it gets archived but not filed anywhere.
It cannot land in the wrong table. There is a test for this.

---

## Proving it works on real companies

I ran the backfill against eight companies chosen to cover every statement shape found
earlier. The classifier had only ever been tested against saved field lists, so this was the
first time it ran against live responses end to end.

| Company | Detected shape | Correct? |
| --- | --- | --- |
| Reliance, TCS, ITC | ordinary company | yes |
| HDFC Bank, SBI | bank | yes |
| HDFC Life | life insurance | yes |
| ICICI Lombard | general insurance | yes |
| Bajaj Finance | ordinary company | yes |

Bajaj Finance is the one worth pointing at. Its own sector label reads **"Non Banking
Financial Company (NBFC)"** — and its statements use the ordinary company shape, exactly as
the earlier measurement predicted. Anything routing on the word "finance" would have sent it
to the bank renderer and produced nonsense.

### The sector inversion fix, confirmed
FinEdge labels Reliance's `industry` as "Petroleum Products" and its `sector` as
"Refineries & Marketing" — narrower than the industry, which is backwards. After correction
the hierarchy reads broad to narrow:

```
RELIANCE    Energy > Petroleum Products > Refineries & Marketing
HDFCBANK    Financial Services > Banks > Private Sector Bank
BAJFINANCE  Financial Services > Finance > Non Banking Financial Company (NBFC)
ICICIGI     Financial Services > Insurance > General Insurance
```

---

## How I checked it works

| Check | Result |
| --- | --- |
| Backend tests | 147 pass |
| Code style | clean |
| Dry run, whole universe | 332,170 requests, 18.45 hours, matches the plan |
| Prioritised order | Reliance, Bharti Airtel, HDFC Bank, ICICI Bank, SBI |
| Live backfill of 8 companies | 472 requests, 0 failed, 0 skipped, 122,696 rows |
| Every statement shape detected correctly | 8 of 8 |
| Quality report | 0 errors, 4 known warnings |
| Unclassifiable statements | 0 |

Stored so far: 1,000 statement periods, 56,485 individual figures, 24,392 days of prices,
30,111 daily valuation readings, 5,440 derived figures.

---

## One thing that went wrong

A shell quirk while wiring the command line: a newline inside a piece of code got written
literally instead of as an escape, splitting a line of code in half. The linter caught it
before anything ran. Fixed by editing the file directly rather than through the shell.

Not interesting in itself, but it is the reason the code-style check runs before the tests
rather than after — it catches this class of damage in a second rather than a minute.

---

## What's next

The wide table the screener actually queries. Everything is now stored in tall, flexible
tables that are right for keeping data but wrong for answering "show me every company with
return on equity above 15 and debt to equity below 0.5" quickly. That one table, one row per
company and about 180 columns, is what Phase 3's screener runs against — and building it is
the last piece of Phase 1.

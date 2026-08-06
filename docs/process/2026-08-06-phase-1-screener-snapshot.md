# Phase 1 - The screener snapshot

**Date:** 2026-08-06
**Roadmap item:** [Phase 1 - Data layer](../prd/08-roadmap.md), final slice
**Result:** Phase 1 complete. 193 backend tests pass. Real screener queries now return answers.

---

## What I set out to do

Everything so far is stored in tall, flexible tables — one row per figure. That is the right
shape for *keeping* data across four different statement formats, but the wrong shape for
answering "show me every company with a P/E under 20 and return on equity above 12" quickly.

This slice builds the wide table that answers those questions: one row per company, 118
columns, rebuilt from the tall tables whenever the data changes.

---

## The column catalog

Rather than hand-writing 118 columns in two places and hoping they stay in step, there is one
list that both the table and the future query language read from. A column cannot exist in
one and not the other.

Each column records where its value comes from, what it is called, what a user might type
instead ("ROE", "Return on equity"), and — the fiddly part — **how to convert the units.**

### The unit problem

FinEdge and the reference product do not agree on units, in three separate ways:

| Kind of figure | FinEdge sends | Users expect | Conversion |
| --- | --- | --- | --- |
| Money in statements | 957,540,000,000 | 95,754 crore | divide by 10 million |
| Return on equity | 0.0827 | 8.27% | multiply by 100 |
| Debt to equity | 0.41 | 0.41 | leave alone |
| Earnings per share | 59.69 | 59.69 | leave alone |
| Market cap from prices | 1,793,061 | 1,793,061 crore | already correct |

The dangerous cases are the ones sitting inside a group where everything *else* needs
converting. Earnings per share arrives in the same response as revenue and profit, both of
which need dividing by ten million. Divide earnings per share too and 59.69 becomes 0.000006 —
which no longer looks like a number anyone would notice being wrong, but every valuation
built on it would be nonsense.

Same trap the other way round: profit margins are fractions and need multiplying by 100, but
debt-to-equity and the current ratio sit right beside them and are already plain numbers.

There are thirteen tests pinning these rules individually.

**A correctness check worth having:** Reliance's net profit came out at 95,754 crore and its
earnings per share at 59.69. Both match the reference product's figures exactly. That is a
much stronger signal than any unit test, because it means the whole chain — fetch, store,
convert, aggregate — agrees with an independent source.

---

## Two rules for picking which number to show

A company can have four versions of the same figure: standalone or consolidated, and
trailing-twelve-months or the latest full year.

- **Consolidated wins.** It includes subsidiaries, which is what the reference product shows
  by default. Only about 2,510 of 5,630 companies have it, so standalone fills the gap.
- **Trailing twelve months wins** over the last full year, being more current.

---

## Two bugs found by checking against the reference

Both were caught by comparing output to the actual screenshots rather than by tests passing.

### Reliance's P/E came out at 45.7 instead of 24.0

Nearly double. The cause was a single line comparing pairs of `(date, statement type)` to pick
the most recent figure. Statement type is stored as `"c"` for consolidated and `"s"` for
standalone — and **"s" sorts after "c"**, so "most recent" quietly meant "standalone".

For a holding company like Reliance, standalone profit is a fraction of consolidated, so the
P/E roughly doubles. The number was wrong but entirely plausible-looking, which is what makes
this class of bug dangerous. Fixed by ranking consolidated explicitly rather than relying on
alphabetical order. A test now pins the exact 45.72-versus-23.99 case.

### Every bank and insurer showed no profit at all

Only 4 of the 8 loaded companies had a net profit figure. The four missing were the two banks
and the two insurers.

The reason is the schema discovery from the previous slice, coming back around: a bank does
not have a field called `profitLossForPeriod`. It has `profitLossForThePeriod`. A life
insurer calls it `profitLossAfterTaxAndExtraordinaryItems`. A general insurer calls it
`profitLossAfterTax`.

I had built the catalog against the ordinary-company field names only. Every bank and insurer
in the country would have silently vanished from any screen mentioning profit — not shown as
an error, just absent.

Columns now carry a list of alternative names to try. All eight companies have a net profit;
banks and insurers included.

---

## What the snapshot can now answer

A real query against the loaded companies:

```
P/E under 20 and return on equity above 12

  HDFCBANK    HDFC Bank Ltd                PE 14.35   ROE 13.59%
  SBIN        State Bank Of India          PE 12.02   ROE 13.55%
  TCS         Tata Consultancy Services    PE 17.22   ROE 46.44%
  ITC         ITC Ltd                      PE 17.99   ROE 27.36%
```

That is the screener working, without the query language on top of it yet.

### Figures StockLens works out itself
Dividend yield, enterprise value, EV/EBITDA, earnings yield, annualised price returns over 1,
3, 5 and 10 years, distance from the 52-week high and low, 50- and 200-day moving averages,
average traded value, promoter holding and pledge, and cash generation against reported profit.

The price returns are worth noting: they are **annualised**, so a 3-year and a 1-year figure
mean the same thing and can sit in the same column comparison. Reliance's 10-year works out at
18.1% a year.

### One detail that would have been a bug
Shareholding quarters are labelled "Mar 2026", "Jun 2026". Sorting those as text puts June
before March. The latest quarter is now picked by parsing the label properly. Reliance's
promoter holding reads 50.48%, which is the June 2026 figure and matches the reference.

Also worth recording: HDFC Bank and ITC come back with *no* promoter holding. That is correct
— both are professionally managed with no promoter group — and is a case where blank means
something real rather than missing data.

---

## How I checked it works

| Check | Result |
| --- | --- |
| Backend tests | 193 pass |
| Code style | clean |
| Reliance net profit against the reference | 95,754 crore, exact match |
| Reliance earnings per share against the reference | 59.69, exact match |
| Reliance P/E after the fix | 23.99 against the reference's 23.98 |
| Reliance promoter holding | 50.48%, matches |
| All four statement formats produce a net profit | 8 of 8 |
| Snapshot rebuild is repeatable | yes, and removed companies disappear |
| Live screener query | returns sensible results |

---

## One recurring annoyance

For the second iteration running, writing code through the shell mangled a newline character
inside a string, splitting a line in half. The style checker caught it instantly both times.
I have stopped routing code containing escape characters through the shell.

---

## Phase 1 is complete

The data layer is done: raw responses stored, four statement formats normalised, and a wide
table the screener can query in milliseconds.

## What's next

Phase 2, the public company page. Everything the reference screenshots show — the quarterly
results table, profit and loss with growth cards, balance sheet, cash flows, ratios,
shareholding, peers, documents — rendered from what is now in the database. The interesting
part is that the same table component has to render four genuinely different statement
formats, which is exactly why the format detection was built first.

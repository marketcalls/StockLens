# Phase 2 - The company page

**Date:** 2026-08-06
**Roadmap item:** [Phase 2 - Public read surface](../prd/08-roadmap.md), frontend half
**Result:** Working. 226 backend and 36 frontend tests pass. Verified in a real browser.

---

## What got built

Search with autocomplete, a landing page, and the company page: header with price and sector,
twelve key figures, a five-year price chart, quarterly results, profit and loss, balance
sheet, cash flows, ratios, shareholding and peers.

**One table component draws every company.** It has no idea what a bank is. The server sends
a list of labelled rows already chosen for that company's reporting format, and the component
draws whatever it receives. Side by side:

| Ordinary company (Reliance) | Bank (HDFC Bank) |
| --- | --- |
| Sales | Revenue |
| Expenses | Interest |
| Operating Profit | Expenses |
| OPM % | Financing Profit |
| Other Income | Financing Margin % |
| Interest | Provisions |
| Depreciation | ... |

Same component, same endpoint, entirely different rows.

Search is keyboard-first: arrows move, Enter opens, Escape closes, and requests are held back
briefly so a fast typist does not fire one per keystroke.

---

## Three bugs found by looking at the screen

### 1. Quarterly figures were annual figures

The most serious. The quarterly table showed **9,04,770 crore of sales for March 2023** — that
is a full year for Reliance, sitting in a three-month column.

The cause is a name collision. FinEdge's pre-calculated figures (operating profit, EBITDA)
come as an annual series labelled by period: "Mar 2023", "Mar 2024". The *quarterly* statement
also has a period called "Mar 2023" — the January-to-March quarter. I was matching the two by
that label, so every March quarter silently received the whole year's figures.

Fixed two ways. Those annual aggregates are now only merged into annual and trailing-twelve-
month tables, never quarterly. And operating profit is now worked out from the statement
itself — sales minus expenses, where expenses excludes the interest and depreciation lines
shown separately — so the table reconciles by construction for every period.

**The check that proves it:** Reliance's operating profit for June 2023 now reads 38,093
crore, which is exactly what the reference shows. Before the fix that column held a year.

This one is worth dwelling on because it was invisible to tests, produced numbers that looked
entirely reasonable, and only stood out because a March column was four times its neighbours.

### 2. Price charts had spikes to zero

Every chart dropped vertically to zero on about a dozen dates. Those turned out to be Diwali
Muhurat sessions and special Saturday sittings, where FinEdge sends a row with every field
set to zero.

Zero is not a price. This is the same rule established when the data layer was built —
missing is never zero — and I had not applied it here. All-zero rows are now discarded at
import, 81 existing ones were removed, and the quality check that looked for prices *below*
zero now looks for zero as well. It had been passing happily.

### 3. Banks showed 0% bad loans

Gross bad loans, net bad loans and the capital ratio all read 0% for every quarter — which
would be a remarkable bank. FinEdge returns zero for fields it has no value for.

A row that is zero in every single period is now dropped. A row with one real figure and some
zeros is kept, because there the zeros mean something.

---

## One thing that looked like a bug and was not

The first screenshot showed the price chart crammed into a sliver at the left edge. Before
changing anything I checked the rendered chart directly: full width, complete data path.

The screenshot had simply caught the chart mid-animation. Had I "fixed" it, I would have
broken working code. Worth the two minutes it took to check.

---

## How I checked it works

| Check | Result |
| --- | --- |
| Backend tests | 226 pass |
| Frontend tests | 36 pass |
| TypeScript and code style | clean |
| Production build | succeeds |
| Reliance in a real browser | renders fully |
| HDFC Bank in a real browser | renders bank rows, no sales or operating profit |
| Reliance operating profit, Jun 2023 | 38,093 against the reference's 38,093 |
| Operating margin, Jun 2023 | 18.07% against the reference's 18% |
| Sales minus Expenses equals Operating Profit | holds |
| Quality report | 0 errors |

---

## Small details that matter on a financial page

- Numbers use Indian grouping: 10,75,675 rather than 1,075,675
- Figures line up in columns, because digits are set to equal width
- Negative numbers keep their minus sign as well as their colour, so the meaning survives for
  anyone who cannot distinguish the colours
- A missing figure shows a dash, never a zero
- Wide tables scroll inside their own box with the line labels pinned; the page itself never
  scrolls sideways

---

## What's next

Phase 3, the screener. The wide table it queries is already built and the column catalog
already knows every name and unit. What remains is the query language on top: parsing
`Market Capitalization > 500 AND Return on equity > 15` into SQL, the results grid, and the
preset screens.

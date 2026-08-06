# Phase 2 - Company page API

**Date:** 2026-08-06
**Roadmap item:** [Phase 2 - Public read surface](../prd/08-roadmap.md), backend half
**Result:** Working. 217 backend tests pass. Statements render correctly for all four
company types.

---

## What I set out to do

Serve the company page: search, the header block, the financial statement tables, ratios,
shareholding and peers. All public, all from our own database.

The interesting problem is that **one table has to render four completely different kinds of
company.** An ordinary company's profit and loss reads Sales, Expenses, Operating Profit,
OPM%. A bank has none of those lines — it has interest earned, interest expended, net
interest income, bad loans and capital ratios. A life insurer has premiums and actuarial
liabilities.

The solution is that the list of rows belongs to the *company type*, not to the table. One
component draws all four; a template per type says what to draw. This is why detecting the
company type came first, three slices ago.

---

## Five bugs, all found by comparing to the reference

None of these were caught by tests. Every one came from rendering a real company and
checking the numbers against the actual Screener pages.

### 1. HDFC Bank's financing profit read 1,295,104,700,000

Roughly a trillion. Rows that are *looked up* from the data get converted from rupees to
crore. Rows that are *calculated* — net interest income is interest earned minus interest
expended — skipped that conversion entirely.

It did not show up in ordinary companies because their only calculated rows are percentages,
which need no conversion. It took a bank to expose it.

### 2. The profit and loss table did not add up

Sales minus Expenses did not equal Operating Profit. Off by about 25,000 crore.

The cause: I was taking Sales from one field and Expenses from a different, related one.
FinEdge provides a matched pair where revenue minus expenses genuinely equals operating
profit; I had picked the revenue figure from the other pair.

Worth fixing carefully rather than papering over, because a financial table that does not
add up destroys trust in every other number on the page. It now reconciles exactly:
1,104,637 − 954,414 = 150,223.

### 3. Reliance had zero fixed assets

I had guessed the field names for the balance sheet rather than checking them. Several were
wrong — the real ones are `equityCapital` not `equityShareCapital`, `reserves` not
`totalReserves`.

The subtle one: a field called `fixedAssets` does exist, but it is zero, while
`propertyPlantAndEquipment` holds the real figure. My "use the first field that has a value"
rule treated zero as a value. Reordered so the populated field is tried first.

### 4. Reliance appeared to have 47 shareholders

The shareholder count is reported per group. I was taking whichever group happened to have
one — and the promoter group has 47 holders, against roughly 4.6 million members of the
public.

Now summed across groups: 4,651,863 for June 2026, which matches the reference exactly.

### 5. Balance sheets and cash flows reported an unknown company type

Only the profit and loss statement carries the markers that identify a company type, so
balance sheet records are stored as "unknown". The page needs the type to pick a layout, so
it now falls back to the type decided from the company's profit and loss.

---

## What now matches the reference exactly

| Figure | StockLens | Reference |
| --- | --- | --- |
| Reliance net profit, Mar 2024 / 25 / 26 | 79,020 / 81,309 / 95,754 | identical |
| Reliance earnings per share, Mar 2026 | 59.7 | 59.69 |
| Reliance promoter holding, Jun 2026 | 50.48% | 50.48% |
| Reliance shareholders, Jun 2026 | 4,651,863 | 46,51,863 |
| Reliance total assets, Mar 2026 | 21,78,140 | 21,77,546 |
| Reliance price-to-earnings | 23.99 | 23.98 |

Total assets differ by 0.03%, which is a rounding or line-inclusion difference rather than an
error.

---

## Search

Typing "rel" returns Reliance Industries first, then Relaxo, Religare, Reliance
Infrastructure — ordered by an exact symbol match first, then symbol prefix, then name, with
ties broken by company size. Without the size tie-break, "rel" surfaces obscure small
companies ahead of the one almost everyone means.

## Peers

Built from our own sector classification rather than FinEdge's peers endpoint, which returned
four companies for ITC, some of them obscure. Currently returns short lists simply because
only eight companies are loaded; it will fill out as the backfill runs.

---

## How I checked it works

| Check | Result |
| --- | --- |
| Backend tests | 217 pass |
| Code style | clean |
| Ordinary company profit and loss | renders, and reconciles |
| Bank profit and loss | renders bank lines, no sales or operating profit |
| Life insurer profit and loss | renders premiums and actuarial lines |
| Balance sheet | balances: assets equal liabilities |
| Cash flow | renders, including free cash flow |
| Shareholding | matches the reference exactly |
| Search ranking | Reliance first for "rel" |

---

## What's next

The React company page itself: search box, header, the statement tables with their
consolidated/standalone toggle and expandable rows, peers, shareholding and the price chart.
The API is shaped so the frontend component does not need to know anything about company
types — it receives a list of labelled rows and draws them.

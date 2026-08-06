# Checking the numbers

While the download ran, the app was checked against the data arriving in it —
not against its own tests. Eleven faults came out. Ten were figures that were
present, plausible-looking and wrong; the eleventh was documentation describing
an app that did not exist.

None was found by a test going red.

---

## What was checked

Every screener column, every statement family, the query language, index pages,
shareholding, corporate actions, peers, the role limits, and the documentation.

**Most of it was correct**, which is worth saying as plainly as the faults. All
118 stored columns had data. Every percentage column really was a percentage —
return on equity 17.5%, gross margin 60.8%, effective tax 25.1% at the median.
Every money column was in crore, not rupees; the largest total assets figure,
₹83 lakh crore, is a bank's balance sheet, exactly as it should be. Nine of the
ten query forms tested behaved — `AND`, `OR`, parentheses, column-to-column
comparisons, index membership, aliases and case-insensitive multi-word names all
correct. The public row cap held at 25 rows and could not be paged or
`per_page`'d past, and the rate limit fired exactly on the fortieth request in a
minute.

## The faults

**A bank's asset quality read 0%.** Axis Bank showed Gross NPA 0%, Net NPA 0%
and CET1 0% for every quarter. The real figures are 1.28%, 0.39% and 14.7%. A
comment in the scaling code asserted that these fields "already arrive as
percentages"; they arrive as fractions. Six rows across banks and both insurance
families were affected.

The sparklines beside those rows still moved, because the underlying numbers were
fine and only the scaling was wrong. Nothing looked broken.

**An insurer's solvency read 0.02.** Two conventions for the same quantity, and
not consistent per company: HDFC Life sends 1.85, LIC sends 0.0235 for the same
thing, and SBI Life sends both across its own series — so that row was a cliff
from 0.02 to 1.96, reading as an insurer on the brink. Resolved on a regulatory
basis: IRDAI requires 1.5, so a figure an order of magnitude below the statutory
floor is the hundredths form. A genuinely distressed 0.8 is left alone.

**Reliance's dividend yield halved on its own.** From 0.87% to 0.45%, with no
change to its price or its dividends. The trailing-twelve-month cutoff was
derived from the latest ex-date *anywhere in the database*, so every company's
window moved when any other company recorded a later one. The backfill reached
Glenmark, whose next ex-date is three weeks in the future, and Reliance's
₹5.50 from August fell outside a window pushed forward by a dividend nobody has
been paid. 253 companies were affected.

**A three-year return measured thirteen years.** The base price was found by
counting 248 trading days back per year, which is not the same as going back a
year. United Spirits has gaps in its history — suspended, thinly traded — so it
ran out of sessions long before it ran out of calendar, and its "three year"
figure spanned 13.46 years before being annualised as though it were three.

**The median was not a median.** Both index and peer medians took the upper of
the two middle values instead of the midpoint. On Reliance's four refiner peers
that reported 23.99 — Reliance's own multiple — putting it at the middle of a
group it sits at the expensive end of. Three of the four are cheaper. The bias is
always upward and only appears on even-length groups.

**`NOT` returned the whole market.** `NOT (Price to Earning > 20)` gave 5,180
companies. Fifty-four are known to trade under twenty times earnings; the rest
have no P/E because their statements have not been downloaded, and were counted
as though their P/E were zero.

**Prices that were not prices.** Six Adani Green sessions from 2018 with negative
open, high, low and close on real volume — a demerger adjustment applied to
history from before it listed. Sixty-four live quotes where a share that did not
trade came back at zero with a −100% day; Corona Remedies read ₹0.00 against a
₹12,461 Cr market cap, and matched a screen for `Current Price < 100`.

**A multiple divided by noise.** VAML reports EBITDA of −0.03 Cr against an
enterprise value of ₹187,894 Cr. That divides out to −6,242,332, which sorts to
the front of any screen on EV/EBITDA.

**Index pages showing nothing.** The BSE REIT & InvIT page was fifteen rows of
blank columns, each linking to a company page that 404s. Those members are REITs
and InvITs — real constituents, identified by scrip code, that will never appear
in an equity symbol master.

**A row of dashes.** "Non-promoter non-public" rendered empty on nearly half of
companies. Reliance last reported it in 2016.

**Documentation that described a different app.** Eleven undocumented routes, an
endpoint count wrong in both directions, a `family` field that is called
`schema_kind`, and five ratio family names — `profitability`, `liquidity`,
`solvency`, `efficiency`, `valuation` — of which none existed. A reader following
the page got an empty result that read as "this company files no ratios" rather
than "that name is not a thing".

---

## The thread

Seven of the eleven are the same mistake: **a number standing in for a
measurement that was never taken.**

Zero for a price that was not quoted. Zero standing in for unknown inside a
`NOT`. A ratio computed from a denominator that was almost nothing. A blank row
that reads as neither zero nor unreported. Two of them — the NPA percentages and
the solvency ratio — reached the page *as* zero through a scaling error rather
than a missing value, which is a different cause with the same symptom, and the
symptom is what a reader sees.

The other four are their own things: a window computed from the wrong anchor, a
horizon measured over the wrong span, a median that was not the midpoint, and
documentation describing an app that did not exist.

Zero is dangerous here precisely because it is well-behaved. It sorts, it
compares, it averages, it draws. `Current Price < 100` matches it. A median
absorbs it. A chart plots it. Nothing about a zero looks like an error, which is
why every one of these survived review, tests, and in several cases a comment
explaining why the code was right.

The fixes are all the same shape, and so is the discipline: **narrow**. Each one
had an obvious broad version that would have destroyed real data.

- A volume of zero survives. No trades is a fact about the day.
- A change of 0% survives. The price did not move.
- A change of −100% survives when there *is* a price — the rule keys off the
  missing price, not the number.
- Corona Remedies keeps its market cap, which is real, and loses only the price,
  which is not.
- Negative return on equity survives, because a loss is a measurement. Only
  negative *multiples* go, because a negative denominator makes the ratio
  meaningless.
- A solvency ratio of 0.8 is left alone: below the regulatory floor, but nowhere
  near the hundredths form, so it is reported as it stands rather than laundered
  into a healthy 80.

## What this says about testing

Every fault above passed the test suite. Several were *protected* by it.

The `NOT` behaviour had a test asserting the `COALESCE` was present, with a
docstring arguing for it. The NPA scaling had a test whose fixture fed a gross
NPA of 1.2 — a value the feed never sends — and asserted it rendered as 1.2%. The
test agreed with the code, and both disagreed with the data.

That is the failure mode worth naming: a test written from the same
misunderstanding as the code confirms the misunderstanding. The only thing that
caught these was comparing against something outside the codebase — the live API,
a published figure, a regulator's floor, or the same number computed a second way.

Where that could not be done, it is said rather than papered over. Pre-listing
price history — KIMS floated in 2021 and its series starts in 2014 at ₹0.96,
compounding to an 84% ten-year return — cannot be told from a genuine
multi-bagger without listing dates, and the real ones here reach 48%. So it is a
quality check that names the companies, not a threshold that quietly deletes real
returns.

## One more thing this turned up

Normalisation only runs when a row is fetched, so a rule added later never
reaches what came before it — and a long backfill keeps writing with the code it
started with. The download running through all of this kept producing zero-close
price rows for hours after the guard was written.

That was patched by hand three times before it became
[a repair pass](../SELF-HOSTING.md) with its own tests, including three that
assert it decides identically to normalisation. A repair that disagrees with
ingest undoes what ingest just did.

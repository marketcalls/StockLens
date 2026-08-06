# Loading real data

**What was asked:** download the full symbol master and every index, and run the
prioritised backfill so the app is working on real figures rather than a handful
of hand-picked companies.

---

## What a full download costs

Three jobs, and they are not remotely the same size.

| Job | Calls | Time |
| --- | --- | --- |
| Symbol master, all indices, index quotes and returns | 4 | seconds |
| Every company's current price | 1 | seconds |
| Financial statements for every company | ~332,000 | ~18 hours |

The first two are trivial because FinEdge returns the whole universe in one
response. The third is per company: statements, ratios, shareholding, price
history and corporate actions come to 59 calls each, and there are 5,630
companies. At the five-requests-a-second pace the client holds itself to, that is
most of a day.

So this run is bounded at **500 companies** — about 29,500 calls and a hundred
minutes — rather than starting eighteen hours of traffic against someone else's
API without saying so. The rest keep their prices and market caps and fill in
their financials later.

## Which 500

Not the first 500 alphabetically. Companies are ordered by index membership
first, then by market cap, so the run covers the names people actually search for
before it reaches the long tail. The first twelve fetched were Reliance, Bharti
Airtel, HDFC Bank, ICICI Bank, SBI, TCS, Bajaj Finance, L&T, LIC, Hindustan
Unilever, Infosys and Sun Pharma.

A company that has not been reached yet is not blank — it still has a live price,
market cap and 52-week range from the universe-wide quote call. Only the
financial statements are missing, and the index pages say so rather than implying
the whole index is loaded.

## What arriving data proved

The four statement schemas — general, bank, life insurance, general insurance —
were originally worked out from a sample of eight companies. At 117 they still
hold: 103 general, 10 bank, 3 life insurance, 1 general insurance, **and nothing
unclassified**. Every bank landed in the bank family and every insurer in the
right insurance family. Axis Bank's rows read as bank rows (Interest, Financing
Profit, Financing Margin) and SBI Life's read as insurer rows (Gross Premium
Income, Change in Actuarial Liability).

That is the single most reassuring result here, because a misclassified schema
renders a company's accounts under the wrong labels and nothing about the page
looks broken.

## Four things checking the data found

**Tata Motors was missing, and should have been.** Looking for TATAMOTORS
returned nothing. It demerged: the master now carries TMCV (Tata Motors Ltd) and
TMPV (Tata Motors Passenger Vehicles Ltd). The data was current and the
expectation was stale — worth recording, because the instinct on a missing
blue-chip is to assume the download is broken.

**Twenty-eight index members are not companies.** The BSE REIT & InvIT index page
was fifteen rows of nothing: a numeric scrip code, every column blank, each
linking to a company page that 404s. They are REITs, InvITs and SME listings —
genuine constituents that the exchange identifies by scrip code, and which will
never appear in an equity symbol master. They stay listed, because dropping them
would misstate the index, but they are no longer linked and the page says what
they are.

**Six price rows were negative.** Adani Green's first six sessions in June 2018
are stored with every open, high, low and close *below zero*, on real volume —
the demerger adjustment applied to history from before it listed separately. The
existing guard dropped all-zero rows, which was the case that had been seen
before, and had nothing to say about negative ones. The chart dipped under the
axis and any return spanning those dates was nonsense.

**Sixty-four live quotes said a share was worth nothing.** The same fault, but in
today's prices rather than history, and reaching the screener. Illiquid BSE small
caps that saw no trade come back with every price field at 0 and a change of
-100%. Corona Remedies read as Rs. 0.00 against a Rs. 12,461 Cr market cap, and a
screen for `Current Price < 100` matched it.

Zero is now treated as absent for price, 52-week range, market cap and share
count, and the -100% that arrives with a missing price goes with it, since it is
computed from the price that is not there.

The rule is deliberately narrow, because the obvious broad version destroys real
data:

- **Volume of zero survives.** Nothing changed hands is a fact about the day.
- **A change of 0% survives.** The price did not move.
- **A change of -100% survives when there is a price.** The rule keys off the
  missing price, not the number.
- **Corona Remedies keeps its market cap.** That figure is real. Only the price
  goes.

After this, quotes moving more than 50% in a day fell from 64 to 5 — and all five
have real prices and are genuine illiquid small-cap moves.

## A note on the pattern

Every one of those four is the same mistake in a different place: **a missing
value written down as zero**. It has now been found in statement figures, index
valuations, index market caps, historical prices and live quotes.

Zero is a number a financial screen will happily compute with. It sorts first,
it passes a `< 100` filter, it drags a median down, and it draws a line on a
chart. Nothing about it looks like an error, which is exactly why it keeps
getting through — and why the check is worth applying to every new field rather
than each time it bites.

## Where it stands

The bounded 500-company run is in progress, driven from the Super Admin console
rather than a script, which is also how those controls were verified.

Already visible: rebuilding the screener table after the first 117 companies
landed took a screen for large caps under 30x earnings from **4 results to 50** —
Reliance at 23.99, HDFC Bank at 14.35, SBI at 12.02, TCS at 17.22.

Both error-level data-quality checks now pass. The remaining warnings are
understood rather than outstanding: BSE scrip codes and ETFs in the quote feed
beyond the symbol master, 242 companies quoted under both their ticker and their
scrip code, 29 suspended or newly delisted, and the 28 REIT and InvIT index
members above.

## Known, not fixed

The backfill re-fetches companies it already has rather than skipping them. For a
manual "download" that is defensible — figures go stale and a refresh is the
point — but it means extending coverage from 500 to 1,000 pays for the first 500
again. Worth a "skip what is already held" option; not worth changing ingestion
behaviour while a download is running.

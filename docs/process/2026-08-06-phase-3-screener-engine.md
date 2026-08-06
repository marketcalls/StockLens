# Phase 3 - The screener engine

**Date:** 2026-08-06
**Roadmap item:** [Phase 3 - Screener](../prd/08-roadmap.md), backend half
**Result:** Working. 278 backend tests pass. Real queries return in under 2 milliseconds.

---

## What got built

A query language. You type

```
Price to Earning < 20 AND Return on equity > 12
```

and get back the companies that match, with the true count.

Behind it: a tokeniser, a parser producing a tree, a compiler turning that tree into SQL, an
executor, twelve ready-made screens, and the endpoints that serve them.

---

## The awkward part: column names contain spaces

Most query languages can split the input on spaces. This one cannot, because a column is
called "Return on equity", not "return_on_equity". The parser cannot know where the name ends
and the comparison begins without consulting the list of real columns.

So the tokeniser reads a run of words, then asks the catalog for the **longest** prefix that
names something real. "Average return on capital employed 3Years > 20" resolves the whole
six-word name rather than stopping at "Average". Shorter matches are only used if the longer
ones fail.

This is also the security mechanism, and it falls out of the design rather than being bolted
on.

---

## Security: a column name can never come from the user

The rule is that **only names already in the catalog are ever written into SQL**. Everything
else — every number, every piece of text — becomes a bound parameter that the database treats
as a value and never as code.

If a name does not resolve, the query is rejected with a message, long before any SQL exists.

Tried against the running service:

| Input | Result |
| --- | --- |
| `market_cap; DROP TABLE company_snapshot; -- > 1` | Refused: unexpected character ";" |
| `PE < 20; DELETE FROM company` | Refused: unexpected character ";" |
| `PE > (SELECT 1)` | Refused: unknown column "SELECT" |
| `Sharpe ratio > 1` | Refused: unknown column "Sharpe" |

All tables intact afterwards. There are also tests asserting that every identifier appearing
in generated SQL is a known catalog key, and that a quoted injection string ends up as a
parameter value rather than as SQL text.

One input returned results rather than an error: `1=1 OR PE > 0`. That is a tautology, not an
attack — it compiles to `(:p1 = :p2) OR (pe > :p3)` with all three literals bound. A user is
allowed to write a condition that is always true.

---

## The subtle part: what "unknown" means

In SQL, comparing an unknown value to anything gives neither true nor false but "unknown", and
rows that are unknown get filtered out. That is usually right: a company that has never
reported a return on equity should **not** appear in a search for `Return on equity > 15`. It
would be much worse to treat the gap as zero and quietly include it.

But that behaviour is exactly wrong in one place. Consider:

```
NOT (Promoter pledge > 0)
```

The user is asking for companies where promoters have pledged nothing. A company with no
pledge figure at all is precisely what they want — and the plain SQL reading would exclude it,
because unknown stays unknown through the NOT.

So NOT, and only NOT, treats an unknown as true. There are tests for both halves, because the
two look contradictory unless you know why.

Division is guarded too: `Market Capitalization / Sales` where sales is zero yields no answer
rather than an error or an infinity.

---

## Being honest about the row cap

A visitor who is not signed in sees 25 rows. They are also told, truthfully, how many matches
there are in total. Showing 25 of 340 while implying that is all of them would be misleading;
saying "25 of 340" is not.

The limit is applied in the query itself, computed on the server from the cap. There is a test
confirming that asking for page 2 returns nothing rather than rows 26 to 50 — a modified
browser request cannot walk past the wall.

---

## Twelve ready-made screens

Low PE with high returns, debt-free compounders, dividend champions, quality at a reasonable
price, cash generators, negative working capital cycles, companies well off their highs,
promoter pledge risk, small-cap growth, turnarounds, cheap Nifty 50 names, and companies
trading below book value.

A test runs every one of them through the parser, the compiler and the database. If somebody
renames a column, the preset that used it fails immediately rather than quietly returning
nothing months later.

---

## One design tidy-up

`Index = "NIF50"` looks like a normal column comparison but is not — index membership lives in
a separate table. It compiles to an EXISTS against that table instead.

It was initially added to the catalog like any other column, which would have created a
permanently empty column in the main table that nothing ever writes to. It is now marked as a
pseudo-column: screenable, but not stored. A test asserts it stays out of the table and stays
usable in queries.

---

## How I checked it works

| Check | Result |
| --- | --- |
| Backend tests | 278 pass |
| Code style | clean |
| `PE < 20 AND ROE > 12` | HDFC Bank, SBI, TCS, ITC — 1.2 ms |
| `Market Capitalization > 500000` | 8 companies — 0.8 ms |
| `NOT (Promoter pledge > 0) AND PE < 25` | 5 companies — 0.8 ms |
| `Index = "NIF50" AND PE < 20` | 4 companies — 0.9 ms |
| Four injection attempts | all refused, tables intact |
| All twelve presets | parse, compile and run |

Query times are against the eight fully loaded companies. The target is 400 ms at p95 across
the full universe; the table being scanned is about 8 MB, so there is a great deal of headroom.

---

## What's next

The screener interface: a query box with column autocomplete, the results grid, the preset
list, and the 25-row wall rendered as an honest row rather than a pop-up. After that, Phase 4
— accounts, saved screens and watchlists.

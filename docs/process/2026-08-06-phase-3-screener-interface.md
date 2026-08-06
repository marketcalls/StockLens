# Phase 3 - The screener interface

**Date:** 2026-08-06
**Roadmap item:** [Phase 3 - Screener](../prd/08-roadmap.md), frontend half
**Result:** Phase 3 complete. 278 backend and 59 frontend tests pass. Verified in a browser.

---

## What got built

A query box with column autocomplete, a results grid, the twelve ready-made screens, and the
25-row wall for visitors who are not signed in.

Typing

```
Price to Earning < 20 AND Return on equity > 12
```

returns HDFC Bank, SBI, TCS and ITC in under a millisecond.

---

## Autocomplete has the same awkwardness as the parser

Column names contain spaces. The obvious way to suggest completions — look at the last word
the user typed — cannot work here: someone typing "Return on eq" has a last word of "eq",
which matches nothing useful.

So the box works backwards from the cursor to the last operator or bracket, and treats
everything after it as one fragment. "PE < 20 AND Average return on eq" produces a fragment of
"Average return on eq", which correctly suggests both "Average return on equity 3Years" and
"Average return on equity 5Years".

Tab or Enter accepts a suggestion; Ctrl+Enter runs regardless.

---

## The wall is a row, not a pop-up

A visitor who is not signed in sees 25 results. The 26th row of the table says how many more
there are and invites them to sign up.

Two deliberate choices:

- **It is inside the table**, not a modal over the top. Nothing is hidden behind a dialog that
  has to be dismissed.
- **It states the real number.** "315 more companies match. Sign up to see all 340." Showing
  25 while implying that is everything would be a lie by omission.

---

## Errors say what is wrong and where

Typing `Sharpe ratio > 1` produces:

> Unknown column: "Sharpe" (at character 1)

Not "invalid query". The backend already tracks the position of a parse failure, so the box
shows it.

---

## The tests were wrong before the code was

Seven tests failed on the first run. All seven were faults in the tests, not the components.

**The query box is controlled** — it renders whatever value it is handed. My tests passed a
fixed value and then simulated typing, so the box kept rendering the original text and no
suggestions ever appeared. The tests were asserting against a component that could not
possibly respond. Fixed by giving the test harness real state, the way the real page has.

**Two assertions were ambiguous.** A test checked the page contained the text "2" — which was
true of both the match count and the second row's number. The framework found both and refused
to guess, correctly. Now scoped to the specific table cells.

This is the third time in this project that a test has been wrong rather than the code, and
the pattern is the same each time: the test did not reproduce the conditions the component
actually runs under. Worth watching for.

---

## How I checked it works

| Check | Result |
| --- | --- |
| Backend tests | 278 pass |
| Frontend tests | 59 pass |
| TypeScript and code style | clean |
| Production build | succeeds |
| Query in a real browser | 4 companies, 0.8 ms |
| Multi-word autocomplete | "Average return on eq" suggests both 3Y and 5Y variants |
| Bad column | "Unknown column: Sharpe (at character 1)" |
| Ready-made screen | loads its query into the box and runs |
| Query kept in the address bar | yes, so a screen can be shared as a link |

---

## Phase 3 is complete

The screener works end to end: a query language, a fast engine, and an interface for it.

## What's next

Phase 4, which ends this run: accounts, roles, saved screens, watchlists and exports. The
permission model is already written down in
[04 - Roles and access](../prd/04-roles-and-access.md); the work is enforcing it in the query
layer rather than the client, so that the row cap cannot be stepped around by editing a
request.

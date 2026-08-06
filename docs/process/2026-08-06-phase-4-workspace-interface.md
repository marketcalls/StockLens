# Phase 4 - The workspace interface

**Date:** 2026-08-06
**Roadmap item:** [Phase 4 - Accounts and workflow](../prd/08-roadmap.md), frontend half
**Result:** Phase 4 complete. 339 backend and 59 frontend tests pass. Verified in a browser.

---

## What got built

Sign in and sign up, an account menu, a workspace page holding saved screens and watchlists,
a save button and CSV export on the screener, and the row cap turned into an actual
invitation.

---

## The whole thing, seen from the screen

**Signed out**, running a query that matches everything:

```
25 rows, then:
  5,312 more companies match. Create a free account to see all 5,337.
```

**Signed in**, the same page:

```
all rows, no cap
[ Name this screen ] [ Save screen ] [ Export CSV ]
```

That contrast is the entire argument for having accounts, and it is now visible rather than
described.

---

## One rule the interface follows

**The client decides what to offer. The server decides what to allow.**

The limits shown in the interface — can this person save a screen, export, see every row —
come from the server, in the same response that says who they are. Nothing is hardcoded in the
browser.

That matters because none of it is a security boundary. Someone can edit the page and make the
export button appear; the request behind it still returns 401. The interface is there to avoid
offering something that will fail, not to enforce anything. The enforcement was built and
tested in the previous slice.

---

## Small decisions

**Signing in or out clears every cached answer.** The screener result depends on who is asking
— 25 rows or all of them — so a stale cache after signing in would show the old capped result
and look broken.

**The invitation carries where you were going.** The link from the screener is
`/signup?next=/screens`, so after creating an account you land back where you were rather than
on a home page.

**The password field explains the rule before you break it.** "At least 10 characters. A short
sentence works well." — with the field marked while it is too short, rather than a rejection
after submitting.

**Sign-in failures say one thing.** The interface shows whatever the server sends, and the
server deliberately sends the same message for a wrong password, an unknown account and a
suspended one.

---

## One test failed, correctly

The test for the row-cap message asserted on the old wording, which was a plain sentence. It
is now a link. The test failed because the behaviour genuinely changed, which is what a test
is for. Updated to check the link's destination as well as its text, which is a stronger
assertion than the original.

Worth noting after the last three iterations, where the failures were all faults in the tests
rather than the code. This one was the healthy kind.

---

## How I checked it works

| Check | Result |
| --- | --- |
| Backend tests | 339 pass |
| Frontend tests | 59 pass |
| TypeScript and code style | clean |
| Production build | succeeds |
| Signed out, broad query | 25 rows plus the cap row, honest count |
| Header signed out | "Sign in" and "Get free account" |
| Sign in through the form | lands on the screener, header shows the account |
| Signed in, same query | no cap |
| Save a screen | confirmed, appears in the workspace |
| Export link | points at the export endpoint with the query attached |
| Workspace page | shows both saved screens and the watchlist with its symbol |
| Workspace signed out | invitation rather than an error |

---

## Phase 4 is complete, and so is the run

Four phases built over ten iterations:

- **Phase 0** — the skeleton: a client that talks to FinEdge, storage, and a React app
- **Phase 1** — the data layer: four statement formats discovered by measurement, 5,630
  companies, and the wide table the screener queries
- **Phase 2** — the company page: one table component rendering banks, insurers and ordinary
  companies from the same endpoint
- **Phase 3** — the screener: a query language over 118 columns, compiled to parameterised SQL
- **Phase 4** — accounts: roles, saved screens, watchlists and export

Along the way: an API key that was leaking into logs, annual figures sitting in quarterly
columns, a price-to-earnings ratio reading double because "s" sorts after "c", every bank and
insurer silently vanishing from any screen mentioning profit, and a session cookie that
stopped working in every environment except the one name I happened to check.

Each of those was found by comparing output to something real — the reference product, the
running service, the actual data — rather than by a test going red.

## What is not done

Phases 5 and 6 remain: the admin and super-admin consoles, the alerting system, scheduled
screen runs and backtesting. The full data backfill has also only been run for eight companies;
the machinery for all 5,630 is built, tested and costed at roughly 18 hours, but has not been
executed.

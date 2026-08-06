# Phase 4 - Accounts and workflow (backend)

**Date:** 2026-08-06
**Roadmap item:** [Phase 4 - Accounts and workflow](../prd/08-roadmap.md), backend half
**Result:** Working. 339 backend tests pass. Verified end to end against the running service.

---

## What got built

Accounts, the role hierarchy, saved screens, watchlists and CSV export.

The point of the whole phase is the difference between these two responses to the same query:

```
Not signed in:  5,337 companies match, showing the first 25
Signed in:      5,337 companies match, showing all of them
```

---

## Roles are numbers, not a set

Four roles: public, user, admin, super admin. Each is a superset of the one below, so a
permission check is a single comparison — "is your level at least this?" — rather than a list
of which roles may do what, which has to be kept in step by hand every time a role is added.

Every gated route uses the same dependency. No route writes its own check, so the hierarchy
exists in exactly one place.

**There is no path from a web form to an elevated role.** Signup always creates an ordinary
user. The first super admin is made by a command-line tool, and every later one by an existing
super admin. A test asserts the signup path cannot produce anything else.

---

## The cap is enforced where it cannot be argued with

A visitor who is not signed in gets 25 rows. That limit is applied inside the database query,
with the number chosen from the caller's role on the server. It is never taken from the
request.

Three tests cover the ways someone might try to step around it:

- asking for page 2 returns nothing, not rows 26 to 50
- asking for a page size of 100 still returns 25
- signing out puts the limit straight back

The true total is always reported. "5,337 match, here are 25" is honest; showing 25 and
implying that is everything is not.

---

## Two security problems found while building

### The session cookie silently stopped working

Every account test failed at first: signup returned success, but the very next request was
anonymous again.

The cause was one line deciding whether the session cookie should be marked as
HTTPS-only:

```
secure = environment != "development"
```

Which looks reasonable and is wrong. The test suite runs with the environment set to
**"test"** — not "development" — so the cookie was marked HTTPS-only and the plain-HTTP test
client correctly refused to send it back. The same would have happened to anyone running with
the environment set to "local", or "dev", or anything else.

Inferring a security flag from a free-text name only works if you happen to guess every value
anyone will ever use. It now matches against an explicit list of plain-HTTP environments, and
can be overridden outright with a setting. Tests cover both directions.

### The signing secret was too weak to sign with

The JWT library warned that the default signing secret is 18 bytes, where 32 is the minimum
for the algorithm in use. A weak secret means sessions can be forged.

The app now refuses to start with a weak or default secret anywhere that is not plain-HTTP
development, warns loudly when it is, and the example configuration file explains how to
generate a proper one.

---

## Other decisions worth recording

**One message for every failed login.** A wrong password, an account that does not exist and a
suspended account all return exactly the same response. A test compares them character for
character. Otherwise the login form becomes a way to find out who has an account.

The check also hashes a throwaway password when the account does not exist, so a missing
account and a wrong password take a similar amount of time.

**Someone else's saved screen returns "not found", not "forbidden."** "Forbidden" would confirm
it exists. Tested from a second account.

**A screen is validated before it is saved.** A saved screen that cannot run is worse than a
rejected one.

**Exports say how much they left out.** The response carries the total, the number exported
and whether it was truncated, rather than silently returning fewer rows than the user expects.

**Passwords are judged on length alone.** Composition rules push people towards predictable
substitutions without adding real strength.

---

## How I checked it works

| Check | Result |
| --- | --- |
| Backend tests | 339 pass |
| Code style | clean |
| Anonymous request | role public, 25-row cap, cannot save |
| After signup | role user, no cap, can save |
| Screener signed in | 5,337 match, 100 returned, not capped |
| Screener anonymous | 5,337 match, 25 returned, capped |
| Saved screen | stored and runs, 4 matches |
| Watchlist | symbol normalised to upper case |
| CSV export | correct headers and rows, with honest counts in the response headers |
| Export while signed out | refused, 401 |

---

## One thing that was not a bug

A signup with the address `demo@stocklens.test` was rejected. `.test` is a reserved top-level
domain that cannot receive mail, and the validator is right to refuse it. Retried with a real
domain and it worked. Worth noting because the natural first reaction was that the validator
was too strict.

---

## What's next

The interface: sign-in and sign-up forms, the saved-screens list, watchlists, an export
button, and the row-cap message becoming a real invitation to sign up rather than a
statement. That completes Phase 4.

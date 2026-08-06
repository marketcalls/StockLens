# Self-hosting StockLens

What is protected, what is not, and what you have to do yourself.

---

## Before exposing it to anything

1. **Generate a signing secret.** The app refuses to start with the default
   outside local development, but generate one anyway:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

   Put it in `.env` as `JWT_SECRET`. At least 32 bytes; a shorter one is refused.
   Changing it signs everyone out, which is also how you revoke every session at once.

2. **Set `ENVIRONMENT` to anything but a local name.** Anything outside
   `{development, dev, test, testing, local}` switches on the session cookie's
   `Secure` flag, HSTS, and a strict content security policy.

3. **Create the first account from the command line.** There is deliberately no
   path from a web form to an elevated role.

   ```bash
   python -m app.auth.cli create-super-admin you@yourdomain.com
   ```

4. **Set `CORS_ORIGINS`** to the address the frontend is actually served from.

5. **Check `.env` is not in the repository.** It is gitignored, but check.

---

## Rate limits

Applied per account when signed in, per IP otherwise — so changing address does
not reset a signed-in caller's count.

| Surface | Limit | Why |
| --- | --- | --- |
| Company pages, search, columns | 300 per minute | Cheap reads, and one page view fires several |
| Screener | 40 per minute | The expensive query and the obvious scraping target |
| Sign in / sign up | 10 per 5 minutes | Where credential stuffing lands |
| Account creation | 5 per hour | Slows bulk registration |
| CSV export | 20 per hour | Each one pulls thousands of rows |
| Workspace writes | 120 per minute | Saving screens, editing watchlists |

Exceeding one returns `429` with `Retry-After` and a message stating the limit.

### Two limitations, stated rather than hidden

- **Counters live in memory and reset when the app restarts.** This blunts
  scraping and brute force; it is not a billing quota.
- **Counters are per worker.** `uvicorn --workers 4` gives four independent
  counters, so the effective limit is four times what is configured. Run a
  single worker, or put a real limiter in front.

Turn limiting off entirely with `RATE_LIMIT_ENABLED=false` if something upstream
already does it.

---

## Behind a reverse proxy

Set `TRUST_PROXY_HEADERS=true` **only** when a proxy you control sets
`X-Forwarded-For`.

Without a proxy, leaving it on lets any caller send the header themselves and
mint a fresh identity per request, which defeats IP-based limiting completely.
It is off by default for that reason.

Also set `ALLOWED_HOSTS` to the host names you serve, so the app does not answer
to arbitrary `Host` headers.

---

## What is enforced, and where

**Everything that matters is enforced on the server.** The interface hides
options a caller cannot use, but that is convenience, not protection — the
request behind a hidden button still fails.

| Control | Where |
| --- | --- |
| Public screener capped at 25 rows | Inside the SQL query, from the caller's role |
| Saved screens, watchlists, export | Role dependency on the route |
| Someone else's saved screen | Returns 404, not 403, so it cannot be confirmed to exist |
| Screener query safety | Only catalog column names reach SQL; every literal is bound |
| Password storage | Argon2, salted |
| Session | Signed JWT in an HttpOnly, SameSite=Lax cookie |
| Login failures | One identical response for wrong password, unknown account and suspended account |

### Screener injection

The query language accepts only column names already in the catalog. Anything
else is refused before SQL exists. Verified against the running service:

```
market_cap; DROP TABLE company_snapshot; -- > 1   refused
PE > (SELECT 1)                                   refused
Sharpe ratio > 1                                  refused
```

---

## Headers sent

Always: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`,
`Permissions-Policy`, `Cross-Origin-Opener-Policy`.

Outside plain-HTTP environments, additionally a content security policy with
`script-src 'self'` and no `unsafe-eval`, plus `Strict-Transport-Security`.
HSTS is deliberately not sent from a development server, since a browser would
pin it and then refuse plain HTTP on that host.

Authenticated responses carry `Cache-Control: no-store, private`.

Request bodies over 1 MB are refused with `413` before being read.

---

## The FinEdge key

- Held as a secret type, so an accidental print shows `**********`
- Scrubbed from every log line by a filter on the root logger, including the
  HTTP library's own request logging — which is how it leaked in the first place
- Never returned by any endpoint; `/api/meta/health` reports only whether one is
  configured
- Only the ingestion worker uses it. No user request touches FinEdge.

---

## Backups

Everything is in `data/stocklens.db`. Back it up with SQLite's own mechanism
rather than copying the file while the app is running:

```bash
sqlite3 data/stocklens.db "VACUUM INTO 'backup/stocklens-$(date +%F).db'"
```

`data/stocklens_raw.db` holds the compressed FinEdge responses. It can be
rebuilt by re-fetching, so it is worth backing up but not critical.

**Test a restore before you need one.**

---

## What is not covered

Honest gaps, all deliberate rather than overlooked:

- **No email verification.** Accounts are usable immediately. Fine for a small
  instance; add verification before opening registration widely.
- **No password reset.** No email is sent, so a forgotten password needs the CLI.
- **No CSRF token.** The session cookie is `SameSite=Lax`, which stops
  cross-site form posts, and the API only accepts JSON. Add a token if you ever
  relax either.
- **No audit log viewer.** Role changes and logins are recorded in `audit_log`,
  but reading it means querying the database. The console is Phase 5.
- **No TLS.** Terminate it at a reverse proxy.
- **Redistribution rights are unconfirmed.** Serving FinEdge data to anonymous
  visitors is redistribution, and their licence terms have not been checked.
  See [open question Q3](prd/09-open-questions.md).

## Re-applying the data rules

Normalisation decides what counts as a measurement and what is an absent figure,
but it only runs when a row is fetched. A rule added in a later version never
reaches data downloaded before it, and a long backfill keeps writing with the
code it started with — so a fix that lands mid-run misses the rest of that run.

**Re-apply the data rules** in the platform console (or
`POST /api/superadmin/repair`) applies the current rules to everything already
stored. It makes no FinEdge calls, takes seconds, and reports what it changed.
Running it twice reports nothing the second time.

Worth running after upgrading, and after any download that was in flight when you
upgraded.

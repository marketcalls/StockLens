# HTTP API

50 endpoints under `/api`. Interactive docs are at `/docs` when the server is
running; this page covers the parts a schema cannot express — who may call what,
what the units are, and where the results come from.

Every route is a thin wrapper over `app/services`. If you are writing Python that
runs alongside the app, call the service instead — see [SERVICES.md](SERVICES.md).

---

## Access

| Role | Value | Gets |
| --- | --- | --- |
| Public | — | Screener (25 rows), company pages, indices |
| User | 10 | Full result sets, saved screens, watchlists, CSV export |
| Admin | 20 | Everything a user gets, plus data quality |
| Super Admin | 30 | Ingestion control |

| Route | Notes |
| --- | --- |
| `POST /api/auth/signup` | `{email, password, display_name}` |
| `POST /api/auth/login` | `{email, password}` |
| `POST /api/auth/logout` | Clears the cookie |
| `GET /api/auth/me` | Current session, role and limits |
| `GET /api/auth/limits` | The caller's row cap and rate limits |
| `GET /api/limits/screener` | Row cap for the screener alone |
| `GET /api/superadmin/me` | Confirms super-admin access |

The token comes back as an HttpOnly `SameSite=Lax` cookie, so a browser needs
nothing extra; a script must keep the cookie jar (`curl -c/-b`, `httpx.Client()`).

`limits` is what the UI uses to explain why a result set stops where it does
rather than silently truncating.

**The email address is a login identifier, not a delivery address.** This is
self-hosted, so `admin@stocklens.local` and `admin@localhost` are accepted. The
same rule applies to the `stocklens-auth` CLI, so an account the CLI creates can
always sign in.

## Rate limits

Per identity — user id when signed in, client IP otherwise — in a sliding window.

| Bucket | Allowance | Applies to |
| --- | --- | --- |
| Read | 300 / min | Company, index, meta |
| Screener | 40 / min | Running queries |
| Write | 120 / min | Screens and watchlists |
| Auth | 10 / 5 min | Login |
| Signup | 5 / hour | Registration |
| Export | 20 / hour | CSV |

Over the limit returns 429 with `Retry-After`. Limits are in-process, which is
correct for one self-hosted instance and would need Redis behind a load balancer.

---

## Companies

| Route | Notes |
| --- | --- |
| `GET /api/search?q=` | Autocomplete over 5,630 symbols |
| `GET /api/companies?limit=` | Largest by market cap |
| `GET /api/companies/{symbol}` | Profile, quote, index membership, key ratios |
| `GET /api/companies/{symbol}/statements` | `statement=pl\|bs\|cf`, `period=annual\|quarterly\|ttm`, `type=c\|s` |
| `GET /api/companies/{symbol}/ratios` | `family=profitability\|leverage\|liquidity\|efficiency` |
| `GET /api/companies/{symbol}/shareholding` | Holding by group, by quarter |
| `GET /api/companies/{symbol}/peers` | Sector peers with medians |
| `GET /api/companies/{symbol}/prices?limit=` | Daily OHLCV, oldest first |
| `GET /api/companies/{symbol}/corporate-actions` | Dividends, splits, bonus, rights |

**Statements come in four shapes.** Banks, life insurers, general insurers and
everyone else file different line items, so the response carries a `schema_kind`
(`bank`, `life_insurance`, `general_insurance`, `general`) and its own row order.
Do not assume "Sales" exists — a bank reports Interest and Financing Profit, a
life insurer Gross Premium Income and Change in Actuarial Liability. Read the
rows you are given.

**Consolidated is the default and may not exist.** Only 2,510 of 5,630 companies
file consolidated statements. Ask for `type=c` and the response may come back
`statement_type: "s"`; the field tells you what you actually got.

**Ratio families take either name.** FinEdge's codes are `pr`, `le`, `li` and
`ef`; the readable names `profitability`, `leverage`, `liquidity` and
`efficiency` work too, and `solvency` is accepted for leverage. An unknown name
returns 404 listing the real ones, rather than an empty result that would look
like a company with no ratios. Valuation ratios are not here — P/E, P/B and the
rest come back with the company profile and are screenable.

**Check `available` before reading `rows`.** A company whose statements have not
been downloaded yet returns `available: false` with a `reason` and empty rows.
The response has the same keys either way, so nothing needs a defensive `get`.

**Missing is not zero.** `null` means the company never reported the line.

## Indices

| Route | Notes |
| --- | --- |
| `GET /api/indices?index_type=&limit=` | All 239, recognisable ones first |
| `GET /api/indices/movers?limit=` | Best and worst today |
| `GET /api/indices/{index_symbol}` | Constituents, returns, medians |

`detail` returns three counts that mean different things. `count` is every
member. `with_fundamentals` is how many have had their statements downloaded —
every listed company has a quote, but only backfilled ones have financials.
`outside_universe` is members that are not equities at all: 28 across the BSE
indices are REITs, InvITs or SME listings, identified by scrip code, with no
company page and no statements they could ever have. Each constituent carries an
`in_universe` flag.

Index membership is also screenable: `Index = "NIF50" AND Price to Earning < 20`.

## Screener

| Route | Notes |
| --- | --- |
| `GET /api/screener/columns` | The catalog — 119 columns with units and aliases |
| `POST /api/screener/validate` | `{query}` → `{valid, message, position}` |
| `POST /api/screener/run` | `{query, sort, order, page, per_page}` |
| `GET /api/screener/presets` | Twelve ready-made screens |
| `POST /api/screener/presets/{slug}/run` | Run one |
| `GET /api/export/screen?query=` | CSV, signed-in only |

Read `columns` before composing a query. Any name not in the catalog is
rejected at parse time, with `position` pointing at the offending character.

**Units.** Money in Rs. Crore. Percentages as plain numbers — `Return on equity >
15` means 15%. Ratios unitless.

```
Market Capitalization > 500 AND Price to Earning < 15 AND Return on equity > 18
```

`AND`, `OR`, `NOT`, parentheses, comparisons, and column-to-column comparisons
(`Debt < Reserves`) all work. Public callers get 25 rows; `total` is always the
true count, so the UI can say what is being withheld.

**A company with no value for a column matches nothing on it — either way
round.** `NOT (Price to Earning > 20)` returns companies known to trade under 20
times earnings, not the thousands whose statements have yet to be downloaded.
`NOT (x > n)` and `x <= n` give the same answer. To find companies that report
nothing, screen on something they do report.

## Saved work

| Route | Effect |
| --- | --- |
| `GET /api/screens` | Your saved screens |
| `POST /api/screens` | `{name, query, description}` |
| `GET /api/screens/{screen_id}` | One screen |
| `PATCH /api/screens/{screen_id}` | Update it |
| `DELETE /api/screens/{screen_id}` | Remove it |
| `POST /api/screens/{screen_id}/run` | Run it |
| `GET /api/watchlists` | Your lists, with their symbols |
| `POST /api/watchlists` | `{name}` |
| `DELETE /api/watchlists/{watchlist_id}` | Remove a list |
| `POST /api/watchlists/{watchlist_id}/items` | `{symbol, note}` |
| `DELETE /api/watchlists/{watchlist_id}/items/{symbol}` | Remove a symbol |

Signed-in only, and scoped to the owner — someone else's screen returns 404, not
403, since 403 would confirm it exists.

## Ingestion — Super Admin

| Route | Effect |
| --- | --- |
| `GET /api/superadmin/status` | Active run and the last ten |
| `GET /api/superadmin/runs/{run_id}` | One run, with failures |
| `POST /api/superadmin/plan` | Cost of a backfill, spends nothing |
| `POST /api/superadmin/universe` | Symbol master, indices, quotes, returns |
| `POST /api/superadmin/prices` | Every company's quote, one call |
| `POST /api/superadmin/backfill` | `{limit, symbols, call_budget}` — background |
| `POST /api/superadmin/materialise` | Rebuild the screener table |
| `POST /api/superadmin/repair` | Re-apply the data rules to stored rows |
| `POST /api/superadmin/runs/{run_id}/release` | Clear a run whose process died |
| `GET /api/superadmin/quality` | Data quality checks |

`backfill` returns a `run_id` immediately and reports progress through `status`,
which reports `symbols_done` and `symbols_total` — companies, not tasks, because
task rows are written as the run reaches each company and would read as complete
throughout.

One long job at a time, enforced through the database so it holds against a job
started by the CLI or another worker; a second returns 409 naming the one in the
way. A run still marked running after 24 hours is treated as abandoned, which is
longer than the ~18 hours a full universe backfill takes. `release` is for an
operator who already knows a job died — it does not stop a live one.

Every call here is written to `audit_log` with the actor, action and IP.

## Meta

`GET /api/meta/health` is unauthenticated and checks the database, since that is
the dependency whose loss breaks every read. It returns 200 / `"ok"`, or 503 /
`"degraded"` with the error — so a container healthcheck can act on the status
line alone.

It does **not** probe FinEdge by default; that is an outbound call to a third
party, and FinEdge being down does not stop StockLens serving data it already
holds. Add `?finedge=true` when you want it checked.

| Route | Notes |
| --- | --- |
| `GET /api/meta/health` | Liveness; `?finedge=true` to probe upstream too |
| `GET /api/meta/counts` | Row counts per table |
| `GET /api/meta/freshness` | What is held and when it was fetched |
| `GET /api/meta/quality` | Data quality checks |

`counts`, `freshness` and `quality` are for operators.

---

## Errors

`detail` is a sentence fit to show a person. Any context the service attached
sits alongside it, so a program does not have to parse English:

```json
{ "detail": "No company with the symbol FOO", "symbol": "FOO" }
```

Query errors are the one exception: `detail` is an object carrying `message` and
`position`, because the editor underlines the offending character.

```json
{ "detail": { "message": "Unknown column: \"Bogus\"", "position": 26 } }
```

| Status | Means |
| --- | --- |
| 400 | Unparseable query; `position` marks the character |
| 401 | Not signed in |
| 403 | Role insufficient |
| 404 | Unknown symbol, index, run or screen |
| 409 | Duplicate name, or a job already running |
| 413 | Body over 1 MB |
| 429 | Rate limited; see `Retry-After` |

Domain errors are raised by the service layer and mapped to status codes once,
in `app/api/_translate.py`.

## Notes

- **Reads never reach FinEdge.** Everything is served from SQLite. Only the
  Super Admin ingestion routes talk upstream.
- **Dates are ISO 8601.** Timestamps are UTC.
- **CORS** is restricted to the configured frontend origin, with credentials
  enabled so the session cookie travels.

# HTTP API

49 endpoints under `/api`. Interactive docs are at `/docs` when the server is
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

Sign in with `POST /api/auth/login`. The token comes back as an HttpOnly
`SameSite=Lax` cookie, so a browser needs nothing extra; a script must keep the
cookie jar (`curl -c/-b`, `httpx.Client()`).

`GET /api/auth/limits` returns the caller's row cap and rate limits, which is
what the UI uses to explain why a result set stops where it does rather than
silently truncating.

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
| `GET /api/companies/{symbol}/ratios` | `family=profitability\|liquidity\|solvency\|efficiency\|valuation` |
| `GET /api/companies/{symbol}/shareholding` | Holding by group, by quarter |
| `GET /api/companies/{symbol}/peers` | Sector peers with medians |
| `GET /api/companies/{symbol}/prices?limit=` | Daily OHLCV, oldest first |
| `GET /api/companies/{symbol}/corporate-actions` | Dividends, splits, bonus, rights |

**Statements come in four shapes.** Banks, life insurers, general insurers and
everyone else file different line items, so the response carries a `family` and
its own row order. Do not assume "Sales" exists — read the rows you are given.

**Consolidated is the default and may not exist.** Only 2,510 of 5,630 companies
file consolidated statements. Ask for `type=c` and the response may come back
`statement_type: "s"`; the field tells you what you actually got.

**Missing is not zero.** `null` means the company never reported the line.

## Indices

| Route | Notes |
| --- | --- |
| `GET /api/indices?index_type=&limit=` | All 239, recognisable ones first |
| `GET /api/indices/movers?limit=` | Best and worst today |
| `GET /api/indices/{index_symbol}` | Constituents, returns, medians |

`detail` returns `count` and `with_fundamentals` separately. Every listed
company has a quote; only backfilled ones have statements.

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

## Saved work

`GET|POST /api/screens`, `GET|PATCH|DELETE /api/screens/{id}`,
`POST /api/screens/{id}/run`, and the same shape for `/api/watchlists` with
`/items` underneath. Signed-in only, and scoped to the owner — someone else's
screen returns 404, not 403.

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
| `GET /api/superadmin/quality` | Data quality checks |

`backfill` returns a `run_id` immediately and reports progress through `status`.
One long job at a time; a second returns 409. The full universe is roughly
332,000 calls and eighteen hours.

Every call here is written to `audit_log` with the actor, action and IP.

## Meta

`GET /api/meta/health` is unauthenticated and checks the database, since that is
the dependency whose loss breaks every read. It returns 200 / `"ok"`, or 503 /
`"degraded"` with the error — so a container healthcheck can act on the status
line alone.

It does **not** probe FinEdge by default; that is an outbound call to a third
party, and FinEdge being down does not stop StockLens serving data it already
holds. Add `?finedge=true` when you want it checked.

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

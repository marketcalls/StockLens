# The service layer

Every capability StockLens has is a plain Python function in `app/services`,
taking and returning plain data. The HTTP routes in `app/api` are thin wrappers
over these.

That split exists so a future agent can call StockLens directly rather than
talking to it over HTTP:

```python
from app.services import company, index, screener

company.profile("RELIANCE")
screener.run("Price to Earning < 20 AND Return on equity > 12")
index.detail("NIF50")
```

Nothing in `app/services` imports FastAPI, knows about requests, or raises HTTP
errors. It also makes every rule testable without a client.

---

## Rules the layer follows

**Plain data in, plain data out.** Arguments are strings, numbers and lists;
returns are dicts and lists. No ORM objects, no response models, nothing that
needs FastAPI to interpret.

**Domain errors, not status codes.** Services raise `NotFound`, `InvalidQuery`,
`Conflict`, `Forbidden`. `app/api/_translate.py` maps them to status codes once,
at the edge, so no route needs a try block and a non-HTTP caller gets a
meaningful Python exception.

**Authorisation is in the service, not the route.** `workspace.get_screen`
checks ownership itself, so an agent gets the same guarantee a browser does.
Someone else's screen raises `NotFound` rather than `Forbidden`, since
`Forbidden` would confirm it exists.

**An engine can be injected.** Every function takes an optional `engine=`, which
defaults to the configured database. Tests pass a temporary one; nothing needs
patching.

---

## Modules

### `services.company`

| Function | Returns |
| --- | --- |
| `search(term, limit=10)` | Ranked autocomplete matches |
| `profile(symbol)` | Identity, classification, quote, index membership, key ratios |
| `statements(symbol, code, period, statement_type)` | A rendered statement table |
| `ratios(symbol, family, statement_type)` | A ratio family as a time series |
| `shareholding_pattern(symbol)` | Holding by group across quarters |
| `peers(symbol, limit=10)` | Sector peers with medians |
| `prices(symbol, limit=2000)` | Daily OHLCV, oldest first |
| `corporate_actions(symbol)` | Dividends, splits, bonus, rights |
| `largest(limit=50)` | Largest companies by market cap |

`statements` falls back to the other statement type when the requested one is
absent — only 2,510 of 5,630 companies file consolidated — and reports which it
actually used in `statement_type`. Check that field rather than assuming you got
what you asked for.

`code` is `pl`, `bs` or `cf`. `period` is `annual`, `quarterly` or `ttm`.
`statement_type` is `c` (consolidated) or `s` (standalone).

### `services.screener`

| Function | Returns |
| --- | --- |
| `columns()` | The full column catalog, grouped by source |
| `validate(query)` | `{valid, message, position}` without executing |
| `run(query, ...)` | Matching companies with the true total |
| `presets()` | The twelve ready-made screens |
| `run_preset(slug)` | One of them, executed |
| `resolve_column(name)` | Look a column up by label, key or alias |

**Read `columns()` before writing a query.** It is the authoritative list of what
can be screened on and what units each column expects. Money is in Rs. Crore,
percentages are plain numbers (`Return on equity > 15` means 15%), ratios are
unitless.

`run(..., row_cap=None)` is uncapped, which is correct for a server-side caller.
The HTTP layer passes the limit for the caller's role.

`validate` is cheap enough to call before saving or scheduling a query.

### `services.index`

| Function | Returns |
| --- | --- |
| `listing(index_type=None, limit=300)` | All 239 indices, recognisable ones first |
| `detail(index_symbol)` | One index with constituents, returns and medians |
| `movers(limit=10)` | Best and worst index performance today |

`detail` reports `count` (constituents) and `with_fundamentals` separately.
Every listed company has a quote; only backfilled ones have statements, so the
two differ until the backfill has run.

### `services.ingest`

| Function | Effect |
| --- | --- |
| `plan(limit=None)` | Cost of a backfill without spending it |
| `status()` | Current and recent runs with progress |
| `run_detail(run_id)` | One run, with task counts and failures |
| `start_universe_sync()` | Symbol master, indices, index quotes and returns |
| `start_price_refresh()` | Every company's quote, one call |
| `start_backfill(limit=, symbols=, call_budget=)` | Background download |
| `rebuild_snapshot()` | Re-materialise the screener table |
| `quality()` | Data quality checks |

One long job at a time — SQLite has a single writer, and two backfills would
fight over it while doubling the request rate against FinEdge. Starting a second
raises `Conflict`.

`start_backfill` returns immediately with a `run_id`; poll `status()` or
`run_detail(run_id)` for progress. The full universe is roughly 332,000 calls and
eighteen hours.

### `services.workspace`

Saved screens and watchlists, all taking a `user_id` as the first argument.
Ownership is checked inside every function.

---

## Errors

```python
from app.services import NotFound, InvalidQuery, Forbidden, ServiceError
```

| Error | Status | Raised when |
| --- | --- | --- |
| `NotFound` | 404 | Unknown symbol, index, run or screen |
| `InvalidQuery` | 400 | A query could not be parsed; carries `position` |
| `Conflict` | 409 | Duplicate name, or a job already running |
| `Forbidden` | 403 | Role insufficient |

`InvalidQuery.position` is the character offset of the fault, which the query
editor uses to point at it.

---

## Notes for an agent

- **Call the service, not the endpoint.** In-process avoids HTTP, serialisation
  and the role-based row cap, which is a UI concern rather than a data one.
- **`columns()` first, then `validate()`, then `run()`.** The query language
  rejects any name not in the catalog, so guessing wastes a round trip.
- **Nothing here reaches FinEdge.** Reads are served from SQLite. Only
  `services.ingest` talks to the upstream API, and only when explicitly called.
- **Check `available` and `statement_type`** on a statement response before
  using it.
- **Missing is not zero.** A `None` means the company never reported that line.
  Treating it as zero will produce wrong ratios.

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

The response also carries `schema_kind`: `general`, `bank`, `life_insurance` or
`general_insurance`. The four file different line items, so the row labels differ
by family. Read the rows rather than looking for a label you expect.

`code` is `pl`, `bs` or `cf`. `period` is `annual`, `quarterly` or `ttm`.
`statement_type` is `c` (consolidated) or `s` (standalone).

`ratios` takes a `family` of `profitability`, `leverage`, `liquidity` or
`efficiency` — or FinEdge's own codes `pr`, `le`, `li`, `ef`, which is what the
stored rows use. `solvency` is accepted for leverage. An unknown name raises
`NotFound` listing the real ones rather than returning an empty result, which
would read as a company that files no ratios.

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

`detail` reports `count`, `with_fundamentals` and `outside_universe`
separately. Every listed company has a quote but only backfilled ones have
statements, so the first two differ until the backfill has run. The third counts
members that are not equities — REITs, InvITs and SME listings, which the
exchange identifies by scrip code and which have no company row at all. Each
constituent carries `in_universe`.

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
| `repair()` | Re-apply the data rules to rows already stored |
| `release_stuck_run(run_id)` | Clear a run whose process died |
| `quality()` | Data quality checks |

One long job at a time — SQLite has a single writer, and two backfills would
fight over it while doubling the request rate against FinEdge. The lock lives in
the database, not in process memory, so it holds against a job started by the
CLI or a second worker. Starting a second raises `Conflict` naming the one in
the way.

A run still marked running after `STALE_RUN_AFTER` (24 hours, longer than the
~18 a full backfill takes) is treated as abandoned. `release_stuck_run` is the
operator saying they know a job died; it cannot stop a live one, because nothing
here can reach into another process.

`start_backfill` returns immediately with a `run_id`; poll `status()` or
`run_detail(run_id)` for progress, which reports `symbols_done` and
`symbols_total`. Measure in companies, not tasks: task rows are written as the
run reaches each company, so a task ratio reads as complete throughout. The full universe is roughly 332,000 calls and
eighteen hours.

### `services.users`

| Function | Returns |
| --- | --- |
| `listing(term=, role=, include_inactive=)` | Accounts with what each owns |
| `detail(user_id)` | One account, its screens, lists and audit trail |
| `change_role(actor, user_id, role)` | Moves an account between roles |
| `set_active(actor, user_id, active)` | Suspends or restores |
| `invite(actor, email, role)` | Creates an account, returns a one-time password |
| `roles()` / `stats()` | What can be assigned, and headline counts |

Every mutating function takes the acting user as its first argument, because the
rules depend on who is asking: you cannot lower your own role, grant a role above
your own, act on a super administrator unless you are one, or remove the last
active super administrator. Accounts are suspended, never deleted.

### `services.diagnostics`

| Function | Returns |
| --- | --- |
| `health()` | Errors in the last 24h, last failure, last run, storage sizes |
| `logs(level=, logger=, limit=)` | Recent warnings and errors |
| `entry(log_id)` | One record, with its traceback |

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
- **A screener condition never matches an unknown**, whichever way it is
  written. `NOT (Price to Earning > 20)` is the same set as
  `Price to Earning <= 20`, not the whole universe minus the expensive ones.

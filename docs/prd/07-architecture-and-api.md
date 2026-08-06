# 07 - Architecture and API

## Stack

Fixed by decision, not open for re-litigation:

| Layer | Choice |
| --- | --- |
| Backend | **FastAPI** (Python 3.12+) |
| Frontend | **React** (Vite, TypeScript) |
| Database | **SQLite** (WAL mode) |
| UI components | **shadcn/ui** on Tailwind CSS, with a light/dark theme switcher |

Supporting choices that follow from those:

| Concern | Choice | Why |
| --- | --- | --- |
| ORM / query layer | SQLAlchemy 2.x Core, plus raw SQL for the screener | The screener compiler emits SQL directly; an ORM would be in the way |
| Migrations | Alembic | Standard with SQLAlchemy, works fine against SQLite with batch mode |
| HTTP client | `httpx.AsyncClient` | Async, connection-pool control, matches FastAPI |
| Validation | Pydantic v2 | Ships with FastAPI; also models the FinEdge response shapes |
| Background jobs | APScheduler in-process, plus a standalone CLI worker for backfill | No Redis or Celery needed at this scale; the backfill worker is a long-running script that owns the write connection |
| Auth | JWT in an HTTP-only cookie, `passlib[argon2]` for password hashing | No third-party dependency for v1 |
| Frontend data fetching | TanStack Query | Caching, background refetch, pagination out of the box |
| Tables | TanStack Table | The screener grid and every statement table need virtualisation and column pinning |
| Charts | Recharts | Price, valuation-band and segment charts |
| Theme | `next-themes`-style provider with `class` strategy on `<html>` | shadcn/ui's documented dark-mode approach |
| Testing | pytest + httpx test client; Vitest + Testing Library | |

## Why SQLite works for this

The instinct is that a 5,630-company financial database needs Postgres. It does not, and the
numbers say why:

| Quantity | Size |
| --- | --- |
| `company_snapshot` (the screener table) | 5,630 rows x ~180 REAL columns, roughly **8 MB** |
| Symbol master, indices, constituents | under 5 MB |
| `price_daily`, 13 years x 5,630 symbols | ~19 M rows, roughly **1.2 GB** |
| `price_ratio_daily`, 8 years x 5,630 | ~11 M rows, roughly **600 MB** |
| Statement lines, all periods and schemas | ~25 M rows, roughly **1.5 GB** |
| Shareholding, documents, corporate actions | roughly **500 MB** |
| **Serving database total** | **~4 GB** |
| Raw response archive (separate file, compressed) | ~3 GB |

SQLite handles multi-gigabyte databases without complaint. The access pattern is the ideal
one for it:

- **One writer** - the ingestion worker, running nightly
- **Many readers** - the FastAPI web tier
- **WAL mode** - readers are never blocked by the writer
- **Read-heavy, mostly point and range queries** on indexed columns
- **No multi-tenant write contention** - user writes (saved screens, watchlists) are tiny and
  infrequent compared to reads

The screener query - the hottest path - scans an 8 MB table. That is a sub-5 ms operation
entirely in page cache.

### Where SQLite constrains us, and how we work around it

| Constraint | Workaround |
| --- | --- |
| No array type | `snapshot_index_membership` junction table |
| No native `jsonb` | JSON stored as TEXT, queried with `json_extract`; raw payloads stored as compressed BLOB |
| Single writer | Ingestion batches commits every 200 tasks; user writes go through a short-lived write connection with `busy_timeout` |
| No `pg_trgm` | FTS5 virtual table for company search, which is faster than trigram for prefix search anyway |
| No materialised views | The materialisation step writes `company_snapshot` explicitly at the end of each run |
| Weak typing by default | `STRICT` tables everywhere |
| Limited concurrent write throughput | Not a factor: nothing in this product has concurrent write pressure |
| No network access | Backend and database live on the same host by design |

### The migration trigger

Move to Postgres only if one of these becomes true. Until then, SQLite is the correct choice
and adds real operational simplicity (one file, trivial backup, no server to run).

- Sustained concurrent write load from users exceeding roughly 50 writes/second
- Need to run the web tier on more than one host
- Need read replicas for geographic distribution
- A single query regularly exceeding 500 ms that indexing cannot fix

The three-layer data model in [06](06-data-model-and-ingestion.md) is deliberately
portable - SQLAlchemy Core plus Alembic means the migration is a schema translation, not a
rewrite.

## Service layout

```
stocklens/
  backend/
    app/
      main.py                 FastAPI app, middleware, CORS, lifespan
      config.py               Pydantic Settings, reads .env
      db/
        engine.py             SQLite engine, PRAGMA setup, session factory
        models.py             SQLAlchemy table definitions
        migrations/           Alembic
      auth/
        router.py             signup, login, logout, me, password reset
        security.py           argon2 hashing, JWT issue and verify
        deps.py               require_role dependency, current_user
      finedge/
        client.py             async client: auth, retry, backoff, redaction
        endpoints.py          typed wrapper per FinEdge endpoint
        schemas.py            Pydantic models of FinEdge responses
      ingest/
        jobs/                 universe, price, delta, feeds, shareholding, backfill
        normalise.py          raw JSON -> layer 2 tables, schema_kind aware
        materialise.py        layer 2 -> company_snapshot
        quality.py            post-run data quality checks
        worker.py             CLI entrypoint for long-running backfill
      screener/
        catalog.py            column catalog: name, type, unit, source, aliases
        parser.py             query text -> AST
        compiler.py           AST -> parameterised SQL
        execute.py            run, cache, paginate, apply role limits
      api/
        companies.py          company page endpoints
        screener.py           screen run, save, presets
        market.py             indices, calendars, movers, heatmap
        watchlist.py          watchlists, notes, comparisons
        alerts.py             alert rules and inbox
        admin.py              admin console
        superadmin.py         data platform console
    tests/
  frontend/
    src/
      components/ui/          shadcn/ui primitives
      components/             app components (StatementTable, ScreenerGrid, ...)
      features/               company, screener, market, watchlist, admin
      lib/                    api client, formatters, query keys
      providers/              ThemeProvider, QueryClientProvider, AuthProvider
      routes/
  data/
    stocklens.db              serving database
    stocklens_raw.db          raw response archive
  docs/prd/
```

## Frontend notes

### Theme switcher
shadcn/ui's `class` dark-mode strategy: a `ThemeProvider` writes `light` or `dark` onto
`<html>`, persists the choice to `localStorage`, and defaults to the system preference. The
switcher is a three-state control (Light / Dark / System) in the header. All colours come
from the CSS custom properties shadcn defines, so no component hard-codes a colour.

Financial tables need one extra consideration: positive and negative value colours must be
readable in both themes and must not rely on red/green alone. Negative numbers get a minus
sign and a distinct weight, not just a colour.

### Components that carry the product
- **StatementTable** - the shared renderer behind Quarterly Results, P&L, Balance Sheet,
  Cash Flow and Ratios. Handles horizontal scroll with a pinned first column, expandable
  "+" detail rows, consolidated/standalone toggle, and the three schema variants
  (general / bank / insurance).
- **ScreenerGrid** - virtualised, sortable, column-configurable, with the public 25-row wall
  rendered as a real row rather than a modal.
- **QueryEditor** - textarea with column-name autocomplete, inline validation and an
  AST-driven visual builder as an alternative input mode.
- **ValuationBandChart** - the daily P/E, P/B, P/S, P/FCF series against its own 5-year
  median band.

## StockLens API surface

All responses JSON. All list endpoints paginate with `limit` and `offset`. Role enforcement
is a FastAPI dependency, never a client-side check.

### Public - no authentication

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/search?q=` | Company autocomplete (FTS5) |
| GET | `/api/companies/{symbol}` | Header, profile, key ratios, index membership |
| GET | `/api/companies/{symbol}/pros-cons` | Generated Pros/Cons with the rule that fired |
| GET | `/api/companies/{symbol}/statements` | `?code=pl\|bs\|cf&period=&type=` |
| GET | `/api/companies/{symbol}/ratios` | `?family=pr\|le\|li\|ef` (public gets `ef`) |
| GET | `/api/companies/{symbol}/metrics` | Growth, average, cumulative |
| GET | `/api/companies/{symbol}/peers` | Peer table with default columns |
| GET | `/api/companies/{symbol}/shareholding` | Aggregate percentages by quarter |
| GET | `/api/companies/{symbol}/prices` | OHLCV series |
| GET | `/api/companies/{symbol}/valuation-series` | Daily pe/pb/ps/pfcf |
| GET | `/api/companies/{symbol}/documents` | Announcements, ratings, concalls, presentations |
| GET | `/api/companies/{symbol}/corporate-actions` | Dividends, splits, bonus, rights |
| GET | `/api/companies/{symbol}/segments` | Revenue by segment |
| POST | `/api/screener/run` | Run a query. Public capped at 25 rows, true count returned |
| GET | `/api/screener/columns` | Column catalog for autocomplete and the builder |
| GET | `/api/screener/presets` | Featured public screens |
| GET | `/api/market/indices` | Index dashboard |
| GET | `/api/market/indices/{index_symbol}` | Constituents, returns, valuation history |
| GET | `/api/market/movers` | Gainers, losers, volume spikes, 52-week breakouts |
| GET | `/api/market/heatmap` | Sector aggregates |
| GET | `/api/market/calendar/{results\|ipo\|actions\|holidays}` | Calendars |
| GET | `/api/market/announcements` | Market-wide feed |
| GET | `/api/meta/freshness` | Data timestamps shown in the footer |

### User - authenticated

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/auth/signup` `login` `logout` | Session lifecycle |
| GET | `/api/auth/me` | Current user and role |
| GET/POST/PATCH/DELETE | `/api/screens` | Saved screens with version history |
| POST | `/api/screens/{id}/run` | Run a saved screen |
| GET | `/api/screens/{id}/diff` | Entrants and exits since last run |
| POST | `/api/screens/{id}/backtest` | Historical evaluation |
| GET/POST/DELETE | `/api/watchlists` | Watchlists and membership |
| GET/PUT | `/api/companies/{symbol}/notes` | Private notes and tags |
| POST | `/api/compare` | Up to 10 companies across any columns |
| GET/POST/DELETE | `/api/alerts` | Alert rules |
| GET | `/api/alerts/inbox` | Triggered alerts |
| POST | `/api/export/{screen\|watchlist\|statement}` | CSV or Excel |
| GET/POST/DELETE | `/api/keys` | Personal read-only API keys |
| GET | `/api/columns/custom` | Custom derived columns |

Registered-user versions of the public company endpoints return the full payload -
all 31 ratios, named shareholders, notes to accounts - via the same paths, gated by the
dependency rather than by a separate route.

### Admin

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/admin/data-quality` | Completeness matrix |
| GET | `/api/admin/stale` | Stale data report |
| POST | `/api/admin/refetch` | Targeted re-fetch, symbol-scoped |
| GET | `/api/admin/runs` | Ingestion job history |
| GET | `/api/admin/runs/{id}/tasks` | Task-level detail |
| GET/PATCH | `/api/admin/users` | View, suspend, reset |
| PATCH | `/api/admin/companies/{symbol}/classification` | Sector override |
| PATCH | `/api/admin/presets` | Curate featured screens |

### Super Admin

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/superadmin/backfill` | Start a full or scoped backfill |
| POST | `/api/superadmin/backfill/dry-run` | Call count and duration estimate, no fetching |
| POST | `/api/superadmin/runs/{id}/{pause\|resume\|abort}` | Run control |
| GET | `/api/superadmin/runs/{id}/progress` | Server-sent events: live progress |
| GET/PUT | `/api/superadmin/schedule` | Job schedule configuration |
| GET/PUT | `/api/superadmin/credentials` | Key rotation, write-only, masked fingerprint |
| POST | `/api/superadmin/credentials/test` | Connectivity check |
| GET/PUT | `/api/superadmin/budget` | Call quotas and hard stops |
| GET | `/api/superadmin/raw` | Raw FinEdge payload inspector |
| PATCH | `/api/superadmin/users/{id}/role` | Role assignment |
| POST | `/api/superadmin/rebuild` | Re-materialise `company_snapshot` from layer 2 |
| GET | `/api/superadmin/usage` | Calls, bytes, duration by endpoint |

## Cross-cutting requirements

- **Role enforcement in one place.** A `require_role(Role.USER)` dependency, and a
  `apply_result_limits(user, query)` helper in the screener execution path. No route
  implements its own check.
- **The FinEdge token never appears in a response, a log line, or an error message.**
  The client redacts the query string before any logging.
- **No icons or emoji in code or log output** (project convention).
- **Every response that renders financial data carries an `as_of` timestamp** so the frontend
  can show freshness without a second request.
- **Errors are typed.** A missing statement returns a structured "not available for this
  company" payload with the reason, not a 404 or an empty array that the UI misreads as zero.

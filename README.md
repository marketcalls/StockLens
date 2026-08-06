# StockLens

Stock analysis and screening for Indian equities (NSE + BSE), built on the FinEdge
financial data API. Self-hosted.

Anyone can screen the market and read a company's fundamentals without signing up. Signing
up turns a one-off lookup into an ongoing workflow: saved screens, watchlists and exports
that persist.

## What is here

| | |
| --- | --- |
| **Screener** | A query language over 119 columns — `Market Capitalization > 500 AND Price to Earning < 15 AND Return on equity > 18` — compiled to parameterised SQL. Twelve ready-made screens. |
| **Company pages** | Statements, ratios, shareholding, prices and corporate actions, at `/company/RELIANCE` and `/company/RELIANCE/consolidated`. |
| **Index pages** | All 239 NSE and BSE indices with constituents, valuation and returns across eight horizons. Index membership is screenable. |
| **Accounts** | Four roles, saved screens, watchlists, CSV export. |
| **Platform console** | Trigger and watch the FinEdge download, rebuild the screener table, repair stored data. |
| **People** | Account administration, with the rules that stop an administrator locking everyone out. |
| **Diagnostics** | Warnings, errors and tracebacks kept where an operator can read them. |

Light and dark theme. Responsive from a phone to a desktop.

## Stack

| Layer | Choice |
| --- | --- |
| Backend | FastAPI (Python 3.12+) |
| Frontend | React (Vite, TypeScript) |
| Database | SQLite (WAL mode) |
| UI | shadcn/ui on Tailwind CSS |

Around 480 backend and 85 front-end tests.

## Data

FinEdge covers 5,630 NSE/BSE symbols with 8 years of annual P&L and balance sheet, 5 years
of cash flow, 33 quarters of results, 13 years of daily prices, 41 quarters of shareholding
pattern, and roughly 150 pre-computed ratios per company.

A single call to `/api/v1/quote` with no symbol returns live price, market cap, 52-week range
and volume for the entire universe, which is what makes the daily refresh one API call rather
than 5,630. Financial statements are the slow part: 59 calls per company, so the full set is
roughly 332,000 calls and eighteen hours. The console takes a company count so you can
download the names people actually search for first — companies are ordered by index
membership, then by market cap.

**Companies file four different kinds of statement.** Banks, life insurers, general insurers
and everyone else report different line items, so there is no single "Sales" row to rely on.
The schema family is measured from the data rather than assumed.

Full inventory, measured limits and known gaps:
[docs/prd/02-data-source-inventory.md](docs/prd/02-data-source-inventory.md).

## Roles

| Role | Capability |
| --- | --- |
| Public | Screener (25 rows) and company pages |
| User | Full result sets, saved screens, watchlists, export |
| Admin | Plus accounts, data quality and diagnostics |
| Super Admin | Plus the FinEdge download and role assignment |

## Setup

```bash
cp .env.example .env
# add your FINEDGE_API_KEY, and set JWT_SECRET to at least 32 random bytes

cd backend
python -m venv .venv && .venv/bin/pip install -e ".[dev]"   # .venv/Scripts on Windows
.venv/bin/python -m app.auth.cli create-super-admin you@example.com
.venv/bin/python -m uvicorn app.main:app

cd ../frontend && npm install && npm run dev
```

Tables are created on first start, so there is no migration step. The app refuses
to start with a weak `JWT_SECRET` anywhere that is not plain-HTTP development,
because a guessable signing secret means sessions can be forged.

Sign in, open **Console**, and run the universe sync (four calls, seconds) before
the backfill.

`.env` is gitignored. The FinEdge key must never reach the browser or a log line — it travels
as a query parameter, so anything logging a request URL logs the credential.

Deployment, backups and the data-repair pass: [docs/SELF-HOSTING.md](docs/SELF-HOSTING.md).

## Documentation

- **[docs/API.md](docs/API.md)** — the HTTP endpoints, who can call what, and the units
- **[docs/SERVICES.md](docs/SERVICES.md)** — the Python functions behind them, written for an
  agent that should call the service rather than talk to the app over HTTP
- **[docs/process/](docs/process/)** — a plain-language record of what was built and what went
  wrong, including [the eleven faults found by checking the app against real
  data](docs/process/2026-08-07-checking-the-numbers.md)
- **[docs/prd/](docs/prd/)** — the original product requirements

## License

MIT. Not investment advice; figures come from FinEdge and are not independently audited.

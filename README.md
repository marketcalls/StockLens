# StockLens

Stock analysis and screening platform for Indian equities (NSE + BSE), built on the FinEdge
financial data API.

Anyone can screen the market and read a company's fundamentals without signing up. Signing
up turns a one-off lookup into an ongoing research workflow: saved screens, watchlists,
alerts, comparisons and exports that persist.

## Status

Exploration phase. The product requirements are complete and grounded in a live audit of the
FinEdge API; no application code has been written yet.

Start with **[docs/prd/README.md](docs/prd/README.md)**.

## Stack

| Layer | Choice |
| --- | --- |
| Backend | FastAPI (Python 3.12+) |
| Frontend | React (Vite, TypeScript) |
| Database | SQLite (WAL mode) |
| UI | shadcn/ui on Tailwind CSS, light/dark theme switcher |

## Data

FinEdge covers 5,630 NSE/BSE symbols with 8 years of annual P&L and balance sheet, 5 years
of cash flow, 33 quarters of results, 13 years of daily prices, 41 quarters of shareholding
pattern, and roughly 150 pre-computed ratios, growth metrics and averages per company.

A single call to `/api/v1/quote` with no symbol returns live price, market cap, 52-week range
and volume for the entire universe. That is what makes the daily screener refresh one API
call rather than 5,630.

Full inventory, measured limits and known gaps:
[docs/prd/02-data-source-inventory.md](docs/prd/02-data-source-inventory.md).

## Roles

| Role | Capability |
| --- | --- |
| Public | Read the screener and company pages |
| User | Plus persistence, alerts, export, depth |
| Admin | Plus data quality and user operations |
| Super Admin | Plus the FinEdge data pipeline and role assignment |

Full matrix: [docs/prd/04-roles-and-access.md](docs/prd/04-roles-and-access.md).

## Setup

```bash
cp .env.example .env
# add your FINEDGE_API_KEY
```

`.env` is gitignored. The FinEdge key must never reach the browser or a log line.

# StockLens - Product Requirements

StockLens is a stock analysis and screening platform for Indian equities (NSE + BSE),
built on the FinEdge financial data API. It is modelled on the Screener.in experience:
a fast company search, a deep per-company fundamentals page, and a query-driven screener
over the full listed universe.

These documents are the exploration-phase PRD. Every data claim in them was verified
against the live FinEdge API on 2026-08-06, not inferred from documentation.

## Documents

| # | Document | What it covers |
| --- | --- | --- |
| 01 | [Product overview](01-product-overview.md) | Vision, personas, scope, non-goals, success measures |
| 02 | [Data source inventory](02-data-source-inventory.md) | Verified FinEdge coverage, field catalog, measured limits, gaps |
| 03 | [Feature catalog](03-feature-catalog.md) | Every feature we can build, mapped to its data source |
| 04 | [Roles and access](04-roles-and-access.md) | RBAC matrix, and what signing up actually earns a user |
| 05 | [Screener engine](05-screener-engine.md) | Query language, column catalog, execution model |
| 06 | [Data model and ingestion](06-data-model-and-ingestion.md) | Schema, download pipeline, delta sync, job control |
| 07 | [Architecture and API](07-architecture-and-api.md) | FastAPI + React + SQLite + shadcn/ui, service layout, backend API surface |
| 08 | [Roadmap](08-roadmap.md) | Phased delivery, from thin slice to full product |
| 09 | [Open questions](09-open-questions.md) | Decisions needed, unknowns to resolve before build |

## The one-paragraph summary

FinEdge exposes 5,630 NSE/BSE symbols with 8 years of annual P&L and balance sheet,
5 years of cash flow, 33 quarters of quarterly results, 13 years of daily prices, 41 quarters
of shareholding pattern, and roughly 150 pre-computed ratios, growth metrics and averages
per company. One unauthenticated-by-symbol call to `/api/v1/quote` returns live price,
market cap, 52-week range and volume for the entire universe in a single 1.4 MB response.
That single fact is what makes a real screener feasible: the daily price refresh for all
5,630 stocks is one API call, and the fundamentals behind it change only when a company
files, which `/api/v1/refreshed-stocks` tells us about incrementally. StockLens ingests
that into SQLite, serves a public screener and company pages from it, and reserves the
ingestion controls for Super Admin.

## Stack

FastAPI (Python 3.12+) - React (Vite, TypeScript) - SQLite (WAL) - shadcn/ui on Tailwind,
with a light/dark theme switcher. Rationale and the sizing argument for SQLite are in
[07](07-architecture-and-api.md).

## Verified baseline (2026-08-06)

| Fact | Measured value |
| --- | --- |
| Symbol universe | 5,630 (2,510 with consolidated statements) |
| Whole-universe quote call | 1.4 MB, 0.39 s, one request |
| Annual P&L / balance sheet depth | 8 years (FY2019 - FY2026) |
| Annual cash flow depth | 5 years (FY2022 - FY2026) |
| Quarterly P&L depth | 33 quarters (Jun 2018 - Jun 2026) |
| Daily price history | 3,350 trading days from 2013 |
| Shareholding pattern depth | 41 quarters from Jun 2016 |
| Indices with constituent lists | 239 |
| Auth | API key as `token` query parameter |

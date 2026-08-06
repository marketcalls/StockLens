# 02 - Data Source Inventory (FinEdge)

Everything in this document was verified by calling the live API with the project key on
**2026-08-06**. Where documentation and observed behaviour disagreed, observed behaviour wins.

- Host: `https://data.finedgeapi.com`
- Auth: API key as the **`token` query parameter**. Scheme name `ApiKeyAuth`. HTTPS only.
- Invalid key returns `401 ER006 - missing or invalid token`.
- Key lives in `StockLens/.env` as `FINEDGE_API_KEY`. It must never reach the browser.

## 1. Access tier confirmed

The project key has **Personal API** access across all tested endpoints, including the
premium behaviour on `/api/v1/quote`. Enterprise `/enterprise/api/*` endpoints are not
required by this design; every enterprise capability we need has a Personal equivalent.

## 2. The single most important finding

`GET /api/v1/quote` **with no `symbol` parameter** returns the entire universe:

```
5,630 symbols | 1,438,162 bytes | 0.39 s | one request
```

Per symbol it returns `current_price`, `open_price`, `high_price`, `low_price`, `volume`,
`change`, `high52`, `low52`, `market_cap` (Rs Cr), `shares`, `tradetime`.

This means the daily price and market-cap refresh for the whole screener is **one API call**,
not 5,630. It removes the main scaling objection to building a real screener.

Note on the multi-symbol form: comma-separated values do **not** work
(`symbol=A,B,C` returns `{"A,B,C":{}}`). Repeated parameters do work
(`symbol=RELIANCE&symbol=ITC&symbol=TCS`). Documented max is 100 per call.

## 3. Universe-wide endpoints (one call each, no per-symbol fan-out)

| Endpoint | Returns | Observed |
| --- | --- | --- |
| `/api/v1/stock-symbols` | symbol, nse_code, bse_code, name, consolidated_ind | 5,630 rows, 649 KB, 0.16 s |
| `/api/v1/quote` | full universe EOD quote | 1.4 MB, 0.39 s |
| `/api/v1/index/master` | 239 indices **with constituent symbol lists** | includes BSE Sensex, Nifty 50, BSE 500 |
| `/api/v1/index/market-price/daily-feed` | 229 indices: close, change, pe, pb, div_yield, market_cap, turnover | live |
| `/api/v1/index/price-returns` | 1M/3M/6M/1Y/3Y/5Y/7Y/10Y returns per index | 239 rows |
| `/api/v1/corp-announcements` | market-wide announcement feed | 2,037 rows, supports `symbol` + `from_date` + `to_date` |
| `/api/v1/credit-ratings` | rating action feed | 22 recent |
| `/api/v1/investor-call-transcripts` | concall transcript PDFs | 76 recent |
| `/api/v1/investor-presentations` | investor deck PDFs | 118 recent |
| `/api/v1/corporate-actions/all` | market-wide dividends/splits/bonus by ex-date | 217 rows |
| `/api/v1/results-calendar` | expected result dates | 2,006 rows |
| `/api/v1/ipo-calendar` | forthcoming and open IPOs incl. SME | live |
| `/api/v1/holidays-calendar` | exchange holidays | 19 rows for 2026 |
| `/api/v1/refreshed-stocks?days=N` | per-symbol last-updated timestamps | see delta sync below |

`/api/v1/index/master` carrying `constituents` is what makes index-membership badges
("Part of BSE Sensex, Nifty 50, BSE 500") and index-scoped screening possible.

## 4. Per-symbol endpoints (fan-out required)

| Endpoint | Required params | Notes |
| --- | --- | --- |
| `/api/v1/company-profile/{symbol}` | - | description, website, market_cap, macro_sector, sector, industry, sub_industry |
| `/api/v1/financials/{symbol}` | `statement_type` s\|c, `statement_code` pl\|bs\|cf, `period` ttm\|annual\|quarterly\|halfyearly | raw statement lines |
| `/api/v1/basic-financials/{symbol}` | `statement_type`, `statement_code` | derived aggregates (ebitda, fcf, book value...) |
| `/api/v1/ratios/{symbol}` | `statement_type`, `ratio_type` pr\|le\|li\|ef | 31 ratios across 4 families |
| `/api/v1/financial-metrics/{symbol}` | `statement_type`, `ratio_type` gr\|av\|cu | 56 growth / average / cumulative metrics |
| `/api/v1/daily-price-ratios/{symbol}` | `statement_type`, `from`, `to` | daily pe, pb, ptb, ps, pfcf |
| `/api/v1/annual-price-ratios/{symbol}` | `statement_type` | annual pe/pb/ptb/ps/pfcf + average_price |
| `/api/v1/daily-quotes/{symbol}` | `from`, `to` (years) | OHLCV, 3,350 rows from 2013 |
| `/api/v1/segment-revenue/{symbol}` | `statement_type`, `statement_code`, `period` | per-segment revenue and PBT |
| `/api/v1/notes/{symbol}` | `statement_type`, `period` | management notes to accounts, HTML-ish text |
| `/api/v1/peers/{symbol}` | - | small peer list, see caveat below |
| `/api/v1/shareholdings/pattern/{symbol}` | `period` quarterly\|annual | 41 quarters, columns + rows layout |
| `/api/v1/shareholdings/summary/{symbol}` | `period` | totalShareholders, locked-in, voting rights |
| `/api/v1/shareholdings/distribution/{symbol}` | `period` | promoter / public / non-public group split |
| `/api/v1/shareholdings/ownership-current/{symbol}` | - | named holders, **pledgedSharesPct**, locked-in |
| `/api/v1/shareholdings/ownership-history/{symbol}` | `period` | 2.6 MB for RELIANCE - the heaviest endpoint |
| `/api/v1/shareholdings/declaration/{symbol}` | `period` | boolean disclosure flags |
| `/api/v1/shareholdings/beneficial-owners/{symbol}` | `period` | SBO disclosures, 476 KB |
| `/api/v1/dividend/{symbol}` | - | dividend history with amounts and dates |
| `/api/v1/corporate-actions/{split\|bonus\|rights}/{symbol}` | - | corporate action history |
| `/api/v1/stock-search` | `group`, `value` | all symbols in a sector/industry classification |

Endpoints returning `400` in testing were **always** missing a required parameter, never an
auth or entitlement failure. `/api/v1/commodity-list` and `/api/v1/name-changes` returned
`503` transiently; retry logic is required, not a permissions change.

## 5. Measured history depth (RELIANCE, consolidated)

| Statement | Annual | Quarterly |
| --- | --- | --- |
| Profit & Loss | **8** periods (FY2019 - FY2026) | **33** quarters (Jun 2018 - Jun 2026) |
| Balance Sheet | **8** periods (FY2019 - FY2026) | **16** quarters |
| Cash Flow | **5** periods (FY2022 - FY2026) | **10** quarters |
| Daily prices | 3,350 rows, 2013-01-01 onwards | - |
| Shareholding pattern | - | 41 quarters from Jun 2016 |

`period=ttm` and `period=halfyearly` are valid for `pl`. `period=ytd` is rejected
(`combination pl, ytd is invalid`) despite being listed as allowed - treat the documented
enum as aspirational and validate per statement code.

## 6. Field catalog

### 6.1 Quote (universe-wide)
`current_price`, `open_price`, `high_price`, `low_price`, `volume`, `change`, `high52`,
`low52`, `market_cap`, `shares`, `tradetime`

### 6.2 Profit & Loss - general schema (44 fields)
`income`, `revenueFromOperations`, `revenueFromSaleOfProduct`, `revenueFromSaleOfServices`,
`otherRevenueFromOperations`, `otherIncome`, `interestEarned`, `dividendIncome`,
`rentalIncome`, `feesAndCommissionIncome`, `netGainOnFairValueChanges`,
`netGainOnAmortisedDerecognition`, `expenses`, `costofGoodsSold`, `costOfMaterialsConsumed`,
`purchasesOfStockInTrade`, `changesInInventories`, `employeeBenefitExpense`,
`feesAndCommission`, `netLossOnFairValueChanges`, `netLossOnAmortisedDerecognition`,
`impairmentOnFinancialInstruments`, `otherExpenses`, `financeCosts`,
`depreciationAndAmortisation`, `exceptionalItemsBeforeTax`, `profitBeforeTax`,
`profitLossFromDiscontinuedOperationsAfterTax`, `profitOrLossOfAssociates`,
`extraordinaryItems`, `taxExpense`, `currentTax`, `deferredTax`, `profitLossForPeriod`,
`otherComprehensiveIncomeNetOfTaxes`, `nonControllingInterests`,
`profitOrLossAttributableToOwners`, `eps`, `dilutedOutstandingShares`, `period_start`,
`period_end`, `result_date`, `year`

### 6.3 Profit & Loss - Bank schema (verified on HDFCBANK)
A genuinely different shape, not a subset: `interestEarned`,
`interestOrDiscountOnAdvancesOrBills`, `revenueOnInvestments`,
`interestOnBalancesWithRBIAndOthers`, `otherInterest`, `interestExpended`, `employeesCost`,
`otherOperatingExpenses`, `provisionsForLoanLoss`, `expenditureExcludingProvisions`,
`grossNonPerformingAssets`, `nonPerformingAssets`, `percentageOfGrossNpa`, `percentageOfNpa`,
`cET1Ratio`, `additionalTier1Ratio`, `profitLossBeforeTax`, `profitLossForThePeriod`,
`profitLossOfAssociates`, `profitLossOfMinorityInterest`, `profitOrLossAttributableToOwners`,
`taxExpense`, `eps`, `dilutedOutstandingShares`

**Design consequence:** the P&L table renderer must be schema-aware. A bank company page
shows NII, GNPA % and CET1, not Operating Profit and OPM %.

### 6.3a Schema families - measured, not assumed (2026-08-06)

`python -m app.ingest.discover` probed 22 companies spanning large caps, public and private
banks, a small finance bank, NBFCs, an AMC, a broker, an exchange, life insurers and a
general insurer. Three assumptions in the original draft were wrong:

**There are four families, not three.**

| Family | Discriminating fields | Confirmed members |
| --- | ---: | --- |
| `general` | 37 | RELIANCE, ITC, TCS, MARUTI, SUNPHARMA, NTPC, TATASTEEL, BSE, BAJFINANCE, LICHSGFIN, HDFCAMC, ANGELONE, CHOLAFIN |
| `bank` | 26 | HDFCBANK, SBIN, BANKBARODA, AUBANK |
| `life_insurance` | 67 | HDFCLIFE, LICI, SBILIFE, ICICIPRULI |
| `general_insurance` | 42 | ICICIGI |

Life and general insurers share only **14** fields. Treating "insurance" as one schema, as
the draft did, would render both wrongly.

**NBFCs, AMCs, brokers and exchanges use the `general` schema.** BAJFINANCE, CHOLAFIN,
LICHSGFIN, HDFCAMC, ANGELONE and BSE all matched it. This resolves
[Q5](09-open-questions.md#q5-how-many-distinct-statement-schemas-are-there-really). Note that
`interestEarned` appears in both the general and bank families, so it must never decide a
classification on its own.

**Membership needs subset containment, not exact equality.** AUBANK returns 25 of the bank
family's 26 fields - it has no subsidiaries, so no minority-interest line. An exact-match
rule strands it in a family of one. The classifier scores each family by the share of its
markers present; all 22 companies classify correctly at confidence 1.00.

Six fields appear in every family and carry no signal: `eps`, `income`, `period_start`,
`period_end`, `result_date`, `year`.

### 6.3b The quote feed is not the company universe

`/api/v1/quote` returns **6,747 keys** against a symbol master of **5,630**. The extra 1,146
are not additional companies:

| Kind | Count | Note |
| --- | ---: | --- |
| BSE scrip codes duplicating a company already in the master | **242** | Same company, keyed by `bse_code` as well as by ticker |
| BSE scrip codes with no symbol-master entry | 376 | BSE-only listings, no fundamentals available |
| Alphabetic non-companies | 528 | ETFs (`ABSLLIQUID`, `ABSLNN50ET`), rights entitlements (`5PAISA-RE`) |

**Design consequence:** the screener universe is the **symbol master**, joined by `symbol`.
Treating quote keys as the universe would double-count 242 companies and screen 528
instruments that have no financial statements. A data-quality check pins this.

29 symbol-master entries had no quote in the 2026-08-06 feed, and 28 index constituents have
no symbol-master entry, so index-scoped screens will silently omit those unless flagged.

### 6.4 Basic financials - derived aggregates
- **pl**: `ebit`, `ebitda`, `grossIncome`, `operatingProfit`, `operatingRevenue`,
  `operatingExpenses`, `costOfGoodsSold`, `dividendPayout`, `retentionRatio`,
  `salesPerShare`, `sharesOutstanding`, `dilutedSharesOutstanding`,
  `adjustedEquityShareCapital`, `adjustedFaceValue`, `tax`
- **bs**: `bookValue`, `bookValuepershare`, `tangibleBookValue`, `tangibleBookValueperShare`,
  `totalAssets`, `totalEquity`, `totalLiabilities`, `totalEquityAndLiabilities`,
  `totalReserves`, `shareCapital`, `totalDebt`, `netDebt`, `longTermBorrowings`,
  `shortTermBorrowings`, `totalCash`, `totalReceivables`, `totalPayables`, `workingCapital`,
  `goodwill`, `intangibleAssets`, `loans`, `netLoans`
- **cf**: `operatingCashFlow`, `investingCashFlow`, `financingCashFlow`, `capex`, `fcf`,
  `fcfPerShare`, `cashFlowMargin`, `debtRepayment`, `newDebtIssued`, `equityProceeds`

### 6.5 Ratios (31 fields, 4 families)
- **Profitability (`pr`)**: `grossMargin`, `operatingMargin`, `ebitMargin`, `ebitdaMargin`,
  `preTaxMargin`, `netMargin`, `effectiveTaxRate`, `returnOnEquity`, `returnOnAsset`,
  `returnOnCapital`, `returnOnTangibleAssets`
- **Leverage (`le`)**: `totalDebtToEquity`, `longTermDebtToEquity`, `totalDebttoAssets`,
  `longTermDebtToTotalAssets`, `financialLeverage`, `totalDebtTofcf`, `longTermDebtTofcf`
- **Liquidity (`li`)**: `currentRatio`, `quickRatio`, `interestCoverage`
- **Efficiency (`ef`)**: `assetTurnover`, `inventoryTurnover`, `receivableTurnover`,
  `payableTurnover`, `workingCapitalTurnover`, `debtorDays`, `inventoryDays`, `daysPayable`,
  `cashConversionCycle`, `workingCapitalDays`

Every ratio is returned as a time series with a `header` ("TTM", "Mar 2026", ...) and `year`.
The efficiency family maps exactly onto the Ratios table in the reference screenshots.

### 6.6 Financial metrics (56 fields, 3 families)
- **Growth (`gr`)**: 3-year and 5-year growth for revenue, net income, EPS, EBITDA, EBIT,
  gross income, operating income, COGS, assets, book value, tangible book value,
  diluted shares; plus `capexGrowth3years`, `cfoGrowth3years`, `freeCashFlowGrowth3Years`
- **Average (`av`)**: `roe3yearsAvg`, `roe5yearsAvg`, `roa3/5yearsAvg`, `roce3/5yearsAvg`,
  `rota3/5yearsAvg`, margin averages (gross, operating, EBIT, EBITDA, pre-tax, net) at 3 and
  5 years, `dividendPayoutPct3/5YrsAvg`, `capexAsPctOfNetIncome3yearsAvg`,
  `fcfAsPctOfRevenue3yearsAvg`
- **Cumulative (`cu`)**: `operatingCashFlow3yearsTotal`, `investingCashFlow3yearsTotal`,
  `financingCashFlow3yearsTotal`, `freeCashFlow3yearsTotal`

### 6.7 Valuation
`pe`, `pb`, `ptb`, `ps`, `pfcf` - available both as a **daily** series and an **annual**
series with `average_price`.

## 7. Delta sync - the ingestion backbone

`GET /api/v1/refreshed-stocks?days=N` returns, per symbol, the last-updated Unix timestamp
for each of `balance-sheet`, `cash-flow`, `profit-loss`, `quarterly`:

```json
{ "symbol": "AJAXENGG",
  "balance-sheet": { "last_updated_unix": 1785968591 },
  "cash-flow":     { "last_updated_unix": 1785968591 },
  "profit-loss":   { "last_updated_unix": 1785968607 },
  "quarterly":     { "last_updated_unix": 1785968607 } }
```

`days=1` returned 62 KB covering only symbols that actually changed. This turns the nightly
fundamentals job from 5,630 x 12 calls into a handful of calls plus a targeted refresh of
the changed symbols. Full-universe backfill is a Super Admin action run rarely; the daily
job rides on this endpoint.

## 8. Gaps against the Screener.in reference screenshots

| Reference feature | Status | Resolution |
| --- | --- | --- |
| 12-year annual P&L / balance sheet table | **Gap** - FinEdge has 8 years | Show 8 years, label the range. Accumulate our own history from launch so the table deepens over time. |
| 10-year compounded sales / profit growth | **Gap** - only 3Y and 5Y provided | Show 3Y, 5Y, and TTM. Compute longer horizons ourselves once we hold enough history. |
| 10-year Stock Price CAGR | **Available** | Compute from `daily-quotes` (13 years of history). |
| "Raw PDF" link per quarter | **Partial** | `corp-announcements` filtered by symbol and date gives result-filing PDFs, but not guaranteed one-per-quarter. Best-effort match. |
| Annual report PDFs | **Partial** | Not a dedicated endpoint. Derive from `corp-announcements` by category. |
| Peer set | **Caveat** | `/api/v1/peers/ITC` returned only 4 entries, some obscure. `/api/v1/stock-search?group=sector` returned 6 for Refineries & Marketing against 9 in the reference. **Recommendation: build peers from our own sector + market-cap-band logic**, using the FinEdge peers list only as a seed. |
| Sector breadcrumb | **Naming caveat** | FinEdge labels for RELIANCE are `macro_sector=Energy`, `industry=Petroleum Products`, `sector=Refineries & Marketing`, `sub_industry=Refineries & Marketing`. The `sector`/`industry` naming is effectively inverted versus the reference hierarchy. Normalise at ingestion, do not pass through raw. |
| Index membership badges | **Available** | `index/master` carries constituent lists for 239 indices. |
| Concall AI summaries | **Out of scope for v1** | We have the transcript PDFs; summarisation is a later feature. |
| Mutual fund holdings | **Not available** | FinEdge marks mutual funds "coming soon". |

## 9. Operational unknowns

- **Rate limits are not documented and no rate-limit headers were returned.** No
  `X-RateLimit-*` on any response. Concurrency policy must be established empirically before
  the first full backfill. Design assumes conservative serial-with-small-pool access.
- **No pagination on feed endpoints.** `corp-announcements` returned 2,037 rows with no
  cursor. Date-window the requests rather than relying on a page parameter.
- **Transient 503s observed** on two endpoints. Retry with backoff is mandatory in the
  ingestion client.
- `Connection: close` on responses - the HTTP client should not assume keep-alive reuse.

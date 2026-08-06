# 04 - Roles and Access

## The four roles

| Role | Who | Core capability |
| --- | --- | --- |
| **Public** | Anyone, not signed in | Read the screener and company pages |
| **User** | Registered free account | Everything public, plus persistence, depth, export and alerts |
| **Admin** | Operations staff | Everything user, plus data quality and user operations |
| **Super Admin** | Platform owner | Everything, plus the FinEdge data pipeline and role assignment |

Roles are strictly hierarchical - each level is a superset of the one below. This keeps the
permission check simple: `required_level <= user_level`.

---

## The design problem, stated plainly

The requirement is that public can use the screener and registered users can also use the
screener. So the screener itself cannot be the incentive to sign up. If we gate it, we lose
the acquisition funnel that made the reference product successful. If we gate nothing,
nobody signs up.

**The resolution: public gets full access to answers, registered users get a workflow.**

A public visitor can run any query, see any company, read any statement. What they cannot do
is keep anything. Every session starts from zero. The moment a visitor's usage stops being a
one-off lookup and starts being a repeated research process, the absence of an account
becomes the friction - and that is exactly the moment to convert.

Three axes of differentiation, in order of importance:

1. **Persistence** - saved screens, watchlists, notes, column preferences, comparison sets
2. **Automation** - alerts, scheduled screen runs, digests, diff notifications
3. **Extraction and depth** - CSV export, full ratio expansion, named shareholder history,
   custom columns, backtesting

Note that none of these cost us more FinEdge calls. All of them are served from our own
database. The gate is a product decision, not a cost one, which means we can be generous.

---

## What a public visitor gets

Deliberately generous, because this is the funnel and the SEO surface.

- Full company analysis page: quotes, all 8 years of P&L and balance sheet, 5 years of cash
  flow, 33 quarters of results, peer comparison, shareholding aggregates, documents,
  corporate actions, segment revenue, price chart, Pros and Cons
- The full screener query language over all ~180 columns
- All preset public screens
- Index, sector, results, IPO, corporate action and holiday calendars
- Market movers and sector heatmaps
- Sharing a screener result by URL

Public limits, and the honest reason for each:

| Limit | Value | Reason |
| --- | --- | --- |
| Screener rows returned | First 25, then a "sign up to see all 340 results" row | Persistence funnel. The count is always shown truthfully. |
| Screener runs | 20 per session | Abuse and scraping control, not artificial scarcity |
| Saved anything | None | This is the point of the account |
| CSV / Excel export | Not available | Bulk extraction is the clearest signup trigger |
| Comparison | 3 companies | Full feature is 10 |
| Ratio table | Efficiency family only | Full 31-ratio expansion for users |
| Shareholding | Aggregate percentages | Named holders and SBO for users |
| Alerts | None | Requires an identity to deliver to |
| API access | None | Users get a personal read-only key |

Rate limiting for public is by IP with a generous burst. Screener queries are cached by
normalised query hash, so repeated popular screens cost nothing.

---

## What signing up gets you

This is the answer to "what extra does a signup user get". Grouped by the value they deliver.

### 1. Nothing you build disappears
- **Unlimited saved screens** with names, descriptions and version history
- **Multiple named watchlists**, importable from CSV
- **Private notes and tags** on any company
- **Saved column sets** - your preferred peer-comparison columns per sector, remembered
- **Recently viewed** synced across devices
- **Comparison sets** you can name and return to

### 2. The market tells you things without you looking
Ten alert types (E1-E10 in [03](03-feature-catalog.md#e-alerts-and-notifications-registered-only)),
including results declared, upcoming result dates, announcements by category, credit rating
actions, concall transcripts published, ex-dates approaching, promoter stake or pledge
changes, 52-week breakouts, valuation crossing its own 5-year median, and saved-screen
membership changes.

Plus a **weekly digest**: what happened across your watchlist, which of your screens changed
membership, and what is scheduled next week.

### 3. Get the data out
- **CSV and Excel export** of any screener result, watchlist, or financial statement table -
  up to 5,000 rows per export, 50 exports per day
- **Personal read-only API key** for the StockLens API, rate limited, so a user can pull
  their own screens into a spreadsheet or notebook
- **Copy as table** for any statement, formatted for pasting into a sheet

### 4. See more
- Full 31-ratio expansion on every company
- Named shareholder history and Significant Beneficial Owner disclosures
- Notes to accounts
- Valuation band charts - daily P/E, P/B, P/S, P/FCF against their own 5-year median
- Compare 10 companies at once instead of 3
- Uncapped screener result sets

### 5. Build your own analysis
- **Custom columns**: define a derived column with an expression over any ingested field,
  reusable across all your screens
- **Custom Pros/Cons thresholds**: your own definition of "high debt" or "good ROE"
- **Screen backtesting**: what this screen returned 1, 3 and 5 years ago, and how those
  names performed - possible because we hold 13 years of daily prices and dated fundamentals
- **Share a screen publicly** by link, with attribution

### 6. No friction
- No public rate limits or session run caps
- No 25-row wall

### Deliberately not gated
Company page depth, statement history, the query language, preset screens and market
calendars all stay fully public. Gating them would cost us search traffic worth more than
the conversions it would produce.

---

## Full permission matrix

Legend: **Y** = full, **L** = limited, **-** = none

### Read and analysis

| Capability | Public | User | Admin | Super |
| --- | :---: | :---: | :---: | :---: |
| Company search and profile | Y | Y | Y | Y |
| P&L / BS / CF statements, full history | Y | Y | Y | Y |
| Quarterly results | Y | Y | Y | Y |
| Peer comparison | L (default columns) | Y | Y | Y |
| Ratios table | L (efficiency only) | Y (all 31) | Y | Y |
| Growth and averages | Y | Y | Y | Y |
| Shareholding aggregates | Y | Y | Y | Y |
| Named holders, SBO, ownership history | - | Y | Y | Y |
| Notes to accounts | - | Y | Y | Y |
| Documents and PDFs | Y | Y | Y | Y |
| Price chart | Y | Y | Y | Y |
| Valuation band charts | - | Y | Y | Y |
| Segment revenue | Y | Y | Y | Y |
| Corporate actions and dividends | Y | Y | Y | Y |
| Index, IPO, results, holiday calendars | Y | Y | Y | Y |
| Market movers and sector heatmap | Y | Y | Y | Y |

### Screener

| Capability | Public | User | Admin | Super |
| --- | :---: | :---: | :---: | :---: |
| Run any query | L (20/session) | Y | Y | Y |
| Results returned | L (25 rows) | Y | Y | Y |
| Preset screens | Y | Y | Y | Y |
| Query builder UI | Y | Y | Y | Y |
| Index / sector universe filter | Y | Y | Y | Y |
| Custom derived columns | - | Y | Y | Y |
| Save screens | - | Y | Y | Y |
| Screen version history | - | Y | Y | Y |
| Share screen by link | - | Y | Y | Y |
| Scheduled screen runs and diffs | - | Y | Y | Y |
| Screen backtesting | - | Y | Y | Y |
| Feature a screen as a public preset | - | - | Y | Y |

### Personal workspace

| Capability | Public | User | Admin | Super |
| --- | :---: | :---: | :---: | :---: |
| Watchlists | - | Y | Y | Y |
| Notes and tags on companies | - | Y | Y | Y |
| Compare companies | L (3) | Y (10) | Y | Y |
| Saved column preferences | - | Y | Y | Y |
| Alerts (all 10 types) | - | Y | Y | Y |
| Email digest | - | Y | Y | Y |
| CSV / Excel export | - | Y (5k rows, 50/day) | Y | Y (unlimited) |
| Personal read-only API key | - | Y | Y | Y |

### Operations

| Capability | Public | User | Admin | Super |
| --- | :---: | :---: | :---: | :---: |
| Data quality dashboard | - | - | Y | Y |
| Stale data report | - | - | Y | Y |
| Targeted re-fetch, single symbol | - | - | Y | Y |
| Ingestion job history and logs | - | - | Y | Y |
| Company classification override | - | - | Y | Y |
| User management (view, suspend, reset) | - | - | Y | Y |
| Content moderation on shared screens | - | - | Y | Y |
| Promote a user to Admin | - | - | - | Y |
| Modify or remove an Admin | - | - | - | Y |
| Assign Super Admin | - | - | - | Y |

### Data platform - Super Admin only

| Capability | Public | User | Admin | Super |
| --- | :---: | :---: | :---: | :---: |
| **Full universe fundamentals download (5,630 symbols)** | - | - | - | Y |
| Selective backfill by index / sector / cap band / list | - | - | - | Y |
| Ingestion scheduler configuration | - | - | - | Y |
| Delta sync control and dry-run preview | - | - | - | Y |
| FinEdge credential management and rotation | - | - | - | Y |
| API budget, quota and hard-stop controls | - | - | - | Y |
| Raw FinEdge response inspector | - | - | - | Y |
| Purge / rebuild / roll back an ingestion run | - | - | - | Y |
| Cost and usage analytics | - | - | - | Y |

---

## Security requirements

1. **The FinEdge key never leaves the server.** No user role, including Super Admin, can
   read the key value through the UI. Super Admin can replace it and test connectivity;
   the field is write-only and displays as a masked fingerprint.

2. **Enforcement is server-side.** Public row caps, export limits and column gating are
   applied in the query layer, not in the client. A modified client request must not be able
   to retrieve row 26.

3. **`.env` must be gitignored** before the repository has a remote. It currently holds a
   live key in plaintext.

4. **Personal API keys are scoped read-only** and rate limited independently from the web
   session. Revocable by the user and by Admin.

5. **Role changes are audit-logged** with actor, target, old role, new role and timestamp.
   Super Admin actions on the data platform are logged the same way.

6. **The first Super Admin is created by a CLI bootstrap command**, not by self-service
   signup. There is no path from a web form to Super Admin.

7. **Session model**: HTTP-only secure cookies with rotation on privilege change.
   Admin and Super Admin sessions have a shorter idle timeout than user sessions and
   require re-authentication before any destructive data-platform action.

---

## Room left for a paid tier

v1 monetises nothing, but the boundaries are drawn so a paid tier can be inserted later
without redesign. The natural split, should it be needed:

- **Free**: everything described above for User
- **Paid**: higher export limits, more alerts per account, intraday-frequency screen runs,
  full ownership-history downloads, API key with a higher rate limit, longer backtest windows

Adding a tier means adding a level between User and Admin in the hierarchy and moving a few
limits - not restructuring permissions.

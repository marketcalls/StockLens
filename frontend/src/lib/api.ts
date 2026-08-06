/** Typed client for the StockLens backend. */

export type HealthResponse = {
  status: string
  environment: string
  finedge: { reachable: boolean; key_configured: boolean; base_url: string }
}

export type IngestionRun = {
  id: string
  job_kind: string
  status: string
  calls_made: number
  bytes_fetched: number
  started_at: string | null
  finished_at: string | null
}

export type FreshnessResponse = {
  raw: {
    raw_responses: number
    distinct_symbols: number
    last_fetched_at: string | null
    uncompressed_bytes: number
  }
  recent_runs: IngestionRun[]
}

export type SearchResult = {
  symbol: string
  name: string
  sector: string | null
  current_price: number | null
  market_cap: number | null
}

export type Quote = {
  symbol: string
  current_price: number | null
  open_price: number | null
  high_price: number | null
  low_price: number | null
  volume: number | null
  change_pct: number | null
  high52: number | null
  low52: number | null
  market_cap: number | null
  shares: number | null
  trade_time: string | null
}

export type CompanyDetail = {
  symbol: string
  name: string
  nse_code: string | null
  bse_code: string | null
  website: string | null
  description: string | null
  schema_kind: string | null
  classification: {
    macro_sector: string | null
    industry: string | null
    sector: string | null
    sub_industry: string | null
  }
  quote: Quote | null
  indices: { symbol: string; name: string }[]
  key_ratios: Record<string, number | null>
}

export type StatementRow = {
  label: string
  unit: string
  emphasis: boolean
  values: (number | null)[]
  children: StatementRow[]
}

export type StatementResponse = {
  symbol: string
  statement_code: string
  period_kind: string
  statement_type: string
  schema_kind?: string | null
  available: boolean
  reason?: string
  headers: string[]
  result_dates?: (string | null)[]
  rows: StatementRow[]
  unit_note?: string
}

export type SeriesResponse = {
  symbol: string
  available: boolean
  headers: string[]
  rows: { label: string; unit: string; values: (number | null)[] }[]
}

export type Peer = {
  symbol: string
  name: string
  current_price: number | null
  pe: number | null
  market_cap: number | null
  dividend_yield: number | null
  net_profit: number | null
  sales: number | null
  returnoncapital: number | null
  returnonequity: number | null
}

export type PeersResponse = {
  symbol: string
  group: string | null
  classification: Record<string, string | null>
  peers: Peer[]
  median: Record<string, number | null>
  count: number
}

export type PricePoint = {
  symbol: string
  quote_date: string
  open: number | null
  high: number | null
  low: number | null
  close: number | null
  volume: number | null
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = "ApiError"
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: "application/json" },
    credentials: "same-origin",
    ...init,
  })
  if (!response.ok) {
    throw new ApiError(`${path} returned ${response.status}`, response.status)
  }
  return (await response.json()) as T
}

const qs = (params: Record<string, string | number | undefined>) =>
  Object.entries(params)
    .filter(([, v]) => v !== undefined)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
    .join("&")

export const api = {
  health: () => request<HealthResponse>("/api/meta/health"),
  freshness: () => request<FreshnessResponse>("/api/meta/freshness"),
  search: (q: string, limit = 10) =>
    request<{ query: string; results: SearchResult[] }>(`/api/search?${qs({ q, limit })}`),
  companies: (limit = 12) =>
    request<{ total: number; companies: { symbol: string; name: string; market_cap: number }[] }>(
      `/api/companies?${qs({ limit })}`,
    ),
  company: (symbol: string) => request<CompanyDetail>(`/api/companies/${symbol}`),
  statements: (symbol: string, code: string, period: string, statementType: string) =>
    request<StatementResponse>(
      `/api/companies/${symbol}/statements?${qs({ code, period, statement_type: statementType })}`,
    ),
  ratios: (symbol: string, family: string) =>
    request<SeriesResponse>(`/api/companies/${symbol}/ratios?${qs({ family })}`),
  shareholding: (symbol: string) =>
    request<SeriesResponse>(`/api/companies/${symbol}/shareholding`),
  peers: (symbol: string) => request<PeersResponse>(`/api/companies/${symbol}/peers`),
  prices: (symbol: string, limit = 2000) =>
    request<{ symbol: string; count: number; prices: PricePoint[] }>(
      `/api/companies/${symbol}/prices?${qs({ limit })}`,
    ),
}

export type ScreenerColumn = {
  key: string
  label: string
  unit: string
  aliases: string[]
  description: string
  screenable: boolean
}

export type ColumnsResponse = {
  total: number
  screenable: number
  groups: Record<string, ScreenerColumn[]>
}

export type Preset = {
  slug: string
  name: string
  description: string
  query: string
  columns: string[]
}

export type ScreenResult = {
  query: string
  columns: { key: string; label: string; unit: string }[]
  rows: Record<string, string | number | null>[]
  total: number
  returned: number
  capped: boolean
  cap: number | null
  elapsed_ms: number
  page: number
  page_size: number
  preset?: { slug: string; name: string; description: string }
}

export type QueryErrorDetail = { message: string; position: number | null }

export class ScreenerError extends Error {
  constructor(
    message: string,
    readonly position: number | null,
  ) {
    super(message)
    this.name = "ScreenerError"
  }
}

async function postScreen(path: string, body: unknown): Promise<ScreenResult> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  })
  if (response.status === 400) {
    const payload = (await response.json()) as { detail: QueryErrorDetail }
    throw new ScreenerError(payload.detail.message, payload.detail.position)
  }
  if (!response.ok) throw new ApiError(`${path} returned ${response.status}`, response.status)
  return (await response.json()) as ScreenResult
}

export const screener = {
  columns: () => request<ColumnsResponse>("/api/screener/columns"),
  presets: () => request<{ presets: Preset[] }>("/api/screener/presets"),
  run: (query: string, page = 1, columns?: string[]) =>
    postScreen("/api/screener/run", { query, page, columns, page_size: 50 }),
  runPreset: (slug: string, page = 1) =>
    postScreen(`/api/screener/presets/${slug}/run?page=${page}`, {}),
}

export type AuthUser = {
  id: number
  email: string
  display_name: string | null
  role: "public" | "user" | "admin" | "super_admin"
  role_level: number
  is_active: boolean
  email_verified: boolean
  created_at: string
  last_login_at: string | null
}

export type Limits = {
  screener_row_cap: number | null
  screener_rows_unlimited: boolean
  export_row_limit: number
  can_save_screens: boolean
  can_use_watchlists: boolean
  can_export: boolean
  can_admin: boolean
  can_manage_platform: boolean
  /** Every administrative surface is Super Admin only. */
  can_see_admin_area: boolean
}

export type Session = { user: AuthUser | null; role: string; limits: Limits }

export type SavedScreen = {
  id: number
  name: string
  description: string | null
  query: string
  columns: string[] | null
  is_public: boolean
  share_token: string | null
  created_at: string
  updated_at: string
}

export type Watchlist = {
  id: number
  name: string
  created_at: string
  items: { symbol: string; note: string | null; added_at: string }[]
}

async function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  })
  if (!response.ok) {
    let message = `${path} returned ${response.status}`
    try {
      const payload = await response.json()
      if (typeof payload.detail === "string") message = payload.detail
      else if (Array.isArray(payload.detail) && payload.detail[0]?.msg) {
        message = payload.detail[0].msg
      }
    } catch {
      /* keep the default message */
    }
    throw new ApiError(message, response.status)
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

export const auth = {
  me: () => request<Session>("/api/auth/me"),
  signup: (email: string, password: string, displayName?: string) =>
    send<{ user: AuthUser; limits: Limits }>("/api/auth/signup", "POST", {
      email,
      password,
      display_name: displayName || null,
    }),
  login: (email: string, password: string) =>
    send<{ user: AuthUser; limits: Limits }>("/api/auth/login", "POST", { email, password }),
  logout: () => send<{ status: string }>("/api/auth/logout", "POST"),
  changePassword: (currentPassword: string, newPassword: string) =>
    send<{ status: string }>("/api/auth/password", "POST", {
      current_password: currentPassword,
      new_password: newPassword,
    }),
}

export const workspace = {
  screens: () => request<{ screens: SavedScreen[] }>("/api/screens"),
  saveScreen: (name: string, query: string, description?: string) =>
    send<SavedScreen>("/api/screens", "POST", { name, query, description: description || null }),
  deleteScreen: (id: number) => send<void>(`/api/screens/${id}`, "DELETE"),
  runScreen: (id: number) => send<ScreenResult>(`/api/screens/${id}/run`, "POST"),
  watchlists: () => request<{ watchlists: Watchlist[] }>("/api/watchlists"),
  createWatchlist: (name: string) =>
    send<{ id: number; name: string }>("/api/watchlists", "POST", { name }),
  deleteWatchlist: (id: number) => send<void>(`/api/watchlists/${id}`, "DELETE"),
  addSymbol: (id: number, symbol: string) =>
    send<unknown>(`/api/watchlists/${id}/items`, "POST", { symbol }),
  removeSymbol: (id: number, symbol: string) =>
    send<void>(`/api/watchlists/${id}/items/${symbol}`, "DELETE"),
  exportUrl: (query: string) => `/api/export/screen?query=${encodeURIComponent(query)}`,
}

// ---------------------------------------------------------------- indices

/** Horizons FinEdge publishes, in the order a reader scans them. */
export const RETURN_HORIZONS = ["1M", "3M", "6M", "1Y", "3Y", "5Y", "7Y", "10Y"] as const
export type ReturnHorizon = (typeof RETURN_HORIZONS)[number]

export type IndexSummary = {
  index_symbol: string
  index_name: string
  exchange: string
  index_type: string | null
  index_sub_type: string | null
  market_cap: number | null
  constituents: number
  close_price: number | null
  change_pct: number | null
  pe: number | null
  pb: number | null
  div_yield: number | null
  returns: Partial<Record<ReturnHorizon, number>>
}

export type IndexQuote = {
  quote_date: string
  close_price: number | null
  open_price: number | null
  high_price: number | null
  low_price: number | null
  change_pct: number | null
  points_change: number | null
  pe: number | null
  pb: number | null
  div_yield: number | null
  market_cap: number | null
  volume: number | null
}

export type IndexConstituent = {
  symbol: string
  name: string | null
  /** False for REITs, InvITs and SME listings, which are not in the equity universe. */
  in_universe: boolean
  current_price: number | null
  market_cap: number | null
  pe: number | null
  pb: number | null
  dividend_yield: number | null
  returnonequity: number | null
  returnoncapital: number | null
  net_profit: number | null
  sales: number | null
  change_pct: number | null
  sector: string | null
}

export type IndexDetail = {
  index_symbol: string
  index_name: string
  exchange: string
  index_type: string | null
  index_sub_type: string | null
  market_cap: number | null
  quote: IndexQuote | null
  returns: Partial<Record<ReturnHorizon, number>>
  horizons: ReturnHorizon[]
  constituents: IndexConstituent[]
  /** Every listed company has a quote; only backfilled ones have statements. */
  count: number
  with_fundamentals: number
  outside_universe: number
  median: {
    pe: number | null
    pb: number | null
    dividend_yield: number | null
    returnonequity: number | null
  }
}

export type IndexMover = {
  index_symbol: string
  index_name: string
  close_price: number | null
  change_pct: number | null
}

export const indices = {
  list: (limit = 300) => request<{ total: number; indices: IndexSummary[] }>(`/api/indices?${qs({ limit })}`),
  detail: (symbol: string) => request<IndexDetail>(`/api/indices/${symbol}`),
  movers: (limit = 8) =>
    request<{ gainers: IndexMover[]; losers: IndexMover[] }>(`/api/indices/movers?${qs({ limit })}`),
}

// ------------------------------------------------------------- super admin

export type IngestionRunDetail = {
  id: string
  job_kind: string
  scope: string | null
  status: string
  calls_made: number
  call_budget: number | null
  bytes_fetched: number
  rows_written: number
  started_at: string
  finished_at: string | null
  error: string | null
  progress: Record<string, number>
  /** Companies fetched so far, and how many the run set out to fetch. */
  symbols_done: number
  symbols_total: number | null
  is_active: boolean
}

export type IngestionStatus = {
  active_run_id: string | null
  is_running: boolean
  runs: IngestionRunDetail[]
}

export type BackfillPlan = {
  symbols: number
  calls_per_symbol: number
  estimated_calls: number
  estimated_hours: number
  message?: string
}

export type StartedRun = {
  run_id: string
  started?: boolean
  symbols?: number
  estimated_calls?: number
  first?: string[]
  calls_made?: number
  written?: Record<string, number>
  quotes?: number
}

export const superadmin = {
  status: () => request<IngestionStatus>("/api/superadmin/status"),
  run: (runId: string) =>
    request<IngestionRunDetail & { failures: { symbol: string; endpoint: string; last_error: string }[] }>(
      `/api/superadmin/runs/${runId}`,
    ),
  plan: (limit?: number) => send<BackfillPlan>("/api/superadmin/plan", "POST", { limit: limit ?? null }),
  universe: () => send<StartedRun>("/api/superadmin/universe", "POST"),
  prices: () => send<StartedRun>("/api/superadmin/prices", "POST"),
  backfill: (body: { limit?: number | null; symbols?: string[] | null; call_budget?: number | null }) =>
    send<StartedRun>("/api/superadmin/backfill", "POST", {
      limit: body.limit ?? null,
      symbols: body.symbols ?? null,
      call_budget: body.call_budget ?? null,
    }),
  materialise: () => send<Record<string, unknown>>("/api/superadmin/materialise", "POST"),
  repair: () => send<Record<string, number>>("/api/superadmin/repair", "POST"),
  release: (runId: string) =>
    send<{ run_id: string; cleared: boolean }>(`/api/superadmin/runs/${runId}/release`, "POST"),
  quality: () => request<Record<string, unknown>>("/api/superadmin/quality"),
}

// ------------------------------------------------------------------ users

export type ManagedUser = {
  id: number
  email: string
  display_name: string | null
  role: string
  is_active: boolean
  created_at: string | null
  last_login_at: string | null
  saved_screens: number
  watchlists: number
}

export type AuditEntry = {
  id: number
  actor_id: number | null
  action: string
  target: string | null
  detail: string | null
  created_at: string
}

export type UserDetail = {
  user: ManagedUser
  saved_screens: { id: number; name: string; query: string }[]
  watchlists: { id: number; name: string }[]
  audit: AuditEntry[]
}

export type UserListing = {
  total: number
  users: ManagedUser[]
  /** Why the last super admin cannot be demoted, rather than only refusing. */
  active_super_admins: number
}

export const people = {
  list: (params: { q?: string; role?: string; include_inactive?: boolean } = {}) =>
    request<UserListing>(
      `/api/users?${qs({
        q: params.q || undefined,
        role: params.role || undefined,
        include_inactive: params.include_inactive === false ? "false" : undefined,
      })}`,
    ),
  detail: (id: number) => request<UserDetail>(`/api/users/${id}`),
  roles: () => request<{ roles: { value: string; rank: number; label: string }[] }>("/api/users/roles"),
  changeRole: (id: number, role: string) =>
    send<UserDetail>(`/api/users/${id}/role`, "PATCH", { role }),
  setActive: (id: number, active: boolean) =>
    send<UserDetail>(`/api/users/${id}/active`, "PATCH", { active }),
  invite: (email: string, role: string, displayName?: string) =>
    send<{ user: ManagedUser; one_time_password: string }>("/api/users", "POST", {
      email,
      role,
      display_name: displayName || null,
    }),
}

// ------------------------------------------------------------ diagnostics

export type LogEntry = {
  id: number
  created_at: string
  level: string
  logger: string
  message: string
  traceback: string | null
  path: string | null
  method: string | null
  status: number | null
  actor_id: number | null
}

export type DiagnosticsHealth = {
  checked_at: string
  environment: string
  errors_last_24h: number
  warnings_last_24h: number
  last_error: LogEntry | null
  last_run: { id: string; job_kind: string; status: string; started_at: string } | null
  process: { python: string; platform: string }
  storage: Record<string, { path: string; bytes: number }>
}

export const diagnostics = {
  health: () => request<DiagnosticsHealth>("/api/diagnostics/health"),
  logs: (params: { level?: string; logger?: string; limit?: number } = {}) =>
    request<{ total: number; by_level: Record<string, number>; entries: LogEntry[] }>(
      `/api/diagnostics/logs?${qs({
        level: params.level || undefined,
        logger: params.logger || undefined,
        limit: params.limit,
      })}`,
    ),
  entry: (id: number) => request<LogEntry>(`/api/diagnostics/logs/${id}`),
}

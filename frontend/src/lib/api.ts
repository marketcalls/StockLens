/** Typed client for the StockLens backend. */

export type HealthResponse = {
  status: string
  environment: string
  finedge: {
    reachable: boolean
    key_configured: boolean
    base_url: string
  }
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

export const api = {
  health: () => request<HealthResponse>("/api/meta/health"),
  freshness: () => request<FreshnessResponse>("/api/meta/freshness"),
}

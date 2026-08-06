import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { superadmin, type IngestionRunDetail, ApiError } from "@/lib/api"
import { useAuth } from "@/providers/auth-provider"
import { cn, formatBytes, formatIst } from "@/lib/utils"

/** Poll while something is running; stay quiet when nothing is. */
const ACTIVE_POLL_MS = 4000

function Panel({
  title,
  eyebrow,
  children,
  className,
}: {
  title: string
  eyebrow?: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <section className={cn("panel min-w-0 p-4 sm:p-5", className)}>
      {eyebrow ? <p className="eyebrow mb-1">{eyebrow}</p> : null}
      <h2 className="mb-4 font-display text-lg font-semibold tracking-tight sm:text-xl">{title}</h2>
      {children}
    </section>
  )
}

function StatusPill({ status }: { status: string }) {
  const tone =
    status === "running"
      ? "border-primary/40 text-primary"
      : status === "completed"
        ? "border-gain/40 text-gain"
        : "border-loss/40 text-loss"
  return (
    <span
      className={cn(
        "rounded border px-1.5 py-0.5 font-mono text-micro uppercase tracking-wider",
        tone,
      )}
    >
      {status}
    </span>
  )
}

/**
 * How far along a run is.
 *
 * Measured in companies, not tasks. Task rows are written as the run reaches
 * each company, so "tasks done over tasks recorded" sits at 100% for the whole
 * run and reads as finished when it has barely started.
 */
export function Progress({ run }: { run: IngestionRunDetail }) {
  const failed = run.progress?.failed ?? 0
  const total = run.symbols_total
  const done = run.symbols_done ?? 0

  if (!total) {
    // Jobs with no per-company scope - universe, prices, rebuild - have nothing
    // to divide by, so report the work done rather than invent a denominator.
    return (
      <span className="tabular text-micro text-muted-foreground">
        {run.calls_made.toLocaleString("en-IN")} calls
        {failed ? ` · ${failed} failed` : ""}
      </span>
    )
  }

  const pct = Math.min(100, Math.round((done / total) * 100))
  return (
    <span className="inline-flex items-center gap-2">
      <span className="h-1.5 w-24 overflow-hidden rounded-full bg-raised" aria-hidden>
        <span className="block h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
      </span>
      <span className="tabular text-micro text-muted-foreground">
        {done.toLocaleString("en-IN")} / {total.toLocaleString("en-IN")} companies
        {failed ? ` · ${failed} failed` : ""}
      </span>
    </span>
  )
}

function Action({
  label,
  description,
  cost,
  onRun,
  disabled,
  pending,
  tone = "normal",
}: {
  label: string
  description: string
  cost: string
  onRun: () => void
  disabled: boolean
  pending: boolean
  tone?: "normal" | "heavy"
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-grid py-3 last:border-0">
      <div className="min-w-0 flex-1">
        <p className="font-medium">{label}</p>
        <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>
        <p className="mt-1 font-mono text-micro uppercase tracking-wider text-muted-foreground">
          {cost}
        </p>
      </div>
      <button
        type="button"
        onClick={onRun}
        disabled={disabled || pending}
        className={cn(
          "shrink-0 rounded-md border px-3 py-1.5 font-mono text-micro uppercase tracking-wider transition-colors",
          "disabled:cursor-not-allowed disabled:opacity-40",
          tone === "heavy"
            ? "border-primary/50 text-primary hover:bg-primary hover:text-primary-foreground"
            : "bg-raised hover:text-primary",
        )}
      >
        {pending ? "Starting..." : "Run"}
      </button>
    </div>
  )
}

export function AdminPage() {
  const { limits } = useAuth()
  const client = useQueryClient()
  const [message, setMessage] = useState<{ text: string; bad: boolean } | null>(null)
  const [backfillLimit, setBackfillLimit] = useState("500")

  const allowed = limits.can_see_admin_area

  const status = useQuery({
    queryKey: ["superadmin-status"],
    queryFn: superadmin.status,
    enabled: allowed,
    // Poll only while a job is live, so an idle console is not chattering.
    refetchInterval: (query) => (query.state.data?.is_running ? ACTIVE_POLL_MS : false),
  })

  const plan = useQuery({
    queryKey: ["superadmin-plan"],
    queryFn: () => superadmin.plan(),
    enabled: allowed,
    staleTime: 5 * 60_000,
  })

  const running = status.data?.is_running ?? false

  const refresh = () => client.invalidateQueries({ queryKey: ["superadmin-status"] })
  const report = (text: string) => setMessage({ text, bad: false })
  /** A 409 carries which job holds the lock, so show the server's own words. */
  const complain = (fallback: string) => (error: unknown) => {
    setMessage({ text: error instanceof ApiError ? error.message : fallback, bad: true })
    refresh()
  }
  const n = (value: number | undefined) => (value ?? 0).toLocaleString("en-IN")

  const universe = useMutation({
    mutationFn: superadmin.universe,
    onSuccess: (result) => {
      const w = result.written
      report(
        w
          ? `Universe synced: ${n(w.companies)} companies, ${w.indices} indices, ${n(w.index_constituents)} memberships.`
          : "Universe synced.",
      )
      refresh()
    },
    onError: complain("The universe sync failed."),
  })

  const prices = useMutation({
    mutationFn: superadmin.prices,
    onSuccess: (result) => {
      report(`Refreshed ${n(result.quotes)} quotes.`)
      refresh()
    },
    onError: complain("The price refresh failed."),
  })

  const materialise = useMutation({
    mutationFn: superadmin.materialise,
    onSuccess: () => {
      report("Screener table rebuilt from the normalised tables.")
      refresh()
    },
    onError: complain("The rebuild failed."),
  })

  const repairData = useMutation({
    mutationFn: superadmin.repair,
    onSuccess: (result) => {
      report(
        result.total
          ? `Repaired ${n(result.total)} rows: ${n(result.price_rows_removed)} prices removed, ${n(result.quote_rows_corrected)} quotes corrected.`
          : "Nothing to repair - every row already matches the current rules.",
      )
      refresh()
    },
    onError: complain("The repair pass failed."),
  })

  const backfill = useMutation({
    mutationFn: () => {
      const parsed = Number.parseInt(backfillLimit, 10)
      return superadmin.backfill({ limit: Number.isFinite(parsed) && parsed > 0 ? parsed : null })
    },
    onSuccess: (result) => {
      report(
        `Backfill started for ${n(result.symbols)} companies, about ${n(result.estimated_calls)} calls. Progress appears below.`,
      )
      refresh()
    },
    onError: complain("Could not start the backfill."),
  })

  const release = useMutation({
    mutationFn: (runId: string) => superadmin.release(runId),
    onSuccess: (result) => {
      report(`Run ${result.run_id.slice(0, 8)} cleared. A new job can start.`)
      refresh()
    },
    onError: complain("Could not clear that run."),
  })

  const activeRun = status.data?.runs.find((r) => r.is_active)

  return (
    <div className="min-w-0 space-y-6">
      <p className="max-w-2xl text-sm text-muted-foreground">
        Download data from FinEdge and watch it land. One job runs at a time, because the
        database takes a single writer and two downloads would double the request rate.
      </p>

      {message ? (
        <div
          role="status"
          className={cn(
            "panel px-4 py-3 text-sm",
            message.bad ? "border-loss/40 text-loss" : "border-gain/40 text-gain",
          )}
        >
          {message.text}
        </div>
      ) : null}

      {activeRun ? (
        <section className="panel min-w-0 border-primary/40 p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="eyebrow mb-1">Running now</p>
              <p className="font-medium">
                {activeRun.job_kind} · started {formatIst(activeRun.started_at)}
              </p>
              <div className="mt-2">
                <Progress run={activeRun} />
              </div>
            </div>
            <button
              type="button"
              onClick={() => release.mutate(activeRun.id)}
              disabled={release.isPending}
              className="shrink-0 rounded-md border px-3 py-1.5 font-mono text-micro uppercase tracking-wider text-muted-foreground transition-colors hover:border-loss/50 hover:text-loss disabled:opacity-40"
            >
              Clear if dead
            </button>
          </div>
          <p className="mt-3 border-t pt-3 text-micro text-muted-foreground">
            Clearing does not stop a live job - nothing here can reach into the process doing the
            work. Use it only when you know the job has died and its row is blocking new ones.
          </p>
        </section>
      ) : null}

      <Panel title="Downloads" eyebrow={running ? "A job is running" : "Ready"}>
        <Action
          label="Sync the universe"
          description="Symbol master, every index with its members, index quotes and returns."
          cost="4 calls · seconds"
          onRun={() => universe.mutate()}
          disabled={running}
          pending={universe.isPending}
        />
        <Action
          label="Refresh prices"
          description="Current price, day change, market cap and 52-week range for every company."
          cost="1 call · seconds"
          onRun={() => prices.mutate()}
          disabled={running}
          pending={prices.isPending}
        />
        <Action
          label="Re-apply the data rules"
          description="Fixes rows stored before a rule changed - zero prices, absent index valuations. A long download keeps writing with the code it started with."
          cost="0 calls · seconds"
          onRun={() => repairData.mutate()}
          disabled={running}
          pending={repairData.isPending}
        />
        <Action
          label="Rebuild the screener table"
          description="Re-derives the wide table the screener queries. No FinEdge calls."
          cost="0 calls · under a minute"
          onRun={() => materialise.mutate()}
          disabled={running}
          pending={materialise.isPending}
        />

        <div className="border-t border-grid pt-4">
          <p className="font-medium">Backfill financial statements</p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Statements, ratios, shareholding, prices and corporate actions.{" "}
            {plan.data ? (
              <>
                Each company takes {plan.data.calls_per_symbol} calls; all{" "}
                {plan.data.symbols.toLocaleString("en-IN")} would be{" "}
                {plan.data.estimated_calls.toLocaleString("en-IN")} calls and about{" "}
                {Math.round(plan.data.estimated_hours)} hours.
              </>
            ) : null}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Companies are taken in priority order - index members first, then by market cap - so a
            partial run still covers the names people search for.
          </p>
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <div>
              <label
                htmlFor="backfill-limit"
                className="eyebrow mb-1 block"
              >
                How many companies
              </label>
              <input
                id="backfill-limit"
                value={backfillLimit}
                onChange={(event) => setBackfillLimit(event.target.value)}
                inputMode="numeric"
                className="h-9 w-32 rounded-md border bg-raised px-3 font-mono text-data outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <button
              type="button"
              onClick={() => backfill.mutate()}
              disabled={running || backfill.isPending}
              className="h-9 rounded-md border border-primary/50 px-3 font-mono text-micro uppercase tracking-wider text-primary transition-colors hover:bg-primary hover:text-primary-foreground disabled:cursor-not-allowed disabled:opacity-40"
            >
              {backfill.isPending ? "Starting..." : "Start backfill"}
            </button>
            <p className="font-mono text-micro uppercase tracking-wider text-muted-foreground">
              {(() => {
                const n = Number.parseInt(backfillLimit, 10)
                if (!Number.isFinite(n) || n <= 0) return "Enter a number"
                const calls = n * (plan.data?.calls_per_symbol ?? 59)
                const minutes = Math.max(1, Math.round(calls / 5 / 60))
                const time = minutes >= 90 ? `${(minutes / 60).toFixed(1)} hours` : `${minutes} min`
                return `${calls.toLocaleString("en-IN")} calls · about ${time}`
              })()}
            </p>
          </div>

          {/* "Everything" should be a button, not a number you have to know. */}
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="eyebrow">Or take</span>
            {[250, 500, 1000, 2500].map((count) => (
              <button
                key={count}
                type="button"
                onClick={() => setBackfillLimit(String(count))}
                className="rounded-md border bg-raised px-2.5 py-1 font-mono text-micro uppercase tracking-wider transition-colors hover:text-primary"
              >
                {count.toLocaleString("en-IN")}
              </button>
            ))}
            {plan.data ? (
              <button
                type="button"
                onClick={() => setBackfillLimit(String(plan.data.symbols))}
                className="rounded-md border border-primary/50 px-2.5 py-1 font-mono text-micro uppercase tracking-wider text-primary transition-colors hover:bg-primary hover:text-primary-foreground"
              >
                Every company ({plan.data.symbols.toLocaleString("en-IN")})
              </button>
            ) : null}
          </div>
        </div>
      </Panel>

      <Panel title="Recent runs" eyebrow="History">
        {status.isLoading ? <p className="text-sm text-muted-foreground">Loading...</p> : null}
        {status.data && status.data.runs.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nothing has run yet. Start with the universe sync.
          </p>
        ) : null}
        <div className="scroll-slim -mx-1 overflow-x-auto px-1">
          <table className="w-full min-w-[32rem] border-collapse text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="py-2 pr-3 font-medium text-muted-foreground">Job</th>
                <th className="py-2 px-2 font-medium text-muted-foreground">Status</th>
                <th className="py-2 px-2 font-medium text-muted-foreground">Progress</th>
                <th className="hidden py-2 px-2 text-right font-medium text-muted-foreground sm:table-cell">
                  Calls
                </th>
                <th className="hidden py-2 px-2 text-right font-medium text-muted-foreground md:table-cell">
                  Rows
                </th>
                <th className="hidden py-2 px-2 text-right font-medium text-muted-foreground lg:table-cell">
                  Fetched
                </th>
                <th className="hidden py-2 pl-2 text-right font-medium text-muted-foreground xs:table-cell">
                  Started
                </th>
              </tr>
            </thead>
            <tbody>
              {status.data?.runs.map((run) => (
                <tr key={run.id} className="border-b border-grid last:border-0">
                  <td className="py-2 pr-3">
                    <span className="font-medium">{run.job_kind}</span>
                    <span className="ml-2 font-mono text-micro text-muted-foreground">
                      {run.id.slice(0, 8)}
                    </span>
                    {run.error ? (
                      <p className="mt-0.5 max-w-md truncate text-micro text-loss" title={run.error}>
                        {run.error}
                      </p>
                    ) : null}
                  </td>
                  <td className="py-2 px-2">
                    <StatusPill status={run.status} />
                  </td>
                  <td className="py-2 px-2">
                    <Progress run={run} />
                  </td>
                  <td className="hidden py-2 px-2 text-right font-mono text-data tabular sm:table-cell">
                    {run.calls_made.toLocaleString("en-IN")}
                  </td>
                  <td className="hidden py-2 px-2 text-right font-mono text-data tabular md:table-cell">
                    {run.rows_written.toLocaleString("en-IN")}
                  </td>
                  <td className="hidden py-2 px-2 text-right font-mono text-data tabular lg:table-cell">
                    {formatBytes(run.bytes_fetched)}
                  </td>
                  <td className="hidden py-2 pl-2 text-right font-mono text-micro text-muted-foreground xs:table-cell">
                    {formatIst(run.started_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  )
}

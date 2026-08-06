import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"
import { cn, formatBytes, formatIst } from "@/lib/utils"

function Card({
  title,
  children,
  className,
}: {
  title: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <section
      className={cn("panel p-5", className)}
    >
      <h2 className="eyebrow">
        {title}
      </h2>
      <div className="mt-4">{children}</div>
    </section>
  )
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-border/60 py-2 last:border-0">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="tabular text-sm font-medium">{value}</dd>
    </div>
  )
}

/** A dot plus a word. Never colour alone - it has to read without it. */
function StatusDot({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span
        className={cn("h-2 w-2 rounded-full", ok ? "bg-gain" : "bg-loss")}
        aria-hidden
      />
      <span className={cn("font-medium", ok ? "text-gain" : "text-loss")}>{children}</span>
    </span>
  )
}

export function StatusPanel() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health, retry: 1 })
  const freshness = useQuery({ queryKey: ["freshness"], queryFn: api.freshness, retry: 1 })

  return (
    <div className="grid gap-5 md:grid-cols-2">
      <Card title="Backend">
        {health.isPending ? (
          <p className="text-sm text-muted-foreground">Checking...</p>
        ) : health.isError ? (
          <p className="text-sm text-loss">
            Cannot reach the StockLens API. Is the backend running on port 8000?
          </p>
        ) : (
          <dl>
            <Stat
              label="Service"
              value={<StatusDot ok={health.data.status === "ok"}>{health.data.status}</StatusDot>}
            />
            <Stat label="Environment" value={health.data.environment} />
            <Stat
              label="FinEdge reachable"
              value={
                <StatusDot ok={health.data.finedge.reachable}>
                  {health.data.finedge.reachable ? "yes" : "no"}
                </StatusDot>
              }
            />
            <Stat
              label="API key configured"
              value={
                <StatusDot ok={health.data.finedge.key_configured}>
                  {health.data.finedge.key_configured ? "yes" : "no"}
                </StatusDot>
              }
            />
          </dl>
        )}
      </Card>

      <Card title="Stored data">
        {freshness.isPending ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : freshness.isError ? (
          <p className="text-sm text-loss">Could not read data freshness.</p>
        ) : (
          <dl>
            <Stat
              label="Raw responses"
              value={freshness.data.raw.raw_responses.toLocaleString("en-IN")}
            />
            <Stat
              label="Companies"
              value={freshness.data.raw.distinct_symbols.toLocaleString("en-IN")}
            />
            <Stat
              label="Uncompressed size"
              value={formatBytes(freshness.data.raw.uncompressed_bytes)}
            />
            <Stat label="Last fetched" value={formatIst(freshness.data.raw.last_fetched_at)} />
          </dl>
        )}
      </Card>

      <Card title="Recent ingestion runs" className="md:col-span-2">
        {freshness.data?.recent_runs?.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-2 pr-4 font-medium">Job</th>
                  <th className="py-2 pr-4 font-medium">Status</th>
                  <th className="py-2 pr-4 text-right font-medium">Calls</th>
                  <th className="py-2 pr-4 text-right font-medium">Downloaded</th>
                  <th className="py-2 font-medium">Started</th>
                </tr>
              </thead>
              <tbody>
                {freshness.data.recent_runs.map((run) => (
                  <tr key={run.id} className="border-b border-border/60 last:border-0">
                    <td className="py-2 pr-4">{run.job_kind}</td>
                    <td className="py-2 pr-4">
                      <StatusDot ok={run.status === "completed"}>{run.status}</StatusDot>
                    </td>
                    <td className="tabular py-2 pr-4 text-right">{run.calls_made}</td>
                    <td className="tabular py-2 pr-4 text-right">
                      {formatBytes(run.bytes_fetched)}
                    </td>
                    <td className="py-2 text-muted-foreground">{formatIst(run.started_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            No ingestion runs yet. Run{" "}
            <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
              python -m app.ingest.worker fetch RELIANCE
            </code>{" "}
            from the backend directory.
          </p>
        )}
      </Card>
    </div>
  )
}

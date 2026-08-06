import { useState } from "react"
import { useQuery } from "@tanstack/react-query"

import { diagnostics, type LogEntry } from "@/lib/api"
import { useAuth } from "@/providers/auth-provider"
import { cn, formatBytes, formatIst } from "@/lib/utils"

const LEVEL_TONE: Record<string, string> = {
  CRITICAL: "border-loss/60 text-loss",
  ERROR: "border-loss/40 text-loss",
  WARNING: "border-primary/40 text-primary",
}

function LevelTag({ level }: { level: string }) {
  return (
    <span
      className={cn(
        "rounded border px-1.5 py-0.5 font-mono text-micro uppercase tracking-wider",
        LEVEL_TONE[level] ?? "border-border text-muted-foreground",
      )}
    >
      {level}
    </span>
  )
}

function Readout({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="min-w-0">
      <p className="eyebrow mb-0.5">{label}</p>
      <p className={cn("font-mono text-base tabular", tone)}>{value}</p>
    </div>
  )
}

/** One record. The traceback is collapsed, because most of the time the message is enough. */
function Entry({ entry }: { entry: LogEntry }) {
  const [open, setOpen] = useState(false)
  return (
    <li className="border-b border-grid py-2.5 last:border-0">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="font-mono text-micro text-muted-foreground">
          {formatIst(entry.created_at)}
        </span>
        <LevelTag level={entry.level} />
        <span className="font-mono text-micro text-muted-foreground">{entry.logger}</span>
        {entry.path ? (
          <span className="font-mono text-micro text-muted-foreground">
            {entry.method} {entry.path}
            {entry.status ? ` ${entry.status}` : ""}
          </span>
        ) : (
          // Saying which failures came from a job rather than a request is the
          // difference between "a user hit this" and "it happened on its own".
          <span className="font-mono text-micro text-muted-foreground/70">background</span>
        )}
      </div>
      <p className="mt-1 break-words text-sm">{entry.message}</p>
      {entry.traceback ? (
        <>
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
            className="mt-1 font-mono text-micro uppercase tracking-wider text-muted-foreground transition-colors hover:text-primary"
          >
            {open ? "Hide traceback" : "Show traceback"}
          </button>
          {open ? (
            <pre className="scroll-slim mt-2 max-h-80 overflow-auto rounded border bg-raised p-3 font-mono text-micro leading-relaxed">
              {entry.traceback}
            </pre>
          ) : null}
        </>
      ) : null}
    </li>
  )
}

export function DiagnosticsPage() {
  const { limits } = useAuth()
  const [level, setLevel] = useState("")
  const allowed = limits.can_see_admin_area

  const health = useQuery({
    queryKey: ["diagnostics-health"],
    queryFn: diagnostics.health,
    enabled: allowed,
    refetchInterval: 30_000,
  })
  const logs = useQuery({
    queryKey: ["diagnostics-logs", level],
    queryFn: () => diagnostics.logs({ level, limit: 200 }),
    enabled: allowed,
  })

  const summary = health.data
  const errors = summary?.errors_last_24h ?? 0
  const storedBytes = summary
    ? Object.values(summary.storage).reduce((sum, item) => sum + (item.bytes ?? 0), 0)
    : 0

  return (
    <div className="min-w-0 space-y-6">
      <p className="max-w-2xl text-sm text-muted-foreground">
        Warnings and errors are kept here as well as on standard output, so a failure on a
        machine nobody is watching still leaves a record. The most recent 2,000 are held.
      </p>

      {summary ? (
        <section
          className={cn(
            "panel grid min-w-0 grid-cols-2 gap-4 p-4 sm:grid-cols-3 sm:p-5 lg:grid-cols-5",
            errors > 0 && "border-loss/40",
          )}
        >
          <Readout
            label="Errors, 24h"
            value={String(errors)}
            tone={errors > 0 ? "text-loss" : "text-gain"}
          />
          <Readout label="Warnings, 24h" value={String(summary.warnings_last_24h)} />
          <Readout label="Environment" value={summary.environment} />
          <Readout label="Python" value={summary.process.python} />
          <Readout label="Database" value={formatBytes(storedBytes)} />
        </section>
      ) : null}

      {summary?.last_error ? (
        <section className="panel min-w-0 border-loss/40 p-4 sm:p-5">
          <p className="eyebrow mb-2">Most recent failure</p>
          <ul>
            <Entry entry={summary.last_error} />
          </ul>
        </section>
      ) : (
        <section className="panel min-w-0 p-4 sm:p-5">
          <p className="text-sm text-muted-foreground">
            Nothing has failed. There is no error on record.
          </p>
        </section>
      )}

      <section className="panel min-w-0 p-4 sm:p-5">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="eyebrow mb-1">{logs.data ? `${logs.data.total} held` : "Log"}</p>
            <h2 className="font-display text-lg font-semibold tracking-tight sm:text-xl">
              Recent entries
            </h2>
          </div>
          <div
            className="inline-flex rounded-md border bg-raised p-0.5"
            role="group"
            aria-label="Level"
          >
            {["", "WARNING", "ERROR", "CRITICAL"].map((option) => (
              <button
                key={option || "all"}
                type="button"
                onClick={() => setLevel(option)}
                aria-pressed={level === option}
                className={cn(
                  "rounded px-2.5 py-1 font-mono text-micro uppercase tracking-wider transition-colors",
                  level === option
                    ? "bg-card font-medium text-foreground shadow-tile"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {option || "All"}
                {logs.data && option && logs.data.by_level[option]
                  ? ` ${logs.data.by_level[option]}`
                  : ""}
              </button>
            ))}
          </div>
        </div>

        {logs.isLoading ? <p className="text-sm text-muted-foreground">Loading...</p> : null}
        {logs.data && logs.data.entries.length === 0 ? (
          <p className="py-4 text-sm text-muted-foreground">
            {level
              ? `Nothing at ${level.toLowerCase()} level.`
              : "Nothing recorded. That is the good outcome."}
          </p>
        ) : null}

        <ul className="min-w-0">
          {logs.data?.entries.map((entry) => (
            <Entry key={entry.id} entry={entry} />
          ))}
        </ul>
      </section>
    </div>
  )
}

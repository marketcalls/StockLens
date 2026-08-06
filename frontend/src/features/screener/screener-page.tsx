import { useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { useMutation, useQuery } from "@tanstack/react-query"

import { QueryEditor } from "@/features/screener/query-editor"
import { ResultsGrid } from "@/features/screener/results-grid"
import { ApiError, ScreenerError, screener, workspace, type ScreenResult } from "@/lib/api"
import { useAuth } from "@/providers/auth-provider"
import { cn } from "@/lib/utils"

export function ScreenerPage() {
  const [params, setParams] = useSearchParams()
  const [query, setQuery] = useState(params.get("q") ?? "")
  const [error, setError] = useState<{ message: string; position: number | null } | null>(null)
  const [result, setResult] = useState<ScreenResult | null>(null)
  const [activePreset, setActivePreset] = useState<string | null>(null)
  const [screenName, setScreenName] = useState("")
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  const { signedIn, limits } = useAuth()

  const columns = useQuery({
    queryKey: ["screener-columns"],
    queryFn: screener.columns,
    staleTime: 10 * 60_000,
  })
  const presets = useQuery({
    queryKey: ["screener-presets"],
    queryFn: screener.presets,
    staleTime: 10 * 60_000,
  })

  const allColumns = Object.values(columns.data?.groups ?? {}).flat()

  const run = useMutation({
    mutationFn: (text: string) => screener.run(text),
    onSuccess: (data) => {
      setResult(data)
      setError(null)
      setParams({ q: data.query }, { replace: true })
    },
    onError: (err) => {
      setResult(null)
      setError(
        err instanceof ScreenerError
          ? { message: err.message, position: err.position }
          : { message: "Could not reach the screener.", position: null },
      )
    },
  })

  const runPreset = useMutation({
    mutationFn: (slug: string) => screener.runPreset(slug),
    onSuccess: (data) => {
      setResult(data)
      setError(null)
      setQuery(data.query)
      setParams({ q: data.query }, { replace: true })
    },
  })

  const save = useMutation({
    mutationFn: () => workspace.saveScreen(screenName.trim(), result?.query ?? query),
    onSuccess: (screen) => {
      setSaveMessage(`Saved "${screen.name}"`)
      setScreenName("")
    },
    onError: (err) =>
      setSaveMessage(err instanceof ApiError ? err.message : "Could not save that screen."),
  })

  const busy = run.isPending || runPreset.isPending

  return (
    <div className="container space-y-6 py-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Screener</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Search {columns.data?.screenable ?? 118} fundamentals across every listed company.
        </p>
      </div>

      <QueryEditor
        value={query}
        onChange={(v) => {
          setQuery(v)
          setActivePreset(null)
        }}
        onRun={() => run.mutate(query)}
        columns={allColumns}
        error={error}
        running={busy}
      />

      {presets.data?.presets.length ? (
        <section>
          <h2 className="mb-2 text-sm font-medium text-muted-foreground">Ready-made screens</h2>
          <div className="flex flex-wrap gap-2">
            {presets.data.presets.map((preset) => (
              <button
                key={preset.slug}
                type="button"
                title={preset.description}
                onClick={() => {
                  setActivePreset(preset.slug)
                  runPreset.mutate(preset.slug)
                }}
                className={cn(
                  "rounded-md border px-3 py-1.5 text-sm transition",
                  activePreset === preset.slug
                    ? "border-primary bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:border-primary hover:text-foreground",
                )}
              >
                {preset.name}
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {result ? (
        <>
          {result.preset ? (
            <p className="text-sm text-muted-foreground">{result.preset.description}</p>
          ) : null}

          {signedIn ? (
            <div className="flex flex-wrap items-center gap-2 rounded-md border bg-card p-3">
              <input
                value={screenName}
                onChange={(e) => {
                  setScreenName(e.target.value)
                  setSaveMessage(null)
                }}
                placeholder="Name this screen"
                aria-label="Name this screen"
                className="h-9 min-w-48 flex-1 rounded-md border bg-background px-3 text-sm outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring"
              />
              <button
                type="button"
                onClick={() => save.mutate()}
                disabled={!screenName.trim() || save.isPending}
                className="rounded-md border px-3 py-1.5 text-sm font-medium transition hover:border-primary disabled:opacity-50"
              >
                {save.isPending ? "Saving..." : "Save screen"}
              </button>
              {limits.can_export ? (
                <a
                  href={workspace.exportUrl(result.query)}
                  className="rounded-md border px-3 py-1.5 text-sm font-medium transition hover:border-primary"
                >
                  Export CSV
                </a>
              ) : null}
              {saveMessage ? (
                <span role="status" className="text-sm text-muted-foreground">
                  {saveMessage}
                </span>
              ) : null}
            </div>
          ) : (
            <p className="rounded-md border border-dashed p-3 text-sm text-muted-foreground">
              <Link to="/signup?next=/screens" className="text-primary hover:underline">
                Create a free account
              </Link>{" "}
              to save this screen, export it as CSV and see every match.
            </p>
          )}

          <ResultsGrid result={result} />
        </>
      ) : !error && !busy ? (
        <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          Write a query above, or pick one of the ready-made screens.
        </div>
      ) : null}
    </div>
  )
}

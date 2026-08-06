import { useState } from "react"
import { useSearchParams } from "react-router-dom"
import { useMutation, useQuery } from "@tanstack/react-query"

import { QueryEditor } from "@/features/screener/query-editor"
import { ResultsGrid } from "@/features/screener/results-grid"
import { ScreenerError, screener, type ScreenResult } from "@/lib/api"
import { cn } from "@/lib/utils"

export function ScreenerPage() {
  const [params, setParams] = useSearchParams()
  const [query, setQuery] = useState(params.get("q") ?? "")
  const [error, setError] = useState<{ message: string; position: number | null } | null>(null)
  const [result, setResult] = useState<ScreenResult | null>(null)
  const [activePreset, setActivePreset] = useState<string | null>(null)

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

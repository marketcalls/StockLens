import { useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"

import { ReturnsSpark } from "@/components/returns-ladder"
import { indices, type IndexMover, type IndexSummary } from "@/lib/api"
import { cn, formatCrore, formatPercent } from "@/lib/utils"

/** Order the categories so the ones people actually look for come first. */
const CATEGORY_ORDER = [
  "Broad Market Indices",
  "Sectoral Indices",
  "Thematic Indices",
  "Strategy Indices",
]

function categoryRank(name: string): number {
  const at = CATEGORY_ORDER.indexOf(name)
  return at === -1 ? CATEGORY_ORDER.length : at
}

function Change({ value }: { value: number | null }) {
  if (value === null || value === undefined) return <span className="text-muted-foreground">-</span>
  return (
    <span className={cn("font-mono text-data tabular", value < 0 ? "text-loss" : "text-gain")}>
      {value > 0 ? "+" : ""}
      {value.toFixed(2)}%
    </span>
  )
}

function MoverList({ title, movers }: { title: string; movers: IndexMover[] }) {
  return (
    <div className="min-w-0">
      <p className="eyebrow mb-2">{title}</p>
      <ul className="space-y-1.5">
        {movers.map((m) => (
          <li key={m.index_symbol} className="flex items-baseline justify-between gap-3">
            <Link
              to={`/index/${m.index_symbol}`}
              className="min-w-0 truncate text-sm hover:text-primary hover:underline"
            >
              {m.index_name}
            </Link>
            <Change value={m.change_pct} />
          </li>
        ))}
      </ul>
    </div>
  )
}

export function IndicesPage() {
  const [term, setTerm] = useState("")
  const [exchange, setExchange] = useState<"all" | "NSE" | "BSE">("all")

  const list = useQuery({ queryKey: ["indices"], queryFn: () => indices.list(300) })
  const movers = useQuery({ queryKey: ["index-movers"], queryFn: () => indices.movers(6) })

  const grouped = useMemo(() => {
    const all = list.data?.indices ?? []
    const needle = term.trim().toLowerCase()
    const filtered = all.filter((i) => {
      if (exchange !== "all" && i.exchange !== exchange) return false
      if (!needle) return true
      return (
        i.index_name.toLowerCase().includes(needle) ||
        i.index_symbol.toLowerCase().includes(needle)
      )
    })
    const buckets = new Map<string, IndexSummary[]>()
    for (const i of filtered) {
      const key = i.index_sub_type || "Other"
      const bucket = buckets.get(key)
      if (bucket) bucket.push(i)
      else buckets.set(key, [i])
    }
    return [...buckets.entries()].sort(
      (a, b) => categoryRank(a[0]) - categoryRank(b[0]) || a[0].localeCompare(b[0]),
    )
  }, [list.data, term, exchange])

  const shown = grouped.reduce((n, [, rows]) => n + rows.length, 0)

  return (
    <div className="min-w-0 space-y-6">
      <header className="min-w-0">
        <p className="eyebrow mb-2">Market</p>
        <h1 className="font-display text-title font-semibold tracking-tight">Indices</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          {list.data ? `${list.data.total} indices` : "Indices"} across the NSE and BSE, with
          their constituents, valuation and returns.
        </p>
      </header>

      {movers.data && (movers.data.gainers.length > 0 || movers.data.losers.length > 0) ? (
        <section className="panel grid min-w-0 gap-6 p-4 sm:p-5 md:grid-cols-2">
          <MoverList title="Today's gainers" movers={movers.data.gainers} />
          <MoverList title="Today's losers" movers={movers.data.losers} />
        </section>
      ) : null}

      <section className="panel min-w-0 p-4 sm:p-5">
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <label className="sr-only" htmlFor="index-filter">
            Filter indices
          </label>
          <input
            id="index-filter"
            value={term}
            onChange={(event) => setTerm(event.target.value)}
            placeholder="Filter by name"
            className="h-9 min-w-0 flex-1 rounded-md border bg-raised px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <div className="inline-flex rounded-md border bg-raised p-0.5" role="group" aria-label="Exchange">
            {(["all", "NSE", "BSE"] as const).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setExchange(option)}
                aria-pressed={exchange === option}
                className={cn(
                  "rounded px-2.5 py-1 font-mono text-micro uppercase tracking-wider transition-colors",
                  exchange === option
                    ? "bg-card font-medium text-foreground shadow-tile"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {option === "all" ? "Both" : option}
              </button>
            ))}
          </div>
        </div>

        {list.isLoading ? <p className="py-8 text-sm text-muted-foreground">Loading indices...</p> : null}
        {list.isError ? (
          <p className="py-8 text-sm text-loss">Could not load indices.</p>
        ) : null}
        {list.data && shown === 0 ? (
          <p className="py-8 text-sm text-muted-foreground">
            No index matches “{term}”.
          </p>
        ) : null}

        <div className="space-y-7">
          {grouped.map(([category, rows]) => (
            <div key={category} className="min-w-0">
              <h2 className="eyebrow mb-2">
                {category} <span className="text-muted-foreground/70">({rows.length})</span>
              </h2>
              <div className="scroll-slim -mx-1 overflow-x-auto px-1">
                <table className="w-full min-w-[34rem] border-collapse text-sm">
                  <thead>
                    <tr className="border-b text-left">
                      <th className="py-2 pr-3 font-medium text-muted-foreground">Index</th>
                      <th className="py-2 px-2 text-right font-medium text-muted-foreground">Close</th>
                      <th className="py-2 px-2 text-right font-medium text-muted-foreground">Day</th>
                      <th className="hidden py-2 px-2 text-right font-medium text-muted-foreground sm:table-cell">
                        P/E
                      </th>
                      <th className="hidden py-2 px-2 text-right font-medium text-muted-foreground md:table-cell">
                        P/B
                      </th>
                      <th className="hidden py-2 px-2 text-right font-medium text-muted-foreground lg:table-cell">
                        Div yield
                      </th>
                      <th className="hidden py-2 px-2 text-right font-medium text-muted-foreground xs:table-cell">
                        Stocks
                      </th>
                      <th className="hidden py-2 pl-2 text-right font-medium text-muted-foreground lg:table-cell">
                        1M-10Y
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.index_symbol} className="border-b border-grid last:border-0">
                        <td className="py-2 pr-3">
                          <Link
                            to={`/index/${row.index_symbol}`}
                            className="font-medium hover:text-primary hover:underline"
                          >
                            {row.index_name}
                          </Link>
                          <span className="ml-2 font-mono text-micro uppercase text-muted-foreground">
                            {row.exchange}
                          </span>
                        </td>
                        <td className="py-2 px-2 text-right font-mono text-data tabular">
                          {formatCrore(row.close_price)}
                        </td>
                        <td className="py-2 px-2 text-right">
                          <Change value={row.change_pct} />
                        </td>
                        <td className="hidden py-2 px-2 text-right font-mono text-data tabular sm:table-cell">
                          {formatCrore(row.pe)}
                        </td>
                        <td className="hidden py-2 px-2 text-right font-mono text-data tabular md:table-cell">
                          {formatCrore(row.pb)}
                        </td>
                        <td className="hidden py-2 px-2 text-right font-mono text-data tabular lg:table-cell">
                          {formatPercent(row.div_yield)}
                        </td>
                        <td className="hidden py-2 px-2 text-right font-mono text-data tabular xs:table-cell">
                          {row.constituents}
                        </td>
                        <td className="hidden py-2 pl-2 text-right lg:table-cell">
                          <ReturnsSpark returns={row.returns} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

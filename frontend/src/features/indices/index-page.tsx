import { useMemo, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"

import { ReturnsLadder } from "@/components/returns-ladder"
import { indices, type IndexConstituent } from "@/lib/api"
import { cn, formatCrore, formatPercent } from "@/lib/utils"

type SortKey = keyof Pick<
  IndexConstituent,
  "market_cap" | "current_price" | "change_pct" | "pe" | "pb" | "dividend_yield" | "returnonequity" | "sales" | "net_profit"
>

const COLUMNS: { key: SortKey; label: string; format: (v: number | null) => string; at: string }[] = [
  { key: "current_price", label: "Price", format: (v) => formatCrore(v), at: "" },
  { key: "change_pct", label: "Day", format: (v) => formatPercent(v), at: "hidden xs:table-cell" },
  { key: "market_cap", label: "Mcap Cr", format: (v) => formatCrore(v, 0), at: "" },
  { key: "pe", label: "P/E", format: (v) => formatCrore(v), at: "hidden sm:table-cell" },
  { key: "pb", label: "P/B", format: (v) => formatCrore(v), at: "hidden lg:table-cell" },
  { key: "dividend_yield", label: "Div yld", format: (v) => formatPercent(v), at: "hidden xl:table-cell" },
  { key: "returnonequity", label: "ROE", format: (v) => formatPercent(v), at: "hidden md:table-cell" },
  { key: "sales", label: "Sales Cr", format: (v) => formatCrore(v, 0), at: "hidden xl:table-cell" },
  { key: "net_profit", label: "Profit Cr", format: (v) => formatCrore(v, 0), at: "hidden lg:table-cell" },
]

function Readout({ label, value, tone }: { label: string; value: string; tone?: "gain" | "loss" }) {
  return (
    <div className="min-w-0">
      <p className="eyebrow mb-0.5">{label}</p>
      <p
        className={cn(
          "font-mono text-base tabular",
          tone === "gain" && "text-gain",
          tone === "loss" && "text-loss",
        )}
      >
        {value}
      </p>
    </div>
  )
}

export function IndexPage() {
  const { indexSymbol = "" } = useParams()
  const [sort, setSort] = useState<SortKey>("market_cap")
  const [ascending, setAscending] = useState(false)

  const query = useQuery({
    queryKey: ["index", indexSymbol],
    queryFn: () => indices.detail(indexSymbol),
    retry: false,
  })

  const sorted = useMemo(() => {
    const rows = query.data?.constituents ?? []
    return [...rows].sort((a, b) => {
      const left = a[sort]
      const right = b[sort]
      // Companies missing the figure sort last whichever way the column runs,
      // so a sort never buries the loaded rows under a wall of dashes.
      if (left === null || left === undefined) return 1
      if (right === null || right === undefined) return -1
      return ascending ? left - right : right - left
    })
  }, [query.data, sort, ascending])

  if (query.isLoading) {
    return <p className="py-10 text-sm text-muted-foreground">Loading index...</p>
  }
  if (query.isError || !query.data) {
    return (
      <div className="py-10">
        <h1 className="font-display text-title font-semibold">Index not found</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          No index with the symbol {indexSymbol}.{" "}
          <Link to="/indices" className="text-primary hover:underline">
            Browse all indices
          </Link>
          .
        </p>
      </div>
    )
  }

  const index = query.data
  const quote = index.quote
  const up = (quote?.change_pct ?? 0) >= 0

  return (
    <div className="min-w-0 space-y-6">
      <header className="min-w-0">
        <p className="eyebrow mb-2">
          <Link to="/indices" className="hover:text-primary hover:underline">
            Indices
          </Link>
          <span className="mx-1.5 text-muted-foreground/60">/</span>
          {index.exchange}
          {index.index_sub_type ? (
            <>
              <span className="mx-1.5 text-muted-foreground/60">/</span>
              {index.index_sub_type}
            </>
          ) : null}
        </p>
        <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
          <div className="min-w-0">
            <h1 className="font-display text-title font-semibold tracking-tight">
              {index.index_name}
            </h1>
            <p className="mt-1 font-mono text-micro uppercase tracking-wider text-muted-foreground">
              {index.index_symbol}
            </p>
          </div>
          {quote ? (
            <div className="text-right">
              <p className="font-display text-hero font-semibold leading-none tabular">
                {formatCrore(quote.close_price)}
              </p>
              <p className={cn("mt-1 font-mono text-data tabular", up ? "text-gain" : "text-loss")}>
                {up ? "+" : ""}
                {formatCrore(quote.points_change)} ({up ? "+" : ""}
                {quote.change_pct?.toFixed(2)}%)
                <span className="ml-2 text-muted-foreground">{quote.quote_date}</span>
              </p>
            </div>
          ) : null}
        </div>
      </header>

      {quote ? (
        <section className="panel grid min-w-0 grid-cols-2 gap-4 p-4 sm:grid-cols-3 sm:p-5 lg:grid-cols-6">
          <Readout label="P/E" value={formatCrore(quote.pe)} />
          <Readout label="P/B" value={formatCrore(quote.pb)} />
          <Readout label="Div yield" value={formatPercent(quote.div_yield)} />
          <Readout label="Market cap Cr" value={formatCrore(quote.market_cap, 0)} />
          <Readout label="Day high" value={formatCrore(quote.high_price)} />
          <Readout label="Day low" value={formatCrore(quote.low_price)} />
        </section>
      ) : null}

      <div className="grid min-w-0 gap-6 lg:grid-cols-5">
        <section className="panel min-w-0 p-4 sm:p-5 lg:col-span-3">
          <h2 className="eyebrow mb-3">Returns</h2>
          <ReturnsLadder returns={index.returns} />
        </section>

        <section className="panel min-w-0 p-4 sm:p-5 lg:col-span-2">
          <h2 className="eyebrow mb-3">Constituent medians</h2>
          {index.count === 0 ? (
            <p className="text-sm text-muted-foreground">
              This is a price-only series with no published constituent list, so there is nothing
              to take a median across.
            </p>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-4">
                <Readout label="P/E" value={formatCrore(index.median.pe)} />
                <Readout label="P/B" value={formatCrore(index.median.pb)} />
                <Readout label="Div yield" value={formatPercent(index.median.dividend_yield)} />
                <Readout label="ROE" value={formatPercent(index.median.returnonequity)} />
              </div>
              <p className="mt-4 border-t pt-3 text-micro text-muted-foreground">
                {index.with_fundamentals === 0
                  ? `None of the ${index.count} constituents have had their financial statements downloaded yet.`
                  : `Medians are taken across the ${index.with_fundamentals} of ${index.count} constituents whose financial statements have been downloaded. The index P/E above is the exchange's own figure for all ${index.count}.`}
              </p>
            </>
          )}
        </section>
      </div>

      <section className="panel min-w-0 p-4 sm:p-5">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="eyebrow mb-1">
              {index.count === 0 ? "No constituent list" : `${index.count} companies`}
            </p>
            <h2 className="font-display text-lg font-semibold tracking-tight sm:text-xl">
              Constituents
            </h2>
          </div>
          {index.count > 0 ? (
            <Link
              to={`/screens?q=${encodeURIComponent(`Index = "${index.index_symbol}"`)}`}
              className="rounded-md border bg-raised px-3 py-1.5 font-mono text-micro uppercase tracking-wider transition-colors hover:text-primary"
            >
              Screen this index
            </Link>
          ) : null}
        </div>

        {index.count === 0 ? (
          <p className="py-6 text-sm text-muted-foreground">
            The exchange publishes a level for {index.index_name} but not a member list. Volatility,
            dividend-point and currency-converted series work this way.
          </p>
        ) : (
        <div className="scroll-slim -mx-1 overflow-x-auto px-1">
          <table className="w-full min-w-[30rem] border-collapse text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="py-2 pr-3 font-medium text-muted-foreground">Company</th>
                {COLUMNS.map((column) => (
                  <th key={column.key} className={cn("py-2 px-2 text-right", column.at)}>
                    <button
                      type="button"
                      onClick={() => {
                        if (sort === column.key) setAscending((value) => !value)
                        else {
                          setSort(column.key)
                          setAscending(false)
                        }
                      }}
                      className={cn(
                        "font-medium transition-colors hover:text-foreground",
                        sort === column.key ? "text-foreground" : "text-muted-foreground",
                      )}
                      aria-sort={
                        sort === column.key ? (ascending ? "ascending" : "descending") : "none"
                      }
                    >
                      {column.label}
                      {sort === column.key ? (ascending ? " ↑" : " ↓") : ""}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((row) => (
                <tr key={row.symbol} className="border-b border-grid last:border-0">
                  <td className="py-2 pr-3">
                    <Link
                      to={`/company/${row.symbol}`}
                      className="font-medium hover:text-primary hover:underline"
                    >
                      {row.name || row.symbol}
                    </Link>
                    {row.sector ? (
                      <p className="truncate text-micro text-muted-foreground">{row.sector}</p>
                    ) : null}
                  </td>
                  {COLUMNS.map((column) => {
                    const value = row[column.key]
                    const tone =
                      column.key === "change_pct" && typeof value === "number"
                        ? value < 0
                          ? "text-loss"
                          : "text-gain"
                        : ""
                    return (
                      <td
                        key={column.key}
                        className={cn(
                          "py-2 px-2 text-right font-mono text-data tabular",
                          column.at,
                          tone,
                        )}
                      >
                        {column.format(value)}
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        )}

        {index.count > 0 && index.with_fundamentals < index.count ? (
          <p className="mt-3 border-t pt-3 text-micro text-muted-foreground">
            Prices and market caps are current for all {index.count}. Financial figures show for
            the {index.with_fundamentals} whose statements have been downloaded; the rest fill in
            as the download proceeds.
          </p>
        ) : null}
      </section>
    </div>
  )
}

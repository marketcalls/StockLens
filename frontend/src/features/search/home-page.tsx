import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"

import { SearchBox } from "@/features/search/search-box"
import { api } from "@/lib/api"

export function HomePage() {
  const suggestions = useQuery({
    queryKey: ["suggestions"],
    queryFn: () => api.companies(12),
    staleTime: 5 * 60_000,
  })

  return (
    <div className="container flex min-h-[70vh] flex-col items-center justify-center py-16">
      <div className="w-full max-w-2xl text-center">
        <div className="mb-3 flex items-center justify-center gap-2">
          <span className="text-4xl font-semibold tracking-tight">StockLens</span>
          <svg width="30" height="26" viewBox="0 0 22 18" fill="none" aria-hidden>
            <rect x="0" y="11" width="5" height="7" rx="1" className="fill-primary/50" />
            <rect x="8" y="6" width="5" height="12" rx="1" className="fill-primary/75" />
            <rect x="16" y="0" width="5" height="18" rx="1" className="fill-primary" />
          </svg>
        </div>
        <p className="mb-8 text-muted-foreground">
          Stock analysis and screening tool for investors in India.
        </p>

        <SearchBox autoFocus />

        {suggestions.data?.companies.length ? (
          <div className="mt-6">
            <span className="text-sm text-muted-foreground">Or analyse:</span>
            <div className="mt-3 flex flex-wrap justify-center gap-2">
              {suggestions.data.companies.map((company) => (
                <Link
                  key={company.symbol}
                  to={`/company/${company.symbol}`}
                  className="rounded-md border px-3 py-1.5 text-sm text-muted-foreground transition hover:border-primary hover:text-foreground"
                >
                  {company.name.replace(/ (Ltd|Limited)\.?$/i, "")}
                </Link>
              ))}
            </div>
          </div>
        ) : null}

        {suggestions.data ? (
          <p className="mt-8 text-xs text-muted-foreground">
            {suggestions.data.total.toLocaleString("en-IN")} companies from NSE and BSE
          </p>
        ) : null}
      </div>
    </div>
  )
}

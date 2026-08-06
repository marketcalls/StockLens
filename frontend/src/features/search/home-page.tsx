import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"

import { Mark } from "@/components/brand"
import { SearchBox } from "@/features/search/search-box"
import { api, screener } from "@/lib/api"

/**
 * The hero states what the product does in the vocabulary of the thing itself:
 * a company, a statement, a screen. The search field is the whole interface,
 * so it gets the weight - everything else on the page defers to it.
 */
export function HomePage() {
  const suggestions = useQuery({
    queryKey: ["suggestions"],
    queryFn: () => api.companies(10),
    staleTime: 5 * 60_000,
  })
  const presets = useQuery({
    queryKey: ["screener-presets"],
    queryFn: screener.presets,
    staleTime: 10 * 60_000,
  })

  return (
    <div className="container">
      <section className="mx-auto flex min-h-[62vh] max-w-3xl flex-col justify-center py-16 md:py-24">
        <div className="animate-fade-up">
          <div className="mb-5 flex items-center gap-2.5">
            <Mark className="h-6 w-7" />
            <p className="eyebrow">NSE &amp; BSE · fundamentals</p>
          </div>
          <h1 className="font-display text-hero font-semibold">
            Read the statements,
            <br />
            not the story.
          </h1>
          <p className="mt-5 max-w-xl text-base leading-relaxed text-muted-foreground md:text-lg">
            Eight years of accounts for every listed company in India, and a query language
            to search across all of them.
          </p>
        </div>

        <div className="mt-9 animate-fade-up [animation-delay:80ms]">
          <SearchBox autoFocus />
        </div>

        {suggestions.data?.companies.length ? (
          <div className="mt-6 animate-fade-up [animation-delay:160ms]">
            <p className="eyebrow mb-2.5">Or open</p>
            <div className="flex flex-wrap gap-1.5">
              {suggestions.data.companies.map((company) => (
                <Link
                  key={company.symbol}
                  to={`/company/${company.symbol}`}
                  className="rounded-md border px-2.5 py-1.5 text-sm text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
                >
                  {company.name.replace(/ (Ltd|Limited)\.?$/i, "")}
                </Link>
              ))}
            </div>
          </div>
        ) : null}
      </section>

      <div className="rule-fade" />

      <section className="py-14 md:py-20">
        <div className="grid gap-10 md:grid-cols-[minmax(0,20rem)_1fr] md:gap-16">
          <div>
            <p className="eyebrow">Start from a question</p>
            <h2 className="mt-2 font-display text-title font-semibold">
              Ready-made screens
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              Each one is a query you can open, read and change. Nothing is hidden behind a
              black box.
            </p>
            <Link
              to="/screens"
              className="mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
            >
              Write your own query
              <span aria-hidden>→</span>
            </Link>
          </div>

          <ul className="grid gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-2">
            {(presets.data?.presets ?? []).slice(0, 8).map((preset) => (
              <li key={preset.slug}>
                <Link
                  to={`/screens?q=${encodeURIComponent(preset.query)}`}
                  className="flex h-full flex-col gap-1.5 bg-card p-4 transition-colors hover:bg-accent/50"
                >
                  <span className="text-sm font-medium">{preset.name}</span>
                  <span className="text-micro leading-relaxed text-muted-foreground">
                    {preset.description}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {suggestions.data ? (
        <p className="pb-10 text-micro text-muted-foreground">
          {suggestions.data.total.toLocaleString("en-IN")} companies indexed.
        </p>
      ) : null}
    </div>
  )
}

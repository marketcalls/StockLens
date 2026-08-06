import { useEffect, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Search, X } from "lucide-react"

import { api } from "@/lib/api"
import { cn, formatCrore } from "@/lib/utils"

/** Company autocomplete. Keyboard-first: arrows to move, Enter to open, Escape to close. */
export function SearchBox({
  autoFocus = false,
  compact = false,
}: {
  autoFocus?: boolean
  compact?: boolean
}) {
  const [term, setTerm] = useState("")
  const [debounced, setDebounced] = useState("")
  const [active, setActive] = useState(0)
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)

  // Debounce so a fast typist does not fire a request per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(term.trim()), 180)
    return () => clearTimeout(timer)
  }, [term])

  const { data, isFetching } = useQuery({
    queryKey: ["search", debounced],
    queryFn: () => api.search(debounced, 9),
    enabled: debounced.length > 0,
    staleTime: 60_000,
  })

  const results = debounced ? (data?.results ?? []) : []
  useEffect(() => setActive(0), [debounced])

  function choose(symbol: string) {
    setOpen(false)
    setTerm("")
    navigate(`/company/${symbol}`)
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault()
      setActive((i) => Math.min(i + 1, results.length - 1))
    } else if (event.key === "ArrowUp") {
      event.preventDefault()
      setActive((i) => Math.max(i - 1, 0))
    } else if (event.key === "Enter" && results[active]) {
      event.preventDefault()
      choose(results[active].symbol)
    } else if (event.key === "Escape") {
      setOpen(false)
    }
  }

  const showList = open && debounced.length > 0

  return (
    <div className="relative w-full">
      <div className="relative">
        <Search
          className={cn(
            "pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground",
            compact ? "h-4 w-4" : "h-[1.15rem] w-[1.15rem] left-4",
          )}
          aria-hidden
        />
        <input
          ref={inputRef}
          type="search"
          value={term}
          autoFocus={autoFocus}
          onChange={(e) => {
            setTerm(e.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 120)}
          onKeyDown={onKeyDown}
          placeholder={compact ? "Search companies" : "Search for a company"}
          aria-label="Search for a company"
          aria-autocomplete="list"
          aria-expanded={showList}
          className={cn(
            "w-full rounded-lg border bg-card outline-none ring-offset-background transition-all",
            "focus-visible:border-primary",
            compact
              ? "h-9 pl-9 pr-9 text-sm"
              : "h-14 pl-12 pr-12 text-base shadow-panel focus-visible:shadow-pop md:h-16 md:text-lg",
          )}
        />
        {term ? (
          <button
            type="button"
            onClick={() => {
              setTerm("")
              inputRef.current?.focus()
            }}
            aria-label="Clear search"
            className={cn(
              "absolute top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground",
              compact ? "right-3" : "right-4",
            )}
          >
            <X className={compact ? "h-4 w-4" : "h-5 w-5"} aria-hidden />
          </button>
        ) : null}
      </div>

      {showList ? (
        <ul
          role="listbox"
          className="absolute z-50 mt-2 max-h-[22rem] w-full overflow-auto rounded-lg border bg-popover p-1 shadow-pop"
        >
          {results.length === 0 ? (
            <li className="px-3 py-3 text-sm text-muted-foreground">
              {isFetching ? "Searching…" : `No company matches “${debounced}”`}
            </li>
          ) : (
            results.map((result, i) => (
              <li key={result.symbol} role="option" aria-selected={i === active}>
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => choose(result.symbol)}
                  className={cn(
                    "flex w-full items-center justify-between gap-3 rounded-md px-3 py-2 text-left",
                    i === active ? "bg-primary text-primary-foreground" : "hover:bg-accent",
                  )}
                >
                  <span className="min-w-0">
                    <span className="block truncate text-sm">{result.name}</span>
                    <span
                      className={cn(
                        "block font-mono text-micro",
                        i === active ? "text-primary-foreground/70" : "text-muted-foreground",
                      )}
                    >
                      {result.symbol}
                      {result.sector ? ` · ${result.sector}` : ""}
                    </span>
                  </span>
                  {result.market_cap ? (
                    <span
                      className={cn(
                        "tabular shrink-0 font-mono text-micro",
                        i === active ? "text-primary-foreground/70" : "text-muted-foreground",
                      )}
                    >
                      {formatCrore(result.market_cap, 0)}
                    </span>
                  ) : null}
                </button>
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  )
}

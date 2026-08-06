import { useState } from "react"
import { ChevronRight } from "lucide-react"

import { TrendRail } from "@/components/trend-rail"
import type { StatementRow } from "@/lib/api"
import { cn } from "@/lib/utils"

/**
 * Renders any financial statement.
 *
 * It knows nothing about banks, insurers or ordinary companies. The backend
 * sends a list of labelled rows already chosen for that company's schema, so
 * this component draws whatever it is given.
 *
 * Two things it does that a conventional screener does not:
 *
 * 1. Each top-level row carries a trend rail beside its label, so scanning the
 *    label column tells you the trajectory of every line at a glance.
 * 2. It shows the periods that genuinely fit the container, most recent first,
 *    rather than overflowing into a horizontal scrollbar that cuts the newest
 *    column in half. The rest are one click away.
 */

/**
 * Which periods are visible at which width.
 *
 * Indexed from the newest period backwards: index 0 is always shown, index 12
 * only on a very wide screen. Pure CSS rather than a measured column count -
 * measuring needs a re-render to take effect, and columns that pop in after
 * layout read as a glitch.
 *
 * Class strings are written out in full because Tailwind scans source text and
 * cannot see a class name assembled at runtime.
 */
const COLUMN_VISIBILITY = [
  "", // 0 - the latest period, always visible
  "",
  "",
  "hidden xs:table-cell",
  "hidden sm:table-cell",
  "hidden sm:table-cell",
  "hidden md:table-cell",
  "hidden md:table-cell",
  "hidden lg:table-cell",
  "hidden lg:table-cell",
  "hidden xl:table-cell",
  "hidden xl:table-cell",
  "hidden 2xl:table-cell",
  "hidden 2xl:table-cell",
]

function columnClass(indexFromEnd: number, showAll: boolean): string {
  if (showAll) return ""
  // Anything older than the list reaches is only available via "all periods".
  return COLUMN_VISIBILITY[indexFromEnd] ?? "hidden"
}

/**
 * Percentages, with precision matched to the size of the number.
 *
 * A whole-number margin reads fine as "45%", but the same rounding turns Axis
 * Bank's gross NPA of 1.28% into "1%" and its net NPA of 0.37% into "0%" - which
 * is how the underlying scaling bug looked before it was fixed, and just as
 * wrong. Trailing zeros are dropped so a clean 45 does not become "45.0".
 */
function formatPercentValue(value: number): string {
  const size = Math.abs(value)
  const places = size >= 100 ? 0 : size >= 10 ? 1 : 2
  const text = value.toFixed(places)
  // Only strip inside a decimal fraction. Applied to a whole number the same
  // rule eats its trailing zeros, turning a payout ratio of 100% into "1%".
  return text.includes(".") ? text.replace(/\.?0+$/, "") : text
}

function formatValue(value: number | null, unit: string): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—"
  if (unit === "percent" || unit === "fraction_pct") return `${formatPercentValue(value)}%`
  if (unit === "price" || unit === "ratio") return value.toFixed(2)
  if (unit === "count") return Math.round(value).toLocaleString("en-IN")
  return Math.round(value).toLocaleString("en-IN")
}

function Cell({
  value,
  unit,
  emphasis,
  latest,
  visibility,
}: {
  value: number | null
  unit: string
  emphasis: boolean
  latest: boolean
  visibility: string
}) {
  const negative = typeof value === "number" && value < 0
  return (
    <td
      className={cn(
        "tabular whitespace-nowrap px-2.5 py-[7px] text-right font-mono text-data tracking-tight sm:px-3",
        visibility,
        // Negative figures keep the minus sign from toLocaleString as well as
        // the colour, so the meaning survives without it.
        negative && "text-loss",
        value === null && "text-muted-foreground/50",
        emphasis && "font-semibold",
        latest && "bg-raised/60",
      )}
    >
      {formatValue(value, unit)}
    </td>
  )
}

function Line({
  row,
  lastIndex,
  showAll,
  depth = 0,
}: {
  row: StatementRow
  lastIndex: number
  showAll: boolean
  depth?: number
}) {
  const [open, setOpen] = useState(false)
  const expandable = row.children.length > 0

  return (
    <>
      <tr
        className={cn(
          "group border-b border-grid transition-colors last:border-0 hover:bg-accent/40",
          depth > 0 && "bg-muted/40 text-muted-foreground",
        )}
      >
        <th
          scope="row"
          className={cn(
            "sticky left-0 z-10 whitespace-nowrap bg-card py-[7px] pl-3 pr-3 text-left text-data font-normal group-hover:bg-accent/40 sm:pl-4",
            row.emphasis && "font-semibold",
            depth > 0 && "bg-muted/40 pl-7 text-micro group-hover:bg-muted/60 sm:pl-9",
          )}
        >
          <span className="flex items-center gap-2.5">
            {expandable ? (
              <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                className="inline-flex items-center gap-1 rounded text-left hover:text-primary"
                aria-expanded={open}
              >
                <ChevronRight
                  className={cn(
                    "h-3 w-3 shrink-0 text-muted-foreground transition-transform",
                    open && "rotate-90",
                  )}
                  aria-hidden
                />
                {row.label}
              </button>
            ) : (
              <span className={cn(depth === 0 && "pl-4")}>{row.label}</span>
            )}
            {depth === 0 ? (
              // Drawn from every period, not only the visible ones: the shape of
              // the whole history is the point.
              <TrendRail values={row.values} className="ml-auto hidden opacity-70 sm:block" />
            ) : null}
          </span>
        </th>
        {row.values.map((value, i) => (
          <Cell
            key={i}
            value={value}
            unit={row.unit}
            emphasis={row.emphasis}
            latest={i === lastIndex}
            visibility={columnClass(lastIndex - i, showAll)}
          />
        ))}
      </tr>
      {open &&
        row.children.map((child) => (
          <Line
            key={child.label}
            row={child}
            lastIndex={lastIndex}
            showAll={showAll}
            depth={depth + 1}
          />
        ))}
    </>
  )
}

export function StatementTable({
  headers,
  rows,
  note,
  emptyMessage = "No data available for this statement.",
}: {
  headers: string[]
  rows: StatementRow[]
  note?: string
  emptyMessage?: string
}) {
  const [showAll, setShowAll] = useState(false)

  if (!rows.length) {
    return <p className="py-8 text-center text-data text-muted-foreground">{emptyMessage}</p>
  }

  const lastIndex = headers.length - 1

  return (
    <div className="min-w-0">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        {note ? <p className="eyebrow">{note}</p> : <span />}
        {headers.length > 3 ? (
          <button
            type="button"
            onClick={() => setShowAll((v) => !v)}
            className="eyebrow rounded border px-2 py-1 transition-colors hover:border-primary hover:text-foreground"
          >
            {showAll ? "Show recent" : "All " + headers.length + " periods"}
          </button>
        ) : null}
      </div>

      {/* Always able to scroll inside its own box. Column fitting means it
          rarely needs to, but on a very narrow phone even three columns can
          exceed the width - and that must scroll here, never move the page. */}
      <div className="scroll-slim min-w-0 overflow-x-auto rounded-md border">
        <table className={cn("w-full border-collapse", showAll && "min-w-max")}>
          <thead>
            <tr className="border-b bg-raised">
              <th
                scope="col"
                className="sticky left-0 z-20 bg-raised py-2.5 pl-3 pr-3 text-left sm:pl-4"
              >
                <span className="sr-only">Line item</span>
              </th>
              {headers.map((header, i) => (
                <th
                  key={header}
                  scope="col"
                  className={cn(
                    "eyebrow whitespace-nowrap px-2.5 py-2.5 text-right sm:px-3",
                    columnClass(lastIndex - i, showAll),
                    i === lastIndex && "text-foreground",
                  )}
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <Line key={row.label} row={row} lastIndex={lastIndex} showAll={showAll} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

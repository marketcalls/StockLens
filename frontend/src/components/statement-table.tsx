import { useState } from "react"
import { ChevronRight } from "lucide-react"

import type { StatementRow } from "@/lib/api"
import { cn } from "@/lib/utils"

/**
 * Renders any financial statement.
 *
 * It knows nothing about banks, insurers or ordinary companies. The backend
 * sends a list of labelled rows already chosen for that company's schema, so
 * this component draws whatever it is given. That is the whole point of putting
 * the row templates on the server.
 */

function formatValue(value: number | null, unit: string): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-"
  if (unit === "percent" || unit === "fraction_pct") return `${value.toFixed(0)}%`
  if (unit === "price") return value.toFixed(2)
  if (unit === "ratio") return value.toFixed(2)
  if (unit === "count") return Math.round(value).toLocaleString("en-IN")
  // Rs. Crore, grouped Indian-style and shown whole.
  return Math.round(value).toLocaleString("en-IN")
}

function Cell({ value, unit }: { value: number | null; unit: string }) {
  const negative = typeof value === "number" && value < 0
  return (
    <td
      className={cn(
        "tabular whitespace-nowrap px-3 py-2 text-right",
        // Negative figures get a colour AND the minus sign that
        // toLocaleString already supplies, so the meaning survives without it.
        negative && "text-loss",
        value === null && "text-muted-foreground",
      )}
    >
      {formatValue(value, unit)}
    </td>
  )
}

function Line({
  row,
  depth = 0,
}: {
  row: StatementRow
  depth?: number
}) {
  const [open, setOpen] = useState(false)
  const expandable = row.children.length > 0

  return (
    <>
      <tr
        className={cn(
          "border-b border-border/50 last:border-0",
          row.emphasis && "font-semibold",
          depth > 0 && "bg-muted/30 text-muted-foreground",
        )}
      >
        <th
          scope="row"
          className={cn(
            "sticky left-0 z-10 whitespace-nowrap bg-card px-3 py-2 text-left font-normal",
            row.emphasis && "font-semibold",
            depth > 0 && "bg-muted/30 pl-8 text-xs",
          )}
        >
          {expandable ? (
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              className="inline-flex items-center gap-1 rounded hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-expanded={open}
            >
              <ChevronRight
                className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-90")}
                aria-hidden
              />
              {row.label}
            </button>
          ) : (
            <span className={cn(depth > 0 && "pl-[1.15rem] inline-block")}>{row.label}</span>
          )}
        </th>
        {row.values.map((value, i) => (
          <Cell key={i} value={value} unit={row.unit} />
        ))}
      </tr>
      {open &&
        row.children.map((child) => (
          <Line key={child.label} row={child} depth={depth + 1} />
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
  if (!rows.length) {
    return <p className="py-6 text-sm text-muted-foreground">{emptyMessage}</p>
  }

  return (
    <div>
      {note ? <p className="mb-3 text-xs text-muted-foreground">{note}</p> : null}
      {/* The table scrolls inside its own box; the page never scrolls sideways. */}
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full min-w-max border-collapse text-sm">
          <thead>
            <tr className="border-b bg-muted/50">
              <th
                scope="col"
                className="sticky left-0 z-20 bg-muted/50 px-3 py-2 text-left font-medium"
              >
                <span className="sr-only">Line item</span>
              </th>
              {headers.map((header) => (
                <th
                  key={header}
                  scope="col"
                  className="whitespace-nowrap px-3 py-2 text-right font-medium"
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <Line key={row.label} row={row} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

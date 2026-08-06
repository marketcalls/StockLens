import { Link } from "react-router-dom"

import type { ScreenResult } from "@/lib/api"
import { cn } from "@/lib/utils"

function formatCell(value: string | number | null, unit: string): string {
  if (value === null || value === undefined) return "-"
  if (typeof value === "string") return value
  if (Number.isNaN(value)) return "-"
  if (unit === "percent") return `${value.toFixed(2)}%`
  if (unit === "ratio" || unit === "price") return value.toFixed(2)
  if (unit === "days") return value.toFixed(0)
  if (unit === "count") return Math.round(value).toLocaleString("en-IN")
  return Math.round(value).toLocaleString("en-IN")
}

export function ResultsGrid({ result }: { result: ScreenResult }) {
  if (result.total === 0) {
    return (
      <div className="rounded-lg border bg-card p-8 text-center">
        <p className="text-sm font-medium">No companies match this query</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Try loosening a condition, or check the units - money is in Rs. Crore and
          percentages are plain numbers.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">
            {result.total.toLocaleString("en-IN")}
          </span>{" "}
          {result.total === 1 ? "company matches" : "companies match"}
          {result.capped ? (
            <>
              {" "}
              &mdash; showing the first {result.returned}
            </>
          ) : null}
        </p>
        <p className="tabular text-xs text-muted-foreground">{result.elapsed_ms} ms</p>
      </div>

      <div className="overflow-x-auto rounded-md border">
        <table className="w-full min-w-max text-sm">
          <thead>
            <tr className="border-b bg-muted/50 text-left">
              <th scope="col" className="px-3 py-2 font-medium text-muted-foreground">
                #
              </th>
              {result.columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={cn(
                    "whitespace-nowrap px-3 py-2 font-medium",
                    column.key === "name" ? "text-left" : "text-right",
                  )}
                >
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row, index) => (
              <tr key={String(row.symbol)} className="border-b border-border/50 last:border-0">
                <td className="tabular px-3 py-2 text-muted-foreground">
                  {(result.page - 1) * result.page_size + index + 1}
                </td>
                {result.columns.map((column) => (
                  <td
                    key={column.key}
                    className={cn(
                      "tabular whitespace-nowrap px-3 py-2",
                      column.key === "name" ? "text-left" : "text-right",
                      typeof row[column.key] === "number" &&
                        (row[column.key] as number) < 0 &&
                        "text-loss",
                      row[column.key] === null && "text-muted-foreground",
                    )}
                  >
                    {column.key === "name" ? (
                      <Link
                        to={`/company/${row.symbol}`}
                        className="text-primary hover:underline"
                      >
                        {formatCell(row[column.key], column.unit)}
                      </Link>
                    ) : (
                      formatCell(row[column.key], column.unit)
                    )}
                  </td>
                ))}
              </tr>
            ))}

            {/* The wall is a real row, not a pop-up. It states the true count. */}
            {result.capped ? (
              <tr className="border-t bg-muted/40">
                <td
                  colSpan={result.columns.length + 1}
                  className="px-3 py-4 text-center text-sm"
                >
                  <span className="text-muted-foreground">
                    {(result.total - result.returned).toLocaleString("en-IN")} more{" "}
                    {result.total - result.returned === 1 ? "company matches" : "companies match"}.
                  </span>{" "}
                  <Link
                    to="/signup?next=/screens"
                    className="font-medium text-primary hover:underline"
                  >
                    Create a free account to see all{" "}
                    {result.total.toLocaleString("en-IN")}.
                  </Link>
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  )
}

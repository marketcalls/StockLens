import { RETURN_HORIZONS, type ReturnHorizon } from "@/lib/api"
import { cn } from "@/lib/utils"

/**
 * Returns across every horizon FinEdge publishes, as diverging bars from a
 * shared zero line.
 *
 * A column of numbers makes you compare eight figures by reading them. Bars off
 * a common baseline make the shape obvious: an index up 12% over ten years but
 * down 4% over six months reads as a long climb with a recent dip, without the
 * reader doing any arithmetic.
 *
 * Bars are scaled against the largest absolute return present, so a set of
 * single-digit returns still fills the space rather than collapsing to nothing.
 */
export function ReturnsLadder({
  returns,
  className,
}: {
  returns: Partial<Record<ReturnHorizon, number>>
  className?: string
}) {
  const present = RETURN_HORIZONS.filter((h) => typeof returns[h] === "number")
  if (present.length === 0) {
    return <p className="py-4 text-sm text-muted-foreground">No return history published.</p>
  }

  const peak = Math.max(...present.map((h) => Math.abs(returns[h] as number)), 1)

  return (
    <div className={cn("space-y-1.5", className)}>
      {present.map((horizon) => {
        const value = returns[horizon] as number
        const share = Math.abs(value) / peak
        const negative = value < 0
        return (
          <div key={horizon} className="flex items-center gap-2 sm:gap-3">
            <span className="w-8 shrink-0 font-mono text-micro uppercase tracking-wider text-muted-foreground">
              {horizon}
            </span>
            {/* Two equal halves meeting at a centre line, so the sign of the
                return is carried by direction as well as by colour. */}
            <div className="flex min-w-0 flex-1 items-center" aria-hidden>
              <div className="flex flex-1 justify-end">
                {negative ? (
                  <div
                    className="h-3.5 rounded-l-sm bg-loss/70"
                    style={{ width: `${share * 100}%` }}
                  />
                ) : null}
              </div>
              <div className="h-4 w-px shrink-0 bg-border" />
              <div className="flex flex-1 justify-start">
                {negative ? null : (
                  <div
                    className="h-3.5 rounded-r-sm bg-gain/70"
                    style={{ width: `${share * 100}%` }}
                  />
                )}
              </div>
            </div>
            <span
              className={cn(
                "w-16 shrink-0 text-right font-mono text-data tabular",
                negative ? "text-loss" : "text-gain",
              )}
            >
              {value > 0 ? "+" : ""}
              {value.toFixed(2)}%
            </span>
          </div>
        )
      })}
      <p className="pt-1 text-micro text-muted-foreground">
        Annualised beyond one year, as published by the exchange.
      </p>
    </div>
  )
}

/** Compact inline version for a row in the index list. */
export function ReturnsSpark({ returns }: { returns: Partial<Record<ReturnHorizon, number>> }) {
  const present = RETURN_HORIZONS.filter((h) => typeof returns[h] === "number")
  if (present.length === 0) return <span className="text-muted-foreground">-</span>
  const peak = Math.max(...present.map((h) => Math.abs(returns[h] as number)), 1)
  return (
    <span className="inline-flex h-5 items-end gap-px" title={present.map((h) => `${h} ${returns[h]}%`).join("  ")}>
      {present.map((h) => {
        const value = returns[h] as number
        const height = Math.max(2, (Math.abs(value) / peak) * 18)
        return (
          <span
            key={h}
            className={cn("w-1 rounded-sm", value < 0 ? "bg-loss/60" : "bg-gain/60")}
            style={{ height: `${height}px` }}
          />
        )
      })}
    </span>
  )
}

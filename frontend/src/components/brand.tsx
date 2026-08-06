import { cn } from "@/lib/utils"

/**
 * The mark: three bars rising, the last one cut by a lens line.
 *
 * Bars alone would be any finance product. The horizontal line reading across
 * them is the "lens" - the thing that makes a screener a screener rather than
 * a chart.
 */
export function Mark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 20" fill="none" className={cn("h-5 w-6", className)} aria-hidden>
      <rect x="0" y="12" width="5" height="8" rx="1.5" className="fill-primary/40" />
      <rect x="9" y="6" width="5" height="14" rx="1.5" className="fill-primary/70" />
      <rect x="18" y="0" width="5" height="20" rx="1.5" className="fill-primary" />
      <line
        x1="0"
        y1="9.5"
        x2="24"
        y2="9.5"
        className="stroke-foreground"
        strokeWidth="1"
        strokeDasharray="2.5 2"
        opacity="0.45"
      />
    </svg>
  )
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("flex items-center gap-2", className)}>
      <span className="font-display text-lg font-semibold tracking-tight">StockLens</span>
      <Mark />
    </span>
  )
}

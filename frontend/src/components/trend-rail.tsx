import { useId } from "react"

import { cn } from "@/lib/utils"

/**
 * A statement row's trajectory, drawn beside its label.
 *
 * This is the one thing StockLens does that a conventional screener does not.
 * A statement table gives you fifteen numbers per row and leaves you to work
 * out the shape in your head. The rail draws it: scanning the label column
 * tells you at a glance which lines are rising, which are flat, and which have
 * turned over.
 *
 * Deliberately unlabelled and unscaled. It answers "what direction" and nothing
 * more - the exact figures are right there in the same row.
 */
export function TrendRail({
  values,
  width = 46,
  height = 16,
  className,
}: {
  values: (number | null)[]
  width?: number
  height?: number
  className?: string
}) {
  const id = useId()
  const points = values.filter((v): v is number => v !== null && Number.isFinite(v))

  // Two points is the minimum that can describe a direction.
  if (points.length < 3) return <span className={cn("inline-block", className)} style={{ width }} />

  const min = Math.min(...points)
  const max = Math.max(...points)
  const span = max - min || Math.abs(max) || 1

  // A series that crosses zero gets a baseline, because "went negative" is the
  // most important thing a financial line can do.
  const crossesZero = min < 0 && max > 0
  const pad = 2
  const usable = height - pad * 2
  const y = (v: number) => pad + usable - ((v - min) / span) * usable
  const x = (i: number) => (i / (points.length - 1)) * width

  const path = points.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ")
  const area = `${path} L${width},${height - pad} L0,${height - pad} Z`

  const first = points[0]
  const last = points[points.length - 1]
  const rising = last >= first
  const stroke = rising ? "hsl(var(--gain))" : "hsl(var(--loss))"

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={cn("shrink-0 overflow-visible", className)}
      aria-hidden
      focusable="false"
    >
      <defs>
        <linearGradient id={`rail-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.18" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      {crossesZero ? (
        <line
          x1="0"
          x2={width}
          y1={y(0)}
          y2={y(0)}
          stroke="hsl(var(--muted-foreground))"
          strokeWidth="0.5"
          strokeDasharray="2 2"
          opacity="0.5"
        />
      ) : null}
      <path d={area} fill={`url(#rail-${id})`} />
      <path
        d={path}
        fill="none"
        stroke={stroke}
        strokeWidth="1.25"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={x(points.length - 1)} cy={y(last)} r="1.75" fill={stroke} />
    </svg>
  )
}

/**
 * Where the current price sits in its 52-week range.
 *
 * "High / Low: 1611 / 1251" tells you the ends. It does not tell you that the
 * price is a fifth of the way up, which is the thing a reader actually wants.
 */
export function RangeTrack({
  low,
  high,
  current,
  className,
}: {
  low: number
  high: number
  current: number
  className?: string
}) {
  const span = high - low
  const pct = span > 0 ? Math.min(100, Math.max(0, ((current - low) / span) * 100)) : 50

  return (
    <div className={cn("w-full", className)}>
      <div className="relative h-1.5 rounded-full bg-muted">
        <div
          className="absolute inset-y-0 left-0 origin-left rounded-full bg-primary/25 animate-sweep-in"
          style={{ width: `${pct}%` }}
        />
        <div
          className="absolute top-1/2 h-3 w-[3px] -translate-y-1/2 rounded-full bg-primary"
          style={{ left: `calc(${pct}% - 1.5px)` }}
        />
      </div>
      <div className="mt-1.5 flex justify-between">
        <span className="eyebrow tabular">{low.toLocaleString("en-IN")}</span>
        <span className="eyebrow">52 week range</span>
        <span className="eyebrow tabular">{high.toLocaleString("en-IN")}</span>
      </div>
    </div>
  )
}

import { useEffect, useMemo, useRef, useState } from "react"

import type { ScreenerColumn } from "@/lib/api"
import { cn } from "@/lib/utils"

/**
 * Query box with column autocomplete.
 *
 * Column names contain spaces, so the suggestion has to be matched against the
 * trailing run of words rather than the last "word". Typing "Return on eq"
 * should suggest "Return on equity", which a naive last-token match cannot do.
 */

const OPERATOR_BOUNDARY = /[<>=()+\-*/,]|\bAND\b|\bOR\b|\bNOT\b/gi

function currentFragment(text: string, caret: number): { text: string; start: number } {
  const before = text.slice(0, caret)
  let start = 0
  OPERATOR_BOUNDARY.lastIndex = 0
  let match: RegExpExecArray | null
  while ((match = OPERATOR_BOUNDARY.exec(before)) !== null) {
    start = match.index + match[0].length
  }
  const fragment = before.slice(start)
  const trimmed = fragment.replace(/^\s+/, "")
  return { text: trimmed, start: start + (fragment.length - trimmed.length) }
}

export function QueryEditor({
  value,
  onChange,
  onRun,
  columns,
  error,
  running,
}: {
  value: string
  onChange: (v: string) => void
  onRun: () => void
  columns: ScreenerColumn[]
  error?: { message: string; position: number | null } | null
  running?: boolean
}) {
  const [caret, setCaret] = useState(0)
  const [active, setActive] = useState(0)
  const [dismissed, setDismissed] = useState(false)
  const ref = useRef<HTMLTextAreaElement>(null)

  const fragment = useMemo(() => currentFragment(value, caret), [value, caret])

  const suggestions = useMemo(() => {
    const term = fragment.text.trim().toLowerCase()
    if (term.length < 2 || dismissed) return []
    const scored = columns
      .filter((c) => c.screenable || c.unit === "text")
      .map((c) => {
        const names = [c.label, ...c.aliases]
        const best = names
          .map((n) => n.toLowerCase())
          .reduce<number>((rank, name) => {
            if (name === term) return Math.min(rank, 0)
            if (name.startsWith(term)) return Math.min(rank, 1)
            if (name.includes(term)) return Math.min(rank, 2)
            return rank
          }, 99)
        return { column: c, rank: best }
      })
      .filter((s) => s.rank < 99)
      .sort((a, b) => a.rank - b.rank || a.column.label.length - b.column.label.length)
    return scored.slice(0, 8).map((s) => s.column)
  }, [columns, fragment.text, dismissed])

  useEffect(() => setActive(0), [fragment.text])

  function accept(column: ScreenerColumn) {
    const before = value.slice(0, fragment.start)
    const after = value.slice(caret)
    const next = `${before}${column.label} ${after}`
    onChange(next)
    setDismissed(true)
    requestAnimationFrame(() => {
      const position = before.length + column.label.length + 1
      ref.current?.focus()
      ref.current?.setSelectionRange(position, position)
      setCaret(position)
    })
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (suggestions.length) {
      if (event.key === "ArrowDown") {
        event.preventDefault()
        setActive((i) => Math.min(i + 1, suggestions.length - 1))
        return
      }
      if (event.key === "ArrowUp") {
        event.preventDefault()
        setActive((i) => Math.max(i - 1, 0))
        return
      }
      if (event.key === "Tab" || (event.key === "Enter" && !event.shiftKey && !event.ctrlKey)) {
        event.preventDefault()
        accept(suggestions[active])
        return
      }
      if (event.key === "Escape") {
        setDismissed(true)
        return
      }
    }
    // Ctrl/Cmd+Enter always runs, even with the suggestion list open.
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault()
      onRun()
    }
  }

  return (
    <div className="space-y-2">
      <div className="relative">
        <textarea
          ref={ref}
          value={value}
          rows={3}
          spellCheck={false}
          onChange={(e) => {
            onChange(e.target.value)
            setCaret(e.target.selectionStart)
            setDismissed(false)
          }}
          onKeyDown={onKeyDown}
          onSelect={(e) => setCaret((e.target as HTMLTextAreaElement).selectionStart)}
          placeholder={'Market Capitalization > 500 AND Return on equity > 15'}
          aria-label="Screener query"
          className={cn(
            "w-full resize-y rounded-md border bg-card p-3 font-mono text-sm outline-none ring-offset-background transition",
            "focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring",
            error && "border-loss",
          )}
        />
        {suggestions.length ? (
          <ul
            role="listbox"
            aria-label="Column suggestions"
            className="absolute z-40 mt-1 w-full max-w-md overflow-hidden rounded-md border bg-popover p-1 shadow-lg"
          >
            {suggestions.map((column, i) => (
              <li key={column.key} role="option" aria-selected={i === active}>
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => accept(column)}
                  className={cn(
                    "flex w-full items-baseline justify-between gap-3 rounded px-2 py-1.5 text-left text-sm",
                    i === active ? "bg-primary text-primary-foreground" : "hover:bg-accent",
                  )}
                >
                  <span>{column.label}</span>
                  <span
                    className={cn(
                      "shrink-0 text-xs",
                      i === active ? "text-primary-foreground/70" : "text-muted-foreground",
                    )}
                  >
                    {column.unit}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      {error ? (
        <p role="alert" className="text-sm text-loss">
          {error.message}
          {error.position !== null ? (
            <span className="text-muted-foreground"> (at character {error.position + 1})</span>
          ) : null}
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">
          Figures in Rs. Crore, percentages as numbers. Press Tab to accept a suggestion,
          Ctrl+Enter to run.
        </p>
      )}

      <button
        type="button"
        onClick={onRun}
        disabled={running || !value.trim()}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
      >
        {running ? "Running..." : "Run this query"}
      </button>
    </div>
  )
}

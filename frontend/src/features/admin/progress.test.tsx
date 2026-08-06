import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { Progress } from "./admin-page"
import type { IngestionRunDetail } from "@/lib/api"

const run = (over: Partial<IngestionRunDetail> = {}): IngestionRunDetail => ({
  id: "abc12345",
  job_kind: "backfill",
  scope: '{"symbols": 500}',
  status: "running",
  calls_made: 0,
  call_budget: null,
  bytes_fetched: 0,
  rows_written: 0,
  started_at: "2026-08-07T00:00:00+00:00",
  finished_at: null,
  error: null,
  progress: { done: 6185 },
  symbols_done: 113,
  symbols_total: 500,
  is_active: true,
  ...over,
})

describe("Progress", () => {
  it("measures a backfill in companies, not tasks", () => {
    // The bug: task rows are written as the run reaches each company, so
    // "tasks done over tasks recorded" read 6,185 / 6,185 - a full bar on a
    // run that was 23% through.
    render(<Progress run={run()} />)
    expect(screen.getByText(/113 \/ 500 companies/)).toBeInTheDocument()
    expect(screen.queryByText(/6,185/)).not.toBeInTheDocument()
  })

  it("fills the bar in proportion to companies done", () => {
    const { container } = render(<Progress run={run()} />)
    const bar = container.querySelector("span[style*='width']") as HTMLElement
    expect(bar.style.width).toBe("23%")
  })

  it("reports calls for a job with no per-company scope", () => {
    // The universe sync and price refresh have nothing to divide by, so
    // inventing a denominator would be a fabricated percentage.
    const { container } = render(
      <Progress run={run({ job_kind: "universe", scope: null, symbols_total: null, calls_made: 4 })} />,
    )
    expect(screen.getByText(/4 calls/)).toBeInTheDocument()
    expect(container.querySelector("span[style*='width']")).toBeNull()
  })

  it("shows a fresh run as empty rather than complete", () => {
    const { container } = render(<Progress run={run({ symbols_done: 0 })} />)
    const bar = container.querySelector("span[style*='width']") as HTMLElement
    expect(bar.style.width).toBe("0%")
    expect(screen.getByText(/0 \/ 500 companies/)).toBeInTheDocument()
  })

  it("never draws past full even if more companies are seen than planned", () => {
    const { container } = render(<Progress run={run({ symbols_done: 520 })} />)
    const bar = container.querySelector("span[style*='width']") as HTMLElement
    expect(bar.style.width).toBe("100%")
  })

  it("surfaces failures alongside the count", () => {
    render(<Progress run={run({ progress: { done: 100, failed: 7 } })} />)
    expect(screen.getByText(/7 failed/)).toBeInTheDocument()
  })
})

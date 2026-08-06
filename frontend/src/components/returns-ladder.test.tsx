import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { ReturnsLadder, ReturnsSpark } from "./returns-ladder"
import type { ReturnHorizon } from "@/lib/api"

/** The shape a real index returns: eight horizons, mixed signs. */
const NIFTY_50: Partial<Record<ReturnHorizon, number>> = {
  "1M": 0.96,
  "3M": 1.24,
  "6M": -4.29,
  "1Y": 0.25,
  "3Y": 8.32,
  "5Y": 8.69,
  "7Y": 12.28,
  "10Y": 10.99,
}

function widthOf(element: Element): number {
  return Number.parseFloat((element as HTMLElement).style.width) || 0
}

describe("ReturnsLadder", () => {
  it("shows every horizon that has a figure", () => {
    render(<ReturnsLadder returns={NIFTY_50} />)
    for (const horizon of ["1M", "3M", "6M", "1Y", "3Y", "5Y", "7Y", "10Y"]) {
      expect(screen.getByText(horizon)).toBeInTheDocument()
    }
  })

  it("orders horizons shortest to longest regardless of object key order", () => {
    // JSON objects arrive in whatever order the server serialised them, which
    // for the live API is alphabetical: 10Y, 1M, 1Y, 3M...
    const scrambled = { "10Y": 10.99, "1M": 0.96, "1Y": 0.25, "3M": 1.24 } as const
    const { container } = render(<ReturnsLadder returns={scrambled} />)
    const labels = [...container.querySelectorAll("span.w-8")].map((n) => n.textContent)
    expect(labels).toEqual(["1M", "3M", "1Y", "10Y"])
  })

  it("marks a negative return with a sign and the loss colour", () => {
    render(<ReturnsLadder returns={{ "6M": -4.29 }} />)
    const value = screen.getByText("-4.29%")
    expect(value.className).toContain("text-loss")
  })

  it("prefixes a positive return with a plus so the sign is never ambiguous", () => {
    render(<ReturnsLadder returns={{ "1Y": 8.32 }} />)
    expect(screen.getByText("+8.32%")).toBeInTheDocument()
  })

  it("scales bars against the largest return present, not a fixed ceiling", () => {
    // All returns are small. Scaled against a fixed 100% they would be invisible;
    // scaled against the peak the largest fills the track.
    const { container } = render(<ReturnsLadder returns={{ "1M": 0.5, "3M": 1.0 }} />)
    const bars = [...container.querySelectorAll("div[style*='width']")]
    expect(bars).toHaveLength(2)
    const widths = bars.map(widthOf).sort((a, b) => a - b)
    expect(widths[1]).toBe(100)
    expect(widths[0]).toBe(50)
  })

  it("keeps a single return from rendering an empty track", () => {
    const { container } = render(<ReturnsLadder returns={{ "1Y": 3.2 }} />)
    const bar = container.querySelector("div[style*='width']")
    expect(widthOf(bar!)).toBe(100)
  })

  it("says so plainly when an index publishes no returns", () => {
    render(<ReturnsLadder returns={{}} />)
    expect(screen.getByText(/no return history/i)).toBeInTheDocument()
  })

  it("ignores horizons the server omitted rather than drawing them as zero", () => {
    // A missing horizon is unknown, not flat. Drawing a zero bar would assert
    // the index went nowhere over that period.
    const { container } = render(<ReturnsLadder returns={{ "1M": 2.0, "10Y": 9.0 }} />)
    expect(container.querySelectorAll("div[style*='width']")).toHaveLength(2)
    expect(screen.queryByText("3M")).not.toBeInTheDocument()
  })
})

describe("ReturnsSpark", () => {
  it("draws one bar per published horizon", () => {
    const { container } = render(<ReturnsSpark returns={NIFTY_50} />)
    expect(container.querySelectorAll("span[style*='height']")).toHaveLength(8)
  })

  it("falls back to a dash when there is nothing to draw", () => {
    render(<ReturnsSpark returns={{}} />)
    expect(screen.getByText("-")).toBeInTheDocument()
  })

  it("gives every bar a visible minimum height so a flat period is not invisible", () => {
    const { container } = render(<ReturnsSpark returns={{ "1M": 0.001, "1Y": 20 }} />)
    const heights = [...container.querySelectorAll("span[style*='height']")].map((n) =>
      Number.parseFloat((n as HTMLElement).style.height),
    )
    expect(Math.min(...heights)).toBeGreaterThanOrEqual(2)
  })
})

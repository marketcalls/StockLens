import { render, screen, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"

import { ResultsGrid } from "./results-grid"
import type { ScreenResult } from "@/lib/api"

const result = (over: Partial<ScreenResult> = {}): ScreenResult => ({
  query: "PE < 20",
  columns: [
    { key: "name", label: "Name", unit: "text" },
    { key: "market_cap", label: "Market Capitalization", unit: "crore" },
    { key: "pe", label: "Price to Earning", unit: "ratio" },
    { key: "returnonequity", label: "Return on equity", unit: "percent" },
  ],
  rows: [
    { symbol: "HDFCBANK", name: "HDFC Bank Ltd", market_cap: 1135078, pe: 14.35, returnonequity: 13.59 },
    { symbol: "SBIN", name: "State Bank Of India", market_cap: 1001384, pe: 12.02, returnonequity: 13.55 },
  ],
  total: 2,
  returned: 2,
  capped: false,
  cap: 25,
  elapsed_ms: 1.2,
  page: 1,
  page_size: 50,
  ...over,
})

const view = (r: ScreenResult) =>
  render(
    <MemoryRouter>
      <ResultsGrid result={r} />
    </MemoryRouter>,
  )

describe("ResultsGrid", () => {
  it("states how many companies matched", () => {
    view(result({ total: 137, returned: 2 }))
    expect(screen.getByText("137")).toBeInTheDocument()
    expect(screen.getByText(/companies match/)).toBeInTheDocument()
  })

  it("uses the singular for one match", () => {
    view(result({ total: 1, returned: 1, rows: [result().rows[0]] }))
    expect(screen.getByText(/company matches/)).toBeInTheDocument()
  })

  it("groups money in the Indian numbering system", () => {
    view(result())
    expect(screen.getByText("11,35,078")).toBeInTheDocument()
  })

  it("renders percentages with a sign and ratios plain", () => {
    view(result())
    expect(screen.getByText("13.59%")).toBeInTheDocument()
    expect(screen.getByText("14.35")).toBeInTheDocument()
  })

  it("links the company name to its page", () => {
    view(result())
    expect(screen.getByRole("link", { name: "HDFC Bank Ltd" })).toHaveAttribute(
      "href",
      "/company/HDFCBANK",
    )
  })

  it("numbers the rows", () => {
    view(result())
    const body = screen.getAllByRole("rowgroup")[1]
    const firstCells = within(body)
      .getAllByRole("row")
      .map((row) => row.querySelector("td")?.textContent)
    expect(firstCells).toEqual(["1", "2"])
  })

  it("shows an em dash for a missing figure rather than zero", () => {
    view(
      result({
        rows: [{ symbol: "X", name: "X Ltd", market_cap: 100, pe: null, returnonequity: null }],
        total: 1,
        returned: 1,
      }),
    )
    expect(screen.getAllByText("—").length).toBeGreaterThan(0)
  })

  it("shows the cap as a real row stating the true total", () => {
    view(result({ total: 340, returned: 25, capped: true }))
    expect(screen.getByText(/315 more/)).toBeInTheDocument()
    // The invitation is a link, not a dead statement, and carries the true count.
    const link = screen.getByRole("link", { name: /see all 340/ })
    expect(link).toHaveAttribute("href", "/signup?next=/screens")
  })

  it("does not show the cap row when everything fits", () => {
    view(result())
    expect(screen.queryByRole("link", { name: /see all/ })).not.toBeInTheDocument()
  })

  it("explains an empty result rather than showing a blank table", () => {
    view(result({ total: 0, returned: 0, rows: [] }))
    expect(screen.getByText(/No companies match this query/)).toBeInTheDocument()
    expect(screen.getByText(/Rs. Crore/)).toBeInTheDocument()
  })

  it("reports how long the query took", () => {
    view(result())
    expect(screen.getByText("1.2 ms")).toBeInTheDocument()
  })

  it("continues row numbering onto later pages", () => {
    view(result({ page: 2, page_size: 50 }))
    expect(screen.getByText("51")).toBeInTheDocument()
  })
})

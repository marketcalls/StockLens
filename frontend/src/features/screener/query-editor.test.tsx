import { act, fireEvent, render, screen } from "@testing-library/react"
import { useState } from "react"
import { describe, expect, it, vi } from "vitest"

import { QueryEditor } from "./query-editor"
import type { ScreenerColumn } from "@/lib/api"

const columns: ScreenerColumn[] = [
  { key: "returnonequity", label: "Return on equity", unit: "percent", aliases: ["ROE"], description: "", screenable: true },
  { key: "roe3yearsavg", label: "Average return on equity 3Years", unit: "percent", aliases: ["ROE 3Y"], description: "", screenable: true },
  { key: "market_cap", label: "Market Capitalization", unit: "crore", aliases: ["Market cap"], description: "", screenable: true },
  { key: "pe", label: "Price to Earning", unit: "ratio", aliases: ["PE"], description: "", screenable: true },
  { key: "sector", label: "Sector", unit: "text", aliases: [], description: "", screenable: false },
]

/** QueryEditor is controlled, so the harness has to hold the value itself.
 *  Passing a static `value` means typing never changes what renders - which is
 *  how the first version of these tests failed against working code. */
function Editor({
  initial = "",
  onChange,
  ...props
}: Partial<React.ComponentProps<typeof QueryEditor>> & { initial?: string } = {}) {
  const [value, setValue] = useState(initial)
  return (
    <QueryEditor
      value={value}
      onChange={(v) => {
        setValue(v)
        onChange?.(v)
      }}
      onRun={() => {}}
      columns={columns}
      {...props}
    />
  )
}

describe("QueryEditor", () => {
  it("suggests columns from a partial name", () => {
    render(<Editor />)
    const box = screen.getByLabelText("Screener query")
    act(() => {
      fireEvent.change(box, { target: { value: "Return on eq" } })
    })
    expect(screen.getByRole("option", { name: /Return on equity/ })).toBeInTheDocument()
  })

  it("matches against the trailing run of words, not the last word", () => {
    /* Column names contain spaces. A last-token match on "eq" would never find
       "Return on equity". */
    render(<Editor />)
    const box = screen.getByLabelText("Screener query")
    act(() => {
      fireEvent.change(box, { target: { value: "Return on equ" } })
    })
    expect(screen.getByRole("option", { name: /Return on equity/ })).toBeInTheDocument()
  })

  it("starts a fresh fragment after a boolean operator", () => {
    render(<Editor />)
    const box = screen.getByLabelText("Screener query")
    act(() => {
      fireEvent.change(box, { target: { value: "PE < 20 AND Market Cap" } })
    })
    expect(screen.getByRole("option", { name: /Market Capitalization/ })).toBeInTheDocument()
  })

  it("suggests by alias", () => {
    render(<Editor />)
    const box = screen.getByLabelText("Screener query")
    act(() => {
      fireEvent.change(box, { target: { value: "roe" } })
    })
    expect(screen.getByRole("option", { name: /Return on equity/ })).toBeInTheDocument()
  })

  it("does not suggest on a single character", () => {
    render(<Editor />)
    const box = screen.getByLabelText("Screener query")
    act(() => {
      fireEvent.change(box, { target: { value: "R" } })
    })
    expect(screen.queryByRole("option")).not.toBeInTheDocument()
  })

  it("inserts the chosen column into the query", () => {
    const onChange = vi.fn()
    render(<Editor onChange={onChange} />)
    const box = screen.getByLabelText("Screener query")
    act(() => {
      fireEvent.change(box, { target: { value: "Return on equ" } })
    })
    act(() => {
      screen.getByRole("option", { name: /^Return on equity/ }).querySelector("button")!.click()
    })
    expect(onChange).toHaveBeenCalledWith(expect.stringContaining("Return on equity"))
  })

  it("shows a parse error with its position", () => {
    render(<Editor initial="Nonsense > 1" error={{ message: 'Unknown column: "Nonsense"', position: 0 }} />)
    const alert = screen.getByRole("alert")
    expect(alert).toHaveTextContent("Unknown column")
    expect(alert).toHaveTextContent("character 1")
  })

  it("explains the units when there is no error", () => {
    render(<Editor initial="PE < 20" />)
    expect(screen.getByText(/Rs. Crore/)).toBeInTheDocument()
  })

  it("disables the run button for an empty query", () => {
    render(<Editor initial="   " />)
    expect(screen.getByRole("button", { name: /Run this query/ })).toBeDisabled()
  })

  it("runs on click", () => {
    const onRun = vi.fn()
    render(<Editor initial="PE < 20" onRun={onRun} />)
    act(() => screen.getByRole("button", { name: /Run this query/ }).click())
    expect(onRun).toHaveBeenCalled()
  })

  it("shows a running state", () => {
    render(<Editor initial="PE < 20" running />)
    expect(screen.getByRole("button", { name: /Running/ })).toBeDisabled()
  })
})

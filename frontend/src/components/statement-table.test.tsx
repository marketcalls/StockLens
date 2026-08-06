import { act, render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { StatementTable } from "./statement-table"
import type { StatementRow } from "@/lib/api"

const row = (over: Partial<StatementRow> = {}): StatementRow => ({
  label: "Sales",
  unit: "crore",
  emphasis: false,
  values: [1000, 2000],
  children: [],
  ...over,
})

describe("StatementTable", () => {
  it("renders one column per period header", () => {
    render(<StatementTable headers={["Mar 2025", "Mar 2026"]} rows={[row()]} />)
    expect(screen.getByText("Mar 2025")).toBeInTheDocument()
    expect(screen.getByText("Mar 2026")).toBeInTheDocument()
  })

  it("groups money in the Indian numbering system", () => {
    render(
      <StatementTable headers={["Mar 2026"]} rows={[row({ values: [1075675] })]} />,
    )
    // 10,75,675 not 1,075,675
    expect(screen.getByText("10,75,675")).toBeInTheDocument()
  })

  it("shows an em dash for a missing figure rather than zero", () => {
    render(<StatementTable headers={["Mar 2026"]} rows={[row({ values: [null] })]} />)
    expect(screen.getByText("—")).toBeInTheDocument()
    expect(screen.queryByText("0")).not.toBeInTheDocument()
  })

  it("keeps the minus sign on negatives so colour is not the only signal", () => {
    render(
      <StatementTable
        headers={["Mar 2026"]}
        rows={[row({ label: "Cash from Investing", values: [-101089] })]}
      />,
    )
    expect(screen.getByText("-1,01,089")).toBeInTheDocument()
  })

  it("renders percentages with a percent sign", () => {
    render(
      <StatementTable
        headers={["Mar 2026"]}
        rows={[row({ label: "OPM %", unit: "percent", values: [14] })]}
      />,
    )
    expect(screen.getByText("14%")).toBeInTheDocument()
  })

  it("renders per-share figures to two decimals", () => {
    render(
      <StatementTable
        headers={["Mar 2026"]}
        rows={[row({ label: "EPS in Rs", unit: "price", values: [59.69] })]}
      />,
    )
    expect(screen.getByText("59.69")).toBeInTheDocument()
  })

  it("hides child rows until the parent is expanded", () => {
    const parent = row({
      children: [row({ label: "Revenue from sale of product", values: [600] })],
    })
    render(<StatementTable headers={["Mar 2026"]} rows={[parent]} />)

    expect(screen.queryByText("Revenue from sale of product")).not.toBeInTheDocument()
    act(() => screen.getByRole("button", { name: /Sales/ }).click())
    expect(screen.getByText("Revenue from sale of product")).toBeInTheDocument()
  })

  it("marks the expander as collapsed and then expanded", () => {
    const parent = row({ children: [row({ label: "Child", values: [1] })] })
    render(<StatementTable headers={["Mar 2026"]} rows={[parent]} />)
    const button = screen.getByRole("button", { name: /Sales/ })
    expect(button).toHaveAttribute("aria-expanded", "false")
    act(() => button.click())
    expect(button).toHaveAttribute("aria-expanded", "true")
  })

  it("does not offer an expander when there are no children", () => {
    render(<StatementTable headers={["Mar 2026"]} rows={[row()]} />)
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })

  it("renders whatever rows it is given, with no knowledge of company type", () => {
    // The same component draws a bank. It never sees a schema name.
    render(
      <StatementTable
        headers={["Mar 2026"]}
        rows={[
          row({ label: "Financing Profit", values: [163124] }),
          row({ label: "Gross NPA %", unit: "percent", values: [1.2] }),
        ]}
      />,
    )
    expect(screen.getByText("Financing Profit")).toBeInTheDocument()
    // 1.2%, not "1%". A bank's asset quality moves in tenths, so rounding the
    // row to whole percent throws away the only part that changes.
    expect(screen.getByText("1.2%")).toBeInTheDocument()
  })

  it("shows an empty message when there are no rows", () => {
    render(<StatementTable headers={[]} rows={[]} />)
    expect(screen.getByText(/No data available/)).toBeInTheDocument()
  })

  it("shows the unit note when given one", () => {
    render(
      <StatementTable
        headers={["Mar 2026"]}
        rows={[row()]}
        note="Consolidated figures in Rs. Crore"
      />,
    )
    expect(screen.getByText("Consolidated figures in Rs. Crore")).toBeInTheDocument()
  })

  it("uses row headers so screen readers can announce each line", () => {
    render(<StatementTable headers={["Mar 2026"]} rows={[row({ values: [1] })]} />)
    const body = screen.getAllByRole("rowgroup")[1]
    expect(within(body).getByRole("rowheader", { name: "Sales" })).toBeInTheDocument()
  })
})

describe("percentage precision", () => {
  const pct = (values: number[]) =>
    render(
      <StatementTable
        headers={values.map((_, i) => `P${i}`)}
        rows={[row({ label: "Ratio", unit: "percent", values })]}
      />,
    )

  it("keeps the decimals a small percentage lives in", () => {
    // Axis Bank's gross NPA is 1.28% and its net NPA 0.37%. Rounded to whole
    // percent those read "1%" and "0%" - which is how the scaling bug looked
    // before it was fixed, and just as wrong.
    pct([1.28, 0.37])
    expect(screen.getByText("1.28%")).toBeInTheDocument()
    expect(screen.getByText("0.37%")).toBeInTheDocument()
  })

  it("does not clutter a whole-number margin", () => {
    pct([45])
    expect(screen.getByText("45%")).toBeInTheDocument()
  })

  it("keeps one decimal in the middle range", () => {
    pct([14.7])
    expect(screen.getByText("14.7%")).toBeInTheDocument()
  })

  it("does not eat the zeros of a round hundred", () => {
    // Stripping trailing zeros without checking for a decimal point turns a
    // payout ratio of 100% into "1%" and 200% into "2%".
    pct([100, 200, 1000])
    expect(screen.getByText("100%")).toBeInTheDocument()
    expect(screen.getByText("200%")).toBeInTheDocument()
    expect(screen.getByText("1000%")).toBeInTheDocument()
  })

  it("shows an insurer's combined ratio above par", () => {
    // Above 100% means an underwriting loss; it must not be clamped or reduced.
    pct([107.2])
    expect(screen.getByText("107%")).toBeInTheDocument()
  })

  it("keeps the sign on a negative", () => {
    pct([-70])
    expect(screen.getByText("-70%")).toBeInTheDocument()
  })

  it("shows a genuine zero as zero", () => {
    pct([0])
    expect(screen.getByText("0%")).toBeInTheDocument()
  })
})

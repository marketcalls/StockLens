import { describe, expect, it } from "vitest"

import { cn, formatBytes, formatCrore, formatIst, formatPercent } from "./utils"

describe("cn", () => {
  it("merges conflicting tailwind classes, last one winning", () => {
    expect(cn("px-2", "px-4")).toBe("px-4")
  })

  it("drops falsy values", () => {
    expect(cn("a", false && "b", null, undefined, "c")).toBe("a c")
  })
})

describe("formatCrore", () => {
  it("groups in the Indian numbering system", () => {
    // 17,91,661.15 not 1,791,661.15
    expect(formatCrore(1791661.15)).toBe("17,91,661.15")
  })

  it("renders a dash for missing values rather than zero", () => {
    expect(formatCrore(null)).toBe("-")
    expect(formatCrore(undefined)).toBe("-")
    expect(formatCrore(Number.NaN)).toBe("-")
  })

  it("keeps zero distinct from missing", () => {
    expect(formatCrore(0)).toBe("0.00")
  })

  it("preserves the negative sign", () => {
    expect(formatCrore(-1141.09)).toBe("-1,141.09")
  })
})

describe("formatPercent", () => {
  it("appends a percent sign", () => {
    expect(formatPercent(8.77)).toBe("8.77%")
  })

  it("renders a dash for missing values", () => {
    expect(formatPercent(null)).toBe("-")
  })
})

describe("formatBytes", () => {
  it("scales units", () => {
    expect(formatBytes(512)).toBe("512 B")
    expect(formatBytes(1024)).toBe("1.0 KB")
    expect(formatBytes(1_562_513)).toBe("1.5 MB")
  })

  it("handles zero and missing", () => {
    expect(formatBytes(0)).toBe("0 B")
    expect(formatBytes(null)).toBe("0 B")
  })
})

describe("formatIst", () => {
  it("renders UTC timestamps in IST", () => {
    // 15:51 UTC is 21:21 IST the same day.
    const out = formatIst("2026-08-06T15:51:08Z")
    expect(out).toContain("2026")
    expect(out).toMatch(/9:21|21:21/)
  })

  it("says never rather than showing an epoch", () => {
    expect(formatIst(null)).toBe("never")
  })

  it("handles an unparseable value", () => {
    expect(formatIst("not-a-date")).toBe("-")
  })
})

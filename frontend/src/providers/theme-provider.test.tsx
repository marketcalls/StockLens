import { act, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ThemeProvider, useTheme } from "./theme-provider"

const STORAGE_KEY = "stocklens-theme"

/** Replace jsdom's matchMedia with one we control, and expose its listeners. */
function mockMatchMedia(matches: boolean) {
  const listeners = new Set<() => void>()
  const query = {
    matches,
    media: "(prefers-color-scheme: dark)",
    onchange: null,
    addEventListener: (_: string, fn: () => void) => listeners.add(fn),
    removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
    dispatchEvent: () => false,
  }
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: () => query,
  })
  return {
    query,
    emit(next: boolean) {
      query.matches = next
      listeners.forEach((fn) => fn())
    },
    listenerCount: () => listeners.size,
  }
}

function Probe() {
  const { theme, resolvedTheme, setTheme } = useTheme()
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="resolved">{resolvedTheme}</span>
      <button onClick={() => setTheme("dark")}>dark</button>
      <button onClick={() => setTheme("light")}>light</button>
      <button onClick={() => setTheme("system")}>system</button>
    </div>
  )
}

beforeEach(() => {
  localStorage.clear()
  document.documentElement.classList.remove("light", "dark")
  mockMatchMedia(false)
})

describe("ThemeProvider", () => {
  it("defaults to system and resolves via the OS preference", () => {
    mockMatchMedia(true)
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    expect(screen.getByTestId("theme")).toHaveTextContent("system")
    expect(screen.getByTestId("resolved")).toHaveTextContent("dark")
    expect(document.documentElement).toHaveClass("dark")
  })

  it("puts the class on <html> so shadcn's dark variant applies", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    expect(document.documentElement).toHaveClass("light")

    act(() => screen.getByRole("button", { name: "dark" }).click())
    expect(document.documentElement).toHaveClass("dark")
    expect(document.documentElement).not.toHaveClass("light")
  })

  it("sets colorScheme so native controls match the theme", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    act(() => screen.getByRole("button", { name: "dark" }).click())
    expect(document.documentElement.style.colorScheme).toBe("dark")
  })

  it("persists the choice", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    act(() => screen.getByRole("button", { name: "dark" }).click())
    expect(localStorage.getItem(STORAGE_KEY)).toBe("dark")
  })

  it("restores a persisted choice on mount", () => {
    localStorage.setItem(STORAGE_KEY, "dark")
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    expect(screen.getByTestId("theme")).toHaveTextContent("dark")
    expect(document.documentElement).toHaveClass("dark")
  })

  it("ignores a corrupt stored value", () => {
    localStorage.setItem(STORAGE_KEY, "chartreuse")
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    expect(screen.getByTestId("theme")).toHaveTextContent("system")
  })

  it("follows the OS while set to system", () => {
    const media = mockMatchMedia(false)
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    expect(screen.getByTestId("resolved")).toHaveTextContent("light")

    act(() => media.emit(true))
    expect(document.documentElement).toHaveClass("dark")
  })

  it("stops following the OS once an explicit theme is chosen", () => {
    const media = mockMatchMedia(false)
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    act(() => screen.getByRole("button", { name: "light" }).click())
    expect(media.listenerCount()).toBe(0)

    act(() => media.emit(true))
    expect(document.documentElement).toHaveClass("light")
  })

  it("survives localStorage being unavailable", () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError")
    })
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    )
    act(() => screen.getByRole("button", { name: "dark" }).click())
    expect(document.documentElement).toHaveClass("dark")
    setItem.mockRestore()
  })

  it("throws when useTheme is used outside the provider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {})
    expect(() => render(<Probe />)).toThrow(/must be used within a ThemeProvider/)
    spy.mockRestore()
  })
})

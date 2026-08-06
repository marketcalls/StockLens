import { act, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ThemeProvider, useTheme } from "./theme-provider"

const STORAGE_KEY = "stocklens-theme"

/** Replace jsdom's matchMedia with one we control. */
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
    emit(next: boolean) {
      query.matches = next
      listeners.forEach((fn) => fn())
    },
    listenerCount: () => listeners.size,
  }
}

function Probe() {
  const { theme, setTheme, toggleTheme } = useTheme()
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <button onClick={toggleTheme}>toggle</button>
      <button onClick={() => setTheme("dark")}>set-dark</button>
      <button onClick={() => setTheme("light")}>set-light</button>
    </div>
  )
}

const view = () =>
  render(
    <ThemeProvider>
      <Probe />
    </ThemeProvider>,
  )

const press = (name: string) => act(() => screen.getByRole("button", { name }).click())

beforeEach(() => {
  localStorage.clear()
  document.documentElement.classList.remove("light", "dark")
  mockMatchMedia(false)
})

describe("ThemeProvider", () => {
  it("offers exactly two themes", () => {
    view()
    expect(screen.getByTestId("theme")).toHaveTextContent("light")
    press("toggle")
    expect(screen.getByTestId("theme")).toHaveTextContent("dark")
    press("toggle")
    expect(screen.getByTestId("theme")).toHaveTextContent("light")
  })

  it("puts the class on <html> so shadcn's dark variant applies", () => {
    view()
    expect(document.documentElement).toHaveClass("light")
    press("toggle")
    expect(document.documentElement).toHaveClass("dark")
    expect(document.documentElement).not.toHaveClass("light")
  })

  it("sets colorScheme so native controls match", () => {
    view()
    press("set-dark")
    expect(document.documentElement.style.colorScheme).toBe("dark")
  })

  it("persists the choice", () => {
    view()
    press("set-dark")
    expect(localStorage.getItem(STORAGE_KEY)).toBe("dark")
  })

  it("restores a persisted choice on mount", () => {
    localStorage.setItem(STORAGE_KEY, "dark")
    view()
    expect(screen.getByTestId("theme")).toHaveTextContent("dark")
    expect(document.documentElement).toHaveClass("dark")
  })

  it("uses the operating system preference on a first visit only", () => {
    mockMatchMedia(true)
    view()
    expect(screen.getByTestId("theme")).toHaveTextContent("dark")
  })

  it("a stored choice beats the operating system preference", () => {
    mockMatchMedia(true)
    localStorage.setItem(STORAGE_KEY, "light")
    view()
    expect(screen.getByTestId("theme")).toHaveTextContent("light")
  })

  it("never follows the OS after the first render", () => {
    /* A machine that switches to dark at sunset must not override a deliberate
       choice of light. There is no "system" mode, so nothing is listening. */
    const media = mockMatchMedia(false)
    view()
    press("set-light")
    expect(media.listenerCount()).toBe(0)

    act(() => media.emit(true))
    expect(document.documentElement).toHaveClass("light")
  })

  it("ignores a corrupt stored value", () => {
    localStorage.setItem(STORAGE_KEY, "chartreuse")
    view()
    expect(screen.getByTestId("theme")).toHaveTextContent("light")
  })

  it("ignores a stored value left over from the old three-state switcher", () => {
    /* "system" was a valid choice before; it must not survive as a theme name. */
    localStorage.setItem(STORAGE_KEY, "system")
    view()
    expect(screen.getByTestId("theme")).toHaveTextContent("light")
    expect(document.documentElement).toHaveClass("light")
  })

  it("survives localStorage being unavailable", () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError")
    })
    view()
    press("set-dark")
    expect(document.documentElement).toHaveClass("dark")
    setItem.mockRestore()
  })

  it("throws when useTheme is used outside the provider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {})
    expect(() => render(<Probe />)).toThrow(/must be used within a ThemeProvider/)
    spy.mockRestore()
  })
})

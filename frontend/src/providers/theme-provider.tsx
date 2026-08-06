import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react"

export type Theme = "light" | "dark" | "system"
export type ResolvedTheme = "light" | "dark"

const STORAGE_KEY = "stocklens-theme"

type ThemeProviderState = {
  /** What the user chose, which may be "system". */
  theme: Theme
  /** What is actually on screen right now. */
  resolvedTheme: ResolvedTheme
  setTheme: (theme: Theme) => void
}

const ThemeProviderContext = createContext<ThemeProviderState | null>(null)

function prefersDark(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false
  return window.matchMedia("(prefers-color-scheme: dark)").matches
}

function resolve(theme: Theme): ResolvedTheme {
  if (theme === "system") return prefersDark() ? "dark" : "light"
  return theme
}

function readStoredTheme(storageKey: string): Theme {
  if (typeof window === "undefined") return "system"
  try {
    const stored = window.localStorage.getItem(storageKey)
    if (stored === "light" || stored === "dark" || stored === "system") return stored
  } catch {
    // Private browsing or blocked storage. Fall through to the default.
  }
  return "system"
}

export function ThemeProvider({
  children,
  defaultTheme = "system",
  storageKey = STORAGE_KEY,
}: {
  children: React.ReactNode
  defaultTheme?: Theme
  storageKey?: string
}) {
  const [theme, setThemeState] = useState<Theme>(
    () => readStoredTheme(storageKey) ?? defaultTheme,
  )
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() => resolve(theme))

  // Stamp the class onto <html>. shadcn/ui's `class` dark-mode strategy reads
  // it, and index.html applies the same class before first paint so there is no
  // flash of the wrong theme on load.
  useEffect(() => {
    const root = window.document.documentElement
    const next = resolve(theme)
    root.classList.remove("light", "dark")
    root.classList.add(next)
    root.style.colorScheme = next
    setResolvedTheme(next)
  }, [theme])

  // Follow the OS while the choice is "system", and stop following once the
  // user picks an explicit theme.
  useEffect(() => {
    if (theme !== "system" || typeof window === "undefined" || !window.matchMedia) return
    const query = window.matchMedia("(prefers-color-scheme: dark)")
    const onChange = () => {
      const next = query.matches ? "dark" : "light"
      const root = window.document.documentElement
      root.classList.remove("light", "dark")
      root.classList.add(next)
      root.style.colorScheme = next
      setResolvedTheme(next)
    }
    query.addEventListener("change", onChange)
    return () => query.removeEventListener("change", onChange)
  }, [theme])

  const setTheme = useCallback(
    (next: Theme) => {
      try {
        window.localStorage.setItem(storageKey, next)
      } catch {
        // Storage unavailable; the choice still applies for this session.
      }
      setThemeState(next)
    },
    [storageKey],
  )

  const value = useMemo(
    () => ({ theme, resolvedTheme, setTheme }),
    [theme, resolvedTheme, setTheme],
  )

  return (
    <ThemeProviderContext.Provider value={value}>{children}</ThemeProviderContext.Provider>
  )
}

export function useTheme(): ThemeProviderState {
  const context = useContext(ThemeProviderContext)
  if (!context) throw new Error("useTheme must be used within a ThemeProvider")
  return context
}

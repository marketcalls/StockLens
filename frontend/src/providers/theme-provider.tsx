import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react"

export type Theme = "light" | "dark"

const STORAGE_KEY = "stocklens-theme"

type ThemeProviderState = {
  theme: Theme
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
}

const ThemeProviderContext = createContext<ThemeProviderState | null>(null)

function prefersDark(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false
  return window.matchMedia("(prefers-color-scheme: dark)").matches
}

/**
 * Two themes, no "follow the system" mode.
 *
 * The operating system preference is still used, but only to pick the theme on
 * a first visit. Once someone has chosen, that choice stands and the app stops
 * watching the OS - otherwise a machine that switches to dark at sunset would
 * override a deliberate choice of light.
 */
function readStoredTheme(storageKey: string): Theme | null {
  if (typeof window === "undefined") return null
  try {
    const stored = window.localStorage.getItem(storageKey)
    if (stored === "light" || stored === "dark") return stored
  } catch {
    // Private browsing or blocked storage.
  }
  return null
}

export function ThemeProvider({
  children,
  storageKey = STORAGE_KEY,
}: {
  children: React.ReactNode
  storageKey?: string
}) {
  const [theme, setThemeState] = useState<Theme>(
    () => readStoredTheme(storageKey) ?? (prefersDark() ? "dark" : "light"),
  )

  // Stamp the class onto <html>. shadcn/ui's `class` dark-mode strategy reads
  // it, and index.html applies the same class before first paint so there is no
  // flash of the wrong theme on load.
  useEffect(() => {
    const root = window.document.documentElement
    root.classList.remove("light", "dark")
    root.classList.add(theme)
    root.style.colorScheme = theme
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

  const toggleTheme = useCallback(
    () => setTheme(theme === "dark" ? "light" : "dark"),
    [theme, setTheme],
  )

  const value = useMemo(
    () => ({ theme, setTheme, toggleTheme }),
    [theme, setTheme, toggleTheme],
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

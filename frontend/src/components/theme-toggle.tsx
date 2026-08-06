import { Moon, Sun } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useTheme } from "@/providers/theme-provider"

/**
 * One button, two themes.
 *
 * The icon shows what you will get, not what you have: on a light page it shows
 * a moon, because pressing it gives you dark. The label says so explicitly for
 * anyone who cannot see the icon.
 */
export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const next = theme === "dark" ? "light" : "dark"

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggleTheme}
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
    >
      {theme === "dark" ? (
        <Sun className="h-[1.15rem] w-[1.15rem]" aria-hidden />
      ) : (
        <Moon className="h-[1.15rem] w-[1.15rem]" aria-hidden />
      )}
    </Button>
  )
}

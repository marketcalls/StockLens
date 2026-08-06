import { ThemeToggle } from "@/components/theme-toggle"
import { StatusPanel } from "@/features/meta/status-panel"

export default function App() {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="container flex h-16 items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-xl font-semibold tracking-tight">StockLens</span>
            {/* The mark: three bars, tallest last. Echoes the screener chart glyph. */}
            <svg
              width="22"
              height="18"
              viewBox="0 0 22 18"
              fill="none"
              aria-hidden
              className="translate-y-[1px]"
            >
              <rect x="0" y="11" width="5" height="7" rx="1" className="fill-primary/50" />
              <rect x="8" y="6" width="5" height="12" rx="1" className="fill-primary/75" />
              <rect x="16" y="0" width="5" height="18" rx="1" className="fill-primary" />
            </svg>
          </div>
          <ThemeToggle />
        </div>
      </header>

      <main className="container py-10">
        <div className="mb-8">
          <h1 className="text-2xl font-semibold tracking-tight">System status</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Phase 0 groundwork. The screener and company pages arrive in phases 2 and 3 -
            see <span className="font-mono text-xs">docs/prd/08-roadmap.md</span>.
          </p>
        </div>
        <StatusPanel />
      </main>

      <footer className="border-t">
        <div className="container py-6 text-xs text-muted-foreground">
          Market data from FinEdge. Figures in Rs. Crore unless stated otherwise.
        </div>
      </footer>
    </div>
  )
}

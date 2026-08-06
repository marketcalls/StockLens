import { Link, Route, Routes, useLocation } from "react-router-dom"

import { ThemeToggle } from "@/components/theme-toggle"
import { AuthPage } from "@/features/auth/auth-page"
import { WorkspacePage } from "@/features/workspace/workspace-page"
import { useAuth } from "@/providers/auth-provider"
import { CompanyPage } from "@/features/company/company-page"
import { StatusPanel } from "@/features/meta/status-panel"
import { ScreenerPage } from "@/features/screener/screener-page"
import { HomePage } from "@/features/search/home-page"
import { SearchBox } from "@/features/search/search-box"

function Header() {
  const onHome = useLocation().pathname === "/"
  return (
    <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur">
      <div className="container flex h-16 items-center gap-6">
        <Link to="/" className="flex shrink-0 items-center gap-2">
          <span className="text-lg font-semibold tracking-tight">StockLens</span>
          <svg width="20" height="17" viewBox="0 0 22 18" fill="none" aria-hidden>
            <rect x="0" y="11" width="5" height="7" rx="1" className="fill-primary/50" />
            <rect x="8" y="6" width="5" height="12" rx="1" className="fill-primary/75" />
            <rect x="16" y="0" width="5" height="18" rx="1" className="fill-primary" />
          </svg>
        </Link>

        {/* The home page has its own large search, so the header omits it there. */}
        {!onHome ? (
          <div className="max-w-md flex-1">
            <SearchBox />
          </div>
        ) : (
          <div className="flex-1" />
        )}

        <nav className="flex shrink-0 items-center gap-1">
          <AccountNav />
          <Link
            to="/screens"
            className="rounded px-3 py-1.5 text-sm text-muted-foreground transition hover:text-foreground"
          >
            Screens
          </Link>
          <Link
            to="/status"
            className="rounded px-3 py-1.5 text-sm text-muted-foreground transition hover:text-foreground"
          >
            Status
          </Link>
          <ThemeToggle />
        </nav>
      </div>
    </header>
  )
}

function AccountNav() {
  const { signedIn, user, logout, isLoading } = useAuth()
  if (isLoading) return null
  if (!signedIn) {
    return (
      <>
        <Link
          to="/login"
          className="rounded px-3 py-1.5 text-sm text-muted-foreground transition hover:text-foreground"
        >
          Sign in
        </Link>
        <Link
          to="/signup"
          className="rounded-md border border-primary px-3 py-1.5 text-sm font-medium text-primary transition hover:bg-primary hover:text-primary-foreground"
        >
          Get free account
        </Link>
      </>
    )
  }
  return (
    <>
      <Link
        to="/workspace"
        className="rounded px-3 py-1.5 text-sm text-muted-foreground transition hover:text-foreground"
        title={user?.email ?? undefined}
      >
        {user?.display_name || "Workspace"}
      </Link>
      <button
        type="button"
        onClick={() => logout()}
        className="rounded px-3 py-1.5 text-sm text-muted-foreground transition hover:text-foreground"
      >
        Sign out
      </button>
    </>
  )
}

function StatusPage() {
  return (
    <div className="container py-10">
      <h1 className="text-2xl font-semibold tracking-tight">System status</h1>
      <p className="mb-8 mt-1 text-sm text-muted-foreground">
        Ingestion health and what is currently loaded.
      </p>
      <StatusPanel />
    </div>
  )
}

function NotFound() {
  return (
    <div className="container py-20 text-center">
      <h1 className="text-xl font-semibold">Page not found</h1>
      <Link to="/" className="mt-4 inline-block text-sm text-primary hover:underline">
        Back to search
      </Link>
    </div>
  )
}

export default function App() {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Header />
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/company/:symbol" element={<CompanyPage />} />
          <Route path="/screens" element={<ScreenerPage />} />
          <Route path="/workspace" element={<WorkspacePage />} />
          <Route path="/login" element={<AuthPage mode="login" />} />
          <Route path="/signup" element={<AuthPage mode="signup" />} />
          <Route path="/status" element={<StatusPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <footer className="border-t">
        <div className="container py-6 text-xs text-muted-foreground">
          Market data from FinEdge. Figures in Rs. Crore unless stated otherwise. Not investment
          advice.
        </div>
      </footer>
    </div>
  )
}

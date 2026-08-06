import { useEffect, useState } from "react"
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom"
import { Menu, X } from "lucide-react"

import { Wordmark } from "@/components/brand"
import { ThemeToggle } from "@/components/theme-toggle"
import { ProfileMenu } from "@/components/profile-menu"
import { AdminPage } from "@/features/admin/admin-page"
import { AdminShell } from "@/features/admin/admin-shell"
import { DiagnosticsPage } from "@/features/admin/diagnostics-page"
import { PeoplePage } from "@/features/admin/people-page"
import { AuthPage } from "@/features/auth/auth-page"
import { CompanyPage } from "@/features/company/company-page"
import { IndexPage } from "@/features/indices/index-page"
import { IndicesPage } from "@/features/indices/indices-page"
import { StatusPanel } from "@/features/meta/status-panel"
import { ScreenerPage } from "@/features/screener/screener-page"
import { HomePage } from "@/features/search/home-page"
import { SearchBox } from "@/features/search/search-box"
import { SettingsPage } from "@/features/settings/settings-page"
import { WorkspacePage } from "@/features/workspace/workspace-page"
import { cn } from "@/lib/utils"

const NAV = [
  { to: "/screens", label: "Screens" },
  { to: "/indices", label: "Indices" },
  { to: "/workspace", label: "Workspace" },
]

function NavItem({
  to,
  label,
  onNavigate,
}: {
  to: string
  label: string
  onNavigate?: () => void
}) {
  return (
    <NavLink
      to={to}
      onClick={onNavigate}
      className={({ isActive }) =>
        cn(
          "rounded-md px-3 py-1.5 text-sm transition-colors",
          isActive
            ? "bg-accent font-medium text-accent-foreground"
            : "text-muted-foreground hover:text-foreground",
        )
      }
    >
      {label}
    </NavLink>
  )
}

function Header() {
  const location = useLocation()
  const onHome = location.pathname === "/"
  const [open, setOpen] = useState(false)

  // A route change should always close the drawer, however it was triggered.
  useEffect(() => setOpen(false), [location.pathname])

  return (
    <header className="sticky top-0 z-40 border-b bg-background/85 backdrop-blur-md">
      <div className="container flex h-16 items-center gap-4">
        <Link to="/" className="shrink-0">
          <Wordmark />
        </Link>

        {!onHome ? (
          <div className="hidden min-w-0 flex-1 md:block">
            <div className="max-w-sm">
              <SearchBox compact />
            </div>
          </div>
        ) : (
          <div className="flex-1" />
        )}

        <nav className="hidden shrink-0 items-center gap-1 md:flex">
          {NAV.map((item) => (
            <NavItem key={item.to} {...item} />
          ))}
          <span className="mx-1 h-5 w-px bg-border" />
          <ThemeToggle />
          <ProfileMenu />
        </nav>

        <div className="ml-auto flex items-center gap-1 md:hidden">
          <ThemeToggle />
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            className="rounded-md p-2 text-muted-foreground hover:text-foreground"
          >
            {open ? (
              <X className="h-5 w-5" aria-hidden />
            ) : (
              <Menu className="h-5 w-5" aria-hidden />
            )}
          </button>
        </div>
      </div>

      {open ? (
        <div className="border-t bg-card md:hidden">
          <div className="container space-y-3 py-4">
            {!onHome ? <SearchBox compact /> : null}
            <nav className="flex flex-col gap-1">
              {NAV.map((item) => (
                <NavItem key={item.to} {...item} onNavigate={() => setOpen(false)} />
              ))}
            </nav>
            <div className="flex flex-wrap items-center gap-2 border-t pt-3">
              <ProfileMenu />
            </div>
          </div>
        </div>
      ) : null}
    </header>
  )
}

function NotFound() {
  return (
    <div className="container py-24 text-center">
      <p className="eyebrow">404</p>
      <h1 className="mt-2 font-display text-title font-semibold">No such page</h1>
      <Link to="/" className="mt-5 inline-block text-sm text-primary hover:underline">
        Back to search
      </Link>
    </div>
  )
}

export default function App() {
  const { pathname } = useLocation()

  // Arriving at a company from a search result should start at the top.
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [pathname])

  return (
    <div className="flex min-h-screen min-w-0 flex-col overflow-x-hidden bg-background">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
      >
        Skip to content
      </a>
      <Header />
      <main id="main" className="min-w-0 flex-1">
        <Routes>
          <Route path="/" element={<HomePage />} />
          {/* Standalone at the bare path, consolidated on its own URL, so a
              company page is linkable in either form. */}
          <Route path="/company/:symbol" element={<CompanyPage />} />
          <Route path="/company/:symbol/consolidated" element={<CompanyPage />} />
          <Route path="/indices" element={<IndicesPage />} />
          <Route path="/index/:indexSymbol" element={<IndexPage />} />
          <Route path="/screens" element={<ScreenerPage />} />
          <Route path="/workspace" element={<WorkspacePage />} />
          <Route path="/login" element={<AuthPage mode="login" />} />
          <Route path="/signup" element={<AuthPage mode="signup" />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/admin" element={<AdminShell />}>
            <Route index element={<AdminPage />} />
            <Route path="people" element={<PeoplePage />} />
            <Route path="diagnostics" element={<DiagnosticsPage />} />
            <Route path="status" element={<StatusPanel />} />
          </Route>
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <footer className="mt-16 border-t">
        <div className="container flex flex-wrap items-center justify-between gap-3 py-6">
          <p className="text-micro text-muted-foreground">
            Market data from FinEdge. Figures in Rs. Crore unless stated otherwise.
          </p>
          <p className="text-micro text-muted-foreground">Not investment advice.</p>
        </div>
      </footer>
    </div>
  )
}

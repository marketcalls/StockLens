import { useEffect, useState } from "react"
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom"
import { Menu, X } from "lucide-react"

import { Wordmark } from "@/components/brand"
import { ThemeToggle } from "@/components/theme-toggle"
import { AdminPage } from "@/features/admin/admin-page"
import { PeoplePage } from "@/features/admin/people-page"
import { AuthPage } from "@/features/auth/auth-page"
import { CompanyPage } from "@/features/company/company-page"
import { IndexPage } from "@/features/indices/index-page"
import { IndicesPage } from "@/features/indices/indices-page"
import { StatusPanel } from "@/features/meta/status-panel"
import { ScreenerPage } from "@/features/screener/screener-page"
import { HomePage } from "@/features/search/home-page"
import { SearchBox } from "@/features/search/search-box"
import { WorkspacePage } from "@/features/workspace/workspace-page"
import { useAuth } from "@/providers/auth-provider"
import { cn } from "@/lib/utils"

const NAV = [
  { to: "/screens", label: "Screens" },
  { to: "/indices", label: "Indices" },
  { to: "/workspace", label: "Workspace" },
  { to: "/status", label: "Status" },
]

/** Admin links only appear for the people who can actually use them. */
function useNavItems() {
  const { limits } = useAuth()
  const items = [...NAV]
  if (limits.can_admin) items.push({ to: "/admin/people", label: "People" })
  if (limits.can_manage_platform) items.push({ to: "/admin", label: "Console" })
  return items
}

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

function AccountNav({ onNavigate }: { onNavigate?: () => void }) {
  const { signedIn, user, logout, isLoading } = useAuth()
  if (isLoading) return null

  if (!signedIn) {
    return (
      <>
        <Link
          to="/login"
          onClick={onNavigate}
          className="rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          Sign in
        </Link>
        <Link
          to="/signup"
          onClick={onNavigate}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
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
        onClick={onNavigate}
        title={user?.email ?? undefined}
        className="max-w-32 truncate rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        {user?.display_name || "Workspace"}
      </Link>
      <button
        type="button"
        onClick={() => {
          logout()
          onNavigate?.()
        }}
        className="rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        Sign out
      </button>
    </>
  )
}

function Header() {
  const location = useLocation()
  const onHome = location.pathname === "/"
  const [open, setOpen] = useState(false)
  const navItems = useNavItems()

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
          {navItems.map((item) => (
            <NavItem key={item.to} {...item} />
          ))}
          <span className="mx-1 h-5 w-px bg-border" />
          <AccountNav />
          <ThemeToggle />
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
              {navItems.map((item) => (
                <NavItem key={item.to} {...item} onNavigate={() => setOpen(false)} />
              ))}
            </nav>
            <div className="flex flex-wrap items-center gap-2 border-t pt-3">
              <AccountNav onNavigate={() => setOpen(false)} />
            </div>
          </div>
        </div>
      ) : null}
    </header>
  )
}

function StatusPage() {
  return (
    <div className="container py-8 md:py-12">
      <p className="eyebrow">Operations</p>
      <h1 className="mt-2 font-display text-title font-semibold">System status</h1>
      <p className="mb-8 mt-2 max-w-prose text-sm text-muted-foreground">
        Ingestion health and what is currently loaded.
      </p>
      <StatusPanel />
    </div>
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
          <Route path="/status" element={<StatusPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/admin/people" element={<PeoplePage />} />
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

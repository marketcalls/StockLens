import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom"

import { useAuth } from "@/providers/auth-provider"
import { cn } from "@/lib/utils"

const TABS = [
  { to: "/admin", end: true, label: "Data", hint: "Download and rebuild" },
  { to: "/admin/people", end: false, label: "People", hint: "Accounts and roles" },
  { to: "/admin/diagnostics", end: false, label: "Diagnostics", hint: "Errors and logs" },
  { to: "/admin/status", end: false, label: "Status", hint: "What is loaded" },
]

/**
 * One roof for everything administrative.
 *
 * These used to be four unrelated routes, one of them (Status) reachable by
 * anyone. Grouping them means a single access check rather than four, and a
 * single place to look when something is wrong.
 */
export function AdminShell() {
  const { limits, isLoading, signedIn } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return <p className="container py-16 text-sm text-muted-foreground">Checking your access...</p>
  }

  if (!limits.can_see_admin_area) {
    // Someone not signed in should be offered the way in; someone signed in
    // without the role should be told plainly, not sent round a loop.
    if (!signedIn) {
      return <Navigate to="/login" state={{ from: location.pathname }} replace />
    }
    return (
      <div className="container py-20">
        <p className="eyebrow mb-2">Administration</p>
        <h1 className="font-display text-title font-semibold tracking-tight">Not your area</h1>
        <p className="mt-2 max-w-lg text-sm text-muted-foreground">
          The console, accounts and diagnostics are for super administrators. If you run this
          instance, sign in with the account you created with{" "}
          <code className="font-mono text-data">stocklens-auth create-super-admin</code>.
        </p>
      </div>
    )
  }

  return (
    <div className="container min-w-0 py-6 md:py-10">
      <header className="mb-6">
        <p className="eyebrow mb-2">Super admin</p>
        <h1 className="font-display text-title font-semibold tracking-tight">Administration</h1>
      </header>

      <nav
        className="scroll-slim -mx-1 mb-6 flex gap-1 overflow-x-auto border-b px-1 pb-px"
        aria-label="Administration"
      >
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end}
            title={tab.hint}
            className={({ isActive }) =>
              cn(
                "shrink-0 border-b-2 px-3 py-2 text-sm transition-colors",
                isActive
                  ? "border-primary font-medium text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>

      <Outlet />
    </div>
  )
}

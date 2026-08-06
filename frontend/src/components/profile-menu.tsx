import { useEffect, useRef, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { LogOut, Settings, Shield, User } from "lucide-react"

import { useAuth } from "@/providers/auth-provider"
import { cn } from "@/lib/utils"

/** Initials for the avatar. Falls back to the email when there is no name. */
function initials(name: string | null, email: string): string {
  const source = (name || email.split("@")[0]).trim()
  const parts = source.split(/[\s._-]+/).filter(Boolean)
  const letters = parts.length > 1 ? parts[0][0] + parts[1][0] : source.slice(0, 2)
  return letters.toUpperCase()
}

export function ProfileMenu() {
  const { user, limits, signedIn, logout, isLoading } = useAuth()
  const [open, setOpen] = useState(false)
  const wrapper = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  // A menu that stays open after you click past it feels stuck.
  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: MouseEvent) => {
      if (!wrapper.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false)
    }
    document.addEventListener("mousedown", onPointerDown)
    document.addEventListener("keydown", onKey)
    return () => {
      document.removeEventListener("mousedown", onPointerDown)
      document.removeEventListener("keydown", onKey)
    }
  }, [open])

  if (isLoading) return null

  if (!signedIn || !user) {
    return (
      <div className="flex items-center gap-2">
        <Link
          to="/login"
          className="rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          Sign in
        </Link>
        <Link
          to="/signup"
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
        >
          Get free account
        </Link>
      </div>
    )
  }

  const item =
    "flex w-full items-center gap-2.5 rounded-md px-2.5 py-2 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground"

  return (
    <div className="relative" ref={wrapper}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={`Account: ${user.email}`}
        className={cn(
          "flex h-9 w-9 items-center justify-center rounded-full border bg-raised font-mono text-micro font-medium uppercase tracking-wider transition-colors",
          open ? "border-primary/50 text-primary" : "hover:border-primary/40 hover:text-primary",
        )}
      >
        {initials(user.display_name, user.email)}
      </button>

      {open ? (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-2 w-60 rounded-lg border bg-popover p-1.5 shadow-pop"
        >
          <div className="border-b px-2.5 pb-2.5 pt-1.5">
            <p className="truncate text-sm font-medium">{user.display_name || "Account"}</p>
            <p className="truncate text-micro text-muted-foreground">{user.email}</p>
            <p className="eyebrow mt-1.5">{user.role.replace("_", " ")}</p>
          </div>

          <div className="pt-1.5">
            <Link to="/workspace" role="menuitem" className={item} onClick={() => setOpen(false)}>
              <User className="h-4 w-4 shrink-0" aria-hidden />
              Workspace
            </Link>
            <Link to="/settings" role="menuitem" className={item} onClick={() => setOpen(false)}>
              <Settings className="h-4 w-4 shrink-0" aria-hidden />
              Settings
            </Link>

            {/* Everything administrative lives behind one door, and only a super
                administrator can see that the door is there. */}
            {limits.can_see_admin_area ? (
              <Link to="/admin" role="menuitem" className={item} onClick={() => setOpen(false)}>
                <Shield className="h-4 w-4 shrink-0" aria-hidden />
                Administration
              </Link>
            ) : null}
          </div>

          <div className="mt-1.5 border-t pt-1.5">
            <button
              type="button"
              role="menuitem"
              className={cn(item, "text-muted-foreground hover:text-loss")}
              onClick={() => {
                setOpen(false)
                logout()
                navigate("/")
              }}
            >
              <LogOut className="h-4 w-4 shrink-0" aria-hidden />
              Sign out
            </button>
          </div>
        </div>
      ) : null}
    </div>
  )
}

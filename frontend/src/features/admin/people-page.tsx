import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { ApiError, people, type ManagedUser } from "@/lib/api"
import { useAuth } from "@/providers/auth-provider"
import { cn, formatIst } from "@/lib/utils"

const ROLE_TONE: Record<string, string> = {
  super_admin: "border-primary/50 text-primary",
  admin: "border-gain/50 text-gain",
  user: "border-border text-muted-foreground",
}

function RoleTag({ role }: { role: string }) {
  return (
    <span
      className={cn(
        "rounded border px-1.5 py-0.5 font-mono text-micro uppercase tracking-wider",
        ROLE_TONE[role] ?? ROLE_TONE.user,
      )}
    >
      {role.replace("_", " ")}
    </span>
  )
}

/**
 * The rules the server enforces, stated where the choice is made.
 *
 * The server refuses these regardless, but a control that is live and then
 * errors reads as a fault. Disabling it and saying why is the honest form.
 */
export function whyLocked(
  target: ManagedUser,
  me: { id: number | null; role: string },
  superAdmins: number,
): string | null {
  if (target.id === me.id) return "You cannot change your own role or access"
  if (target.role === "super_admin" && me.role !== "super_admin") {
    return "Only a super administrator can act on another"
  }
  if (target.role === "super_admin" && target.is_active && superAdmins <= 1) {
    return "The last active super administrator. Promote another first"
  }
  return null
}

export function PeoplePage() {
  const { user: me, limits, isLoading } = useAuth()
  const client = useQueryClient()
  const [term, setTerm] = useState("")
  const [roleFilter, setRoleFilter] = useState("")
  const [open, setOpen] = useState<number | null>(null)
  const [message, setMessage] = useState<{ text: string; bad: boolean } | null>(null)
  const [handover, setHandover] = useState<{ email: string; password: string } | null>(null)
  const [inviteEmail, setInviteEmail] = useState("")
  const [inviteRole, setInviteRole] = useState("user")

  const allowed = limits.can_admin

  const listing = useQuery({
    queryKey: ["users", term, roleFilter],
    queryFn: () => people.list({ q: term, role: roleFilter }),
    enabled: allowed,
  })
  const roles = useQuery({ queryKey: ["user-roles"], queryFn: people.roles, enabled: allowed })
  const detail = useQuery({
    queryKey: ["user", open],
    queryFn: () => people.detail(open as number),
    enabled: allowed && open !== null,
  })

  const refresh = () => {
    client.invalidateQueries({ queryKey: ["users"] })
    client.invalidateQueries({ queryKey: ["user"] })
  }
  const complain = (fallback: string) => (error: unknown) =>
    setMessage({ text: error instanceof ApiError ? error.message : fallback, bad: true })

  const changeRole = useMutation({
    mutationFn: ({ id, role }: { id: number; role: string }) => people.changeRole(id, role),
    onSuccess: (result) => {
      setMessage({ text: `${result.user.email} is now ${result.user.role.replace("_", " ")}.`, bad: false })
      refresh()
    },
    onError: complain("Could not change that role."),
  })

  const setActive = useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) => people.setActive(id, active),
    onSuccess: (result) => {
      setMessage({
        text: `${result.user.email} is ${result.user.is_active ? "active" : "suspended"}.`,
        bad: false,
      })
      refresh()
    },
    onError: complain("Could not change that account."),
  })

  const invite = useMutation({
    mutationFn: () => people.invite(inviteEmail, inviteRole),
    onSuccess: (result) => {
      setHandover({ email: result.user.email, password: result.one_time_password })
      setInviteEmail("")
      setMessage(null)
      refresh()
    },
    onError: complain("Could not create that account."),
  })

  if (isLoading) {
    return <p className="container py-16 text-sm text-muted-foreground">Checking your access...</p>
  }
  if (!allowed) {
    return (
      <div className="container py-20">
        <h1 className="font-display text-title font-semibold tracking-tight">People</h1>
        <p className="mt-2 max-w-lg text-sm text-muted-foreground">
          Managing accounts requires administrator access.
        </p>
      </div>
    )
  }

  const superAdmins = listing.data?.active_super_admins ?? 0
  const actor = { id: me?.id ?? null, role: me?.role ?? "user" }

  return (
    <div className="container min-w-0 space-y-6 py-6 md:py-10">
      <header>
        <p className="eyebrow mb-2">Administration</p>
        <h1 className="font-display text-title font-semibold tracking-tight">People</h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Accounts are suspended rather than deleted, because the audit trail refers to them.
        </p>
      </header>

      {message ? (
        <div
          role="status"
          className={cn(
            "panel px-4 py-3 text-sm",
            message.bad ? "border-loss/40 text-loss" : "border-gain/40 text-gain",
          )}
        >
          {message.text}
        </div>
      ) : null}

      {handover ? (
        <section className="panel border-primary/40 p-4 sm:p-5">
          <p className="eyebrow mb-1">Hand this over now</p>
          <p className="text-sm">
            {handover.email} can sign in with this password. It is stored only as a hash, so
            nothing can show it again.
          </p>
          <p className="mt-3 select-all rounded border bg-raised px-3 py-2 font-mono text-data">
            {handover.password}
          </p>
          <button
            type="button"
            onClick={() => setHandover(null)}
            className="mt-3 rounded-md border bg-raised px-3 py-1.5 font-mono text-micro uppercase tracking-wider hover:text-primary"
          >
            I have copied it
          </button>
        </section>
      ) : null}

      <section className="panel min-w-0 p-4 sm:p-5">
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <div className="min-w-0 flex-1">
            <label htmlFor="people-filter" className="eyebrow mb-1 block">
              Find someone
            </label>
            <input
              id="people-filter"
              value={term}
              onChange={(event) => setTerm(event.target.value)}
              placeholder="Email or name"
              className="h-9 w-full min-w-0 rounded-md border bg-raised px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
          <div className="inline-flex rounded-md border bg-raised p-0.5" role="group" aria-label="Role">
            {[{ value: "", label: "All" }, ...(roles.data?.roles ?? [])].map((option) => (
              <button
                key={option.value || "all"}
                type="button"
                onClick={() => setRoleFilter(option.value)}
                aria-pressed={roleFilter === option.value}
                className={cn(
                  "rounded px-2.5 py-1 font-mono text-micro uppercase tracking-wider transition-colors",
                  roleFilter === option.value
                    ? "bg-card font-medium text-foreground shadow-tile"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        <div className="scroll-slim -mx-1 overflow-x-auto px-1">
          <table className="w-full min-w-[34rem] border-collapse text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="py-2 pr-3 font-medium text-muted-foreground">Account</th>
                <th className="py-2 px-2 font-medium text-muted-foreground">Role</th>
                <th className="hidden py-2 px-2 font-medium text-muted-foreground xs:table-cell">
                  Status
                </th>
                <th className="hidden py-2 px-2 text-right font-medium text-muted-foreground md:table-cell">
                  Owns
                </th>
                <th className="hidden py-2 px-2 text-right font-medium text-muted-foreground lg:table-cell">
                  Last seen
                </th>
                <th className="py-2 pl-2 text-right font-medium text-muted-foreground">Change</th>
              </tr>
            </thead>
            <tbody>
              {listing.data?.users.map((row) => {
                const locked = whyLocked(row, actor, superAdmins)
                return (
                  <tr key={row.id} className="border-b border-grid last:border-0">
                    <td className="py-2 pr-3">
                      <button
                        type="button"
                        onClick={() => setOpen(open === row.id ? null : row.id)}
                        className="text-left font-medium hover:text-primary hover:underline"
                      >
                        {row.display_name || row.email}
                      </button>
                      <p className="truncate text-micro text-muted-foreground">{row.email}</p>
                    </td>
                    <td className="py-2 px-2">
                      <RoleTag role={row.role} />
                    </td>
                    <td className="hidden py-2 px-2 xs:table-cell">
                      <span className={cn("text-micro", row.is_active ? "text-gain" : "text-loss")}>
                        {row.is_active ? "Active" : "Suspended"}
                      </span>
                    </td>
                    <td className="hidden py-2 px-2 text-right font-mono text-data tabular md:table-cell">
                      {row.saved_screens + row.watchlists}
                    </td>
                    <td className="hidden py-2 px-2 text-right font-mono text-micro text-muted-foreground lg:table-cell">
                      {row.last_login_at ? formatIst(row.last_login_at) : "never"}
                    </td>
                    <td className="py-2 pl-2 text-right">
                      {locked ? (
                        <span className="text-micro text-muted-foreground" title={locked}>
                          Locked
                        </span>
                      ) : (
                        <div className="inline-flex items-center gap-2">
                          <label className="sr-only" htmlFor={`role-${row.id}`}>
                            Role for {row.email}
                          </label>
                          <select
                            id={`role-${row.id}`}
                            value={row.role}
                            onChange={(event) =>
                              changeRole.mutate({ id: row.id, role: event.target.value })
                            }
                            className="h-8 rounded-md border bg-raised px-2 font-mono text-micro uppercase tracking-wider outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          >
                            {(roles.data?.roles ?? []).map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            onClick={() =>
                              setActive.mutate({ id: row.id, active: !row.is_active })
                            }
                            className="rounded-md border bg-raised px-2 py-1 font-mono text-micro uppercase tracking-wider transition-colors hover:text-loss"
                          >
                            {row.is_active ? "Suspend" : "Restore"}
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        {listing.data && listing.data.users.length === 0 ? (
          <p className="py-6 text-sm text-muted-foreground">No account matches that.</p>
        ) : null}
      </section>

      {open !== null && detail.data ? (
        <section className="panel min-w-0 p-4 sm:p-5">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="eyebrow mb-1">{detail.data.user.email}</p>
              <h2 className="font-display text-lg font-semibold tracking-tight sm:text-xl">
                History
              </h2>
            </div>
            <p className="font-mono text-micro uppercase tracking-wider text-muted-foreground">
              {detail.data.saved_screens.length} screens · {detail.data.watchlists.length} lists ·
              joined {formatIst(detail.data.user.created_at)}
            </p>
          </div>
          {detail.data.audit.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing recorded yet.</p>
          ) : (
            <ul className="space-y-1.5">
              {detail.data.audit.map((entry) => (
                <li key={entry.id} className="flex flex-wrap items-baseline gap-x-3 text-sm">
                  <span className="font-mono text-micro text-muted-foreground">
                    {formatIst(entry.created_at)}
                  </span>
                  <span className="font-mono text-data">{entry.action}</span>
                  {entry.detail ? (
                    <span className="text-micro text-muted-foreground">{entry.detail}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}

      <section className="panel min-w-0 p-4 sm:p-5">
        <h2 className="mb-1 font-display text-lg font-semibold tracking-tight sm:text-xl">
          Add someone
        </h2>
        <p className="mb-4 text-sm text-muted-foreground">
          There is no mail server in a self-hosted install, so you get a password to hand over
          yourself. It is shown once.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-0 flex-1">
            <label htmlFor="invite-email" className="eyebrow mb-1 block">
              Email
            </label>
            <input
              id="invite-email"
              value={inviteEmail}
              onChange={(event) => setInviteEmail(event.target.value)}
              placeholder="analyst@yourdomain.com"
              className="h-9 w-full min-w-0 rounded-md border bg-raised px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
          <div>
            <label htmlFor="invite-role" className="eyebrow mb-1 block">
              Role
            </label>
            <select
              id="invite-role"
              value={inviteRole}
              onChange={(event) => setInviteRole(event.target.value)}
              className="h-9 rounded-md border bg-raised px-2 font-mono text-micro uppercase tracking-wider outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {(roles.data?.roles ?? []).map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={() => invite.mutate()}
            disabled={!inviteEmail.trim() || invite.isPending}
            className="h-9 rounded-md border border-primary/50 px-3 font-mono text-micro uppercase tracking-wider text-primary transition-colors hover:bg-primary hover:text-primary-foreground disabled:cursor-not-allowed disabled:opacity-40"
          >
            {invite.isPending ? "Creating..." : "Create account"}
          </button>
        </div>
      </section>
    </div>
  )
}

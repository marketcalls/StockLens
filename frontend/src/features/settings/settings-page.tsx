import { useState } from "react"
import { Link } from "react-router-dom"
import { useMutation } from "@tanstack/react-query"

import { ApiError, auth } from "@/lib/api"
import { useAuth } from "@/providers/auth-provider"
import { cn, formatIst } from "@/lib/utils"

/** Matches the server's rule. Stated here so the form can say it before you submit. */
const MIN_PASSWORD_LENGTH = 10

export function SettingsPage() {
  const { user, signedIn, isLoading } = useAuth()
  const [current, setCurrent] = useState("")
  const [next, setNext] = useState("")
  const [confirm, setConfirm] = useState("")
  const [message, setMessage] = useState<{ text: string; bad: boolean } | null>(null)

  const change = useMutation({
    mutationFn: () => auth.changePassword(current, next),
    onSuccess: () => {
      setMessage({ text: "Password changed. Your session stays signed in.", bad: false })
      setCurrent("")
      setNext("")
      setConfirm("")
    },
    onError: (error) =>
      setMessage({
        text: error instanceof ApiError ? error.message : "Could not change the password.",
        bad: true,
      }),
  })

  if (isLoading) {
    return <p className="container py-16 text-sm text-muted-foreground">Loading...</p>
  }
  if (!signedIn || !user) {
    return (
      <div className="container py-20">
        <h1 className="font-display text-title font-semibold tracking-tight">Settings</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          <Link to="/login" className="text-primary hover:underline">
            Sign in
          </Link>{" "}
          to change your account.
        </p>
      </div>
    )
  }

  // Checked here only to explain the problem next to the field. The server
  // enforces all of it again, and its answer is the one that counts.
  const tooShort = next.length > 0 && next.length < MIN_PASSWORD_LENGTH
  const mismatch = confirm.length > 0 && next !== confirm
  const ready = current.length > 0 && next.length >= MIN_PASSWORD_LENGTH && next === confirm

  const field =
    "h-9 w-full min-w-0 rounded-md border bg-raised px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"

  return (
    <div className="container min-w-0 max-w-2xl space-y-6 py-6 md:py-10">
      <header>
        <p className="eyebrow mb-2">Account</p>
        <h1 className="font-display text-title font-semibold tracking-tight">Settings</h1>
      </header>

      <section className="panel min-w-0 p-4 sm:p-5">
        <h2 className="mb-4 font-display text-lg font-semibold tracking-tight">Your account</h2>
        <dl className="grid grid-cols-2 gap-4">
          <div>
            <dt className="eyebrow mb-0.5">Email</dt>
            <dd className="truncate text-sm">{user.email}</dd>
          </div>
          <div>
            <dt className="eyebrow mb-0.5">Name</dt>
            <dd className="truncate text-sm">{user.display_name || "—"}</dd>
          </div>
          <div>
            <dt className="eyebrow mb-0.5">Role</dt>
            <dd className="text-sm">{user.role.replace("_", " ")}</dd>
          </div>
          <div>
            <dt className="eyebrow mb-0.5">Joined</dt>
            <dd className="text-sm">{formatIst(user.created_at)}</dd>
          </div>
        </dl>
      </section>

      <section className="panel min-w-0 p-4 sm:p-5">
        <h2 className="mb-1 font-display text-lg font-semibold tracking-tight">Change password</h2>
        <p className="mb-4 text-sm text-muted-foreground">
          At least {MIN_PASSWORD_LENGTH} characters. There are no composition rules — length is
          what makes a password hard to guess.
        </p>

        {message ? (
          <p
            role="status"
            className={cn("mb-4 text-sm", message.bad ? "text-loss" : "text-gain")}
          >
            {message.text}
          </p>
        ) : null}

        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (ready) change.mutate()
          }}
        >
          <div>
            <label htmlFor="current-password" className="eyebrow mb-1 block">
              Current password
            </label>
            <input
              id="current-password"
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(event) => setCurrent(event.target.value)}
              className={field}
            />
          </div>
          <div>
            <label htmlFor="new-password" className="eyebrow mb-1 block">
              New password
            </label>
            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(event) => setNext(event.target.value)}
              aria-invalid={tooShort}
              className={cn(field, tooShort && "border-loss/60")}
            />
            {tooShort ? (
              <p className="mt-1 text-micro text-loss">
                {MIN_PASSWORD_LENGTH - next.length} more character
                {MIN_PASSWORD_LENGTH - next.length === 1 ? "" : "s"} needed
              </p>
            ) : null}
          </div>
          <div>
            <label htmlFor="confirm-password" className="eyebrow mb-1 block">
              New password again
            </label>
            <input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              aria-invalid={mismatch}
              className={cn(field, mismatch && "border-loss/60")}
            />
            {mismatch ? (
              <p className="mt-1 text-micro text-loss">These do not match</p>
            ) : null}
          </div>

          <button
            type="submit"
            disabled={!ready || change.isPending}
            className="h-9 rounded-md border border-primary/50 px-3 font-mono text-micro uppercase tracking-wider text-primary transition-colors hover:bg-primary hover:text-primary-foreground disabled:cursor-not-allowed disabled:opacity-40"
          >
            {change.isPending ? "Changing..." : "Change password"}
          </button>
        </form>
      </section>
    </div>
  )
}

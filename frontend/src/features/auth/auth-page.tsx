import { useState } from "react"
import { Link, useNavigate, useSearchParams } from "react-router-dom"

import { ApiError } from "@/lib/api"
import { useAuth } from "@/providers/auth-provider"
import { cn } from "@/lib/utils"

const MIN_PASSWORD = 10

export function AuthPage({ mode }: { mode: "login" | "signup" }) {
  const { login, signup } = useAuth()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = params.get("next") || "/screens"

  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const signingUp = mode === "signup"
  const tooShort = signingUp && password.length > 0 && password.length < MIN_PASSWORD

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      if (signingUp) await signup(email, password)
      else await login(email, password)
      navigate(next, { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="container flex min-h-[70vh] items-center justify-center py-12">
      <div className="w-full max-w-sm">
        <h1 className="font-display text-title font-semibold">
          {signingUp ? "Create your account" : "Sign in"}
        </h1>
        <p className="mb-6 mt-1 text-sm text-muted-foreground">
          {signingUp
            ? "Free. Save screens, keep watchlists and export results."
            : "Welcome back."}
        </p>

        <form onSubmit={submit} className="space-y-4" noValidate>
          <div>
            <label htmlFor="email" className="mb-1 block text-sm font-medium">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="h-10 w-full rounded-md border bg-card px-3 text-sm outline-none ring-offset-background transition focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>

          <div>
            <label htmlFor="password" className="mb-1 block text-sm font-medium">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete={signingUp ? "new-password" : "current-password"}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-describedby="password-hint"
              className={cn(
                "h-10 w-full rounded-md border bg-card px-3 text-sm outline-none ring-offset-background transition focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring",
                tooShort && "border-loss",
              )}
            />
            {signingUp ? (
              <p
                id="password-hint"
                className={cn("mt-1 text-xs", tooShort ? "text-loss" : "text-muted-foreground")}
              >
                At least {MIN_PASSWORD} characters. A short sentence works well.
              </p>
            ) : null}
          </div>

          {error ? (
            <p role="alert" className="text-sm text-loss">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={busy || !email || !password || tooShort}
            className="h-10 w-full rounded-md bg-primary text-sm font-medium text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
          >
            {busy ? "Please wait..." : signingUp ? "Create account" : "Sign in"}
          </button>
        </form>

        <p className="mt-6 text-sm text-muted-foreground">
          {signingUp ? (
            <>
              Already have an account?{" "}
              <Link to="/login" className="text-primary hover:underline">
                Sign in
              </Link>
            </>
          ) : (
            <>
              No account?{" "}
              <Link to="/signup" className="text-primary hover:underline">
                Create one
              </Link>
            </>
          )}
        </p>
      </div>
    </div>
  )
}

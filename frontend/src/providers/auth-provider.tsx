import { createContext, useContext, useMemo } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { auth, type AuthUser, type Limits, type Session } from "@/lib/api"

/**
 * Session state.
 *
 * The limits come from the server rather than being duplicated here. The client
 * uses them to decide what to *offer*; the server decides what to *allow*. If
 * the two ever disagree the server wins, which is why nothing here is a
 * security boundary.
 */

const ANONYMOUS_LIMITS: Limits = {
  screener_row_cap: 25,
  screener_rows_unlimited: false,
  export_row_limit: 0,
  can_save_screens: false,
  can_use_watchlists: false,
  can_export: false,
  can_admin: false,
  can_manage_platform: false,
}

type AuthState = {
  user: AuthUser | null
  limits: Limits
  isLoading: boolean
  signedIn: boolean
  login: (email: string, password: string) => Promise<void>
  signup: (email: string, password: string, displayName?: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient()

  const session = useQuery<Session>({
    queryKey: ["session"],
    queryFn: auth.me,
    staleTime: 60_000,
    retry: false,
  })

  // Anything that depends on who is signed in must be refetched on a change:
  // the screener row cap, saved screens, watchlists.
  const invalidateAll = () => queryClient.invalidateQueries()

  const loginMutation = useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      auth.login(email, password),
    onSuccess: invalidateAll,
  })

  const signupMutation = useMutation({
    mutationFn: ({
      email,
      password,
      displayName,
    }: {
      email: string
      password: string
      displayName?: string
    }) => auth.signup(email, password, displayName),
    onSuccess: invalidateAll,
  })

  const logoutMutation = useMutation({
    mutationFn: auth.logout,
    onSuccess: invalidateAll,
  })

  const value = useMemo<AuthState>(
    () => ({
      user: session.data?.user ?? null,
      limits: session.data?.limits ?? ANONYMOUS_LIMITS,
      isLoading: session.isPending,
      signedIn: Boolean(session.data?.user),
      login: async (email, password) => {
        await loginMutation.mutateAsync({ email, password })
      },
      signup: async (email, password, displayName) => {
        await signupMutation.mutateAsync({ email, password, displayName })
      },
      logout: async () => {
        await logoutMutation.mutateAsync()
      },
    }),
    [session.data, session.isPending, loginMutation, signupMutation, logoutMutation],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (!context) throw new Error("useAuth must be used within an AuthProvider")
  return context
}

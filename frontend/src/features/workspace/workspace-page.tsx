import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Trash2 } from "lucide-react"

import { workspace } from "@/lib/api"
import { useAuth } from "@/providers/auth-provider"
import { formatIst } from "@/lib/utils"

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="panel p-5">
      <h2 className="mb-4 font-display text-lg font-semibold tracking-tight">{title}</h2>
      {children}
    </section>
  )
}

export function WorkspacePage() {
  const { signedIn, isLoading, user } = useAuth()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [listName, setListName] = useState("")

  const screens = useQuery({
    queryKey: ["saved-screens"],
    queryFn: workspace.screens,
    enabled: signedIn,
  })
  const lists = useQuery({
    queryKey: ["watchlists"],
    queryFn: workspace.watchlists,
    enabled: signedIn,
  })

  const removeScreen = useMutation({
    mutationFn: workspace.deleteScreen,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["saved-screens"] }),
  })
  const addList = useMutation({
    mutationFn: workspace.createWatchlist,
    onSuccess: () => {
      setListName("")
      queryClient.invalidateQueries({ queryKey: ["watchlists"] })
    },
  })
  const removeList = useMutation({
    mutationFn: workspace.deleteWatchlist,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["watchlists"] }),
  })
  const removeSymbol = useMutation({
    mutationFn: ({ id, symbol }: { id: number; symbol: string }) =>
      workspace.removeSymbol(id, symbol),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["watchlists"] }),
  })

  if (isLoading) {
    return <div className="container py-16 text-sm text-muted-foreground">Loading...</div>
  }

  if (!signedIn) {
    return (
      <div className="container py-20 text-center">
        <h1 className="font-display text-title font-semibold">Your saved work lives here</h1>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
          Screens you save and companies you follow. Free to create an account.
        </p>
        <Link
          to="/signup?next=/workspace"
          className="mt-5 inline-block rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          Create an account
        </Link>
      </div>
    )
  }

  return (
    <div className="container space-y-5 py-6 md:py-10">
      <div>
        <p className="eyebrow">Saved</p>
        <h1 className="mt-2 font-display text-title font-semibold">Your workspace</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Signed in as {user?.email}
        </p>
      </div>

      <Card title="Saved screens">
        {screens.data?.screens.length ? (
          <ul className="divide-y">
            {screens.data.screens.map((screen) => (
              <li key={screen.id} className="flex items-start justify-between gap-4 py-3">
                <div className="min-w-0">
                  <button
                    type="button"
                    onClick={() =>
                      navigate(`/screens?q=${encodeURIComponent(screen.query)}`)
                    }
                    className="text-left text-sm font-medium text-primary hover:underline"
                  >
                    {screen.name}
                  </button>
                  <p className="truncate font-mono text-xs text-muted-foreground">
                    {screen.query}
                  </p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Updated {formatIst(screen.updated_at)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => removeScreen.mutate(screen.id)}
                  aria-label={`Delete ${screen.name}`}
                  className="shrink-0 rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-loss"
                >
                  <Trash2 className="h-4 w-4" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            No saved screens yet. Run a query on the{" "}
            <Link to="/screens" className="text-primary hover:underline">
              screener
            </Link>{" "}
            and save it.
          </p>
        )}
      </Card>

      <Card title="Watchlists">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (listName.trim()) addList.mutate(listName.trim())
          }}
          className="mb-4 flex gap-2"
        >
          <input
            value={listName}
            onChange={(e) => setListName(e.target.value)}
            placeholder="New list name"
            aria-label="New watchlist name"
            className="h-9 flex-1 rounded-md border bg-background px-3 text-sm outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-ring"
          />
          <button
            type="submit"
            disabled={!listName.trim() || addList.isPending}
            className="rounded-md border px-3 text-sm font-medium transition hover:border-primary disabled:opacity-50"
          >
            Create
          </button>
        </form>
        {addList.isError ? (
          <p role="alert" className="mb-3 text-sm text-loss">
            {(addList.error as Error).message}
          </p>
        ) : null}

        {lists.data?.watchlists.length ? (
          <ul className="space-y-4">
            {lists.data.watchlists.map((list) => (
              <li key={list.id}>
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium">{list.name}</h3>
                  <button
                    type="button"
                    onClick={() => removeList.mutate(list.id)}
                    aria-label={`Delete ${list.name}`}
                    className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-loss"
                  >
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </button>
                </div>
                {list.items.length ? (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {list.items.map((item) => (
                      <span
                        key={item.symbol}
                        className="inline-flex items-center gap-1 rounded border bg-secondary px-2 py-0.5 text-xs"
                      >
                        <Link
                          to={`/company/${item.symbol}`}
                          className="text-primary hover:underline"
                        >
                          {item.symbol}
                        </Link>
                        <button
                          type="button"
                          onClick={() =>
                            removeSymbol.mutate({ id: list.id, symbol: item.symbol })
                          }
                          aria-label={`Remove ${item.symbol}`}
                          className="text-muted-foreground hover:text-loss"
                        >
                          &times;
                        </button>
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="mt-1 text-xs text-muted-foreground">
                    Empty. Add companies from their page.
                  </p>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">No watchlists yet.</p>
        )}
      </Card>
    </div>
  )
}

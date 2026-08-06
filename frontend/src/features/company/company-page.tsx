import { Link, useLocation, useParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

import { StatementTable } from "@/components/statement-table"
import { RangeTrack } from "@/components/trend-rail"
import { api, type SeriesResponse } from "@/lib/api"
import { cn, formatCrore, formatIst, formatPercent } from "@/lib/utils"

function Section({
  title,
  eyebrow,
  action,
  children,
}: {
  title: string
  eyebrow?: string
  action?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section className="panel min-w-0 p-4 sm:p-5">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          {eyebrow ? <p className="eyebrow mb-1">{eyebrow}</p> : null}
          <h2 className="font-display text-lg font-semibold tracking-tight sm:text-xl">
            {title}
          </h2>
        </div>
        {action}
      </div>
      {children}
    </section>
  )
}

function StatementSwitch({
  symbol,
  consolidated,
}: {
  symbol: string
  consolidated: boolean
}) {
  const options = [
    { to: `/company/${symbol}`, label: "Standalone", active: !consolidated },
    { to: `/company/${symbol}/consolidated`, label: "Consolidated", active: consolidated },
  ]
  return (
    <div
      className="inline-flex rounded-md border bg-raised p-0.5"
      role="group"
      aria-label="Figures"
    >
      {options.map((option) => (
        <Link
          key={option.label}
          to={option.to}
          aria-current={option.active ? "page" : undefined}
          className={cn(
            "rounded px-2.5 py-1 font-mono text-micro uppercase tracking-wider transition-colors",
            option.active
              ? "bg-card font-medium text-foreground shadow-tile"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {option.label}
        </Link>
      ))}
    </div>
  )
}

function SeriesTable({ data }: { data: SeriesResponse | undefined }) {
  if (!data?.available) {
    return <p className="py-6 text-sm text-muted-foreground">Not available yet.</p>
  }
  return (
    <StatementTable
      headers={data.headers}
      rows={data.rows.map((r) => ({ ...r, emphasis: false, children: [] }))}
    />
  )
}

const SCHEMA_LABEL: Record<string, string> = {
  general: "Standard reporting",
  bank: "Bank reporting",
  life_insurance: "Life insurance reporting",
  general_insurance: "General insurance reporting",
}

/** A readout tile. Label above, figure below, mono throughout. */
function Readout({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-card px-3 py-2.5 sm:px-4 sm:py-3">
      <div className="eyebrow truncate">{label}</div>
      <div className="tabular mt-1 font-mono text-sm font-medium sm:text-base">{value}</div>
    </div>
  )
}

export function CompanyPage() {
  const { symbol = "" } = useParams()
  const upper = symbol.toUpperCase()
  // The URL decides which set of figures is shown, so either view can be
  // linked to and shared: /company/RELIANCE is standalone,
  // /company/RELIANCE/consolidated is consolidated.
  const consolidated = useLocation().pathname.endsWith("/consolidated")
  const statementType: "c" | "s" = consolidated ? "c" : "s"

  const company = useQuery({ queryKey: ["company", upper], queryFn: () => api.company(upper) })
  const quarterly = useQuery({
    queryKey: ["stmt", upper, "pl", "quarterly", statementType],
    queryFn: () => api.statements(upper, "pl", "quarterly", statementType),
  })
  const annual = useQuery({
    queryKey: ["stmt", upper, "pl", "annual", statementType],
    queryFn: () => api.statements(upper, "pl", "annual", statementType),
  })
  const balance = useQuery({
    queryKey: ["stmt", upper, "bs", "annual", statementType],
    queryFn: () => api.statements(upper, "bs", "annual", statementType),
  })
  const cash = useQuery({
    queryKey: ["stmt", upper, "cf", "annual", statementType],
    queryFn: () => api.statements(upper, "cf", "annual", statementType),
  })
  const ratios = useQuery({
    queryKey: ["ratios", upper, "ef"],
    queryFn: () => api.ratios(upper, "ef"),
  })
  const holding = useQuery({
    queryKey: ["holding", upper],
    queryFn: () => api.shareholding(upper),
  })
  const peers = useQuery({ queryKey: ["peers", upper], queryFn: () => api.peers(upper) })
  const prices = useQuery({
    queryKey: ["prices", upper],
    queryFn: () => api.prices(upper, 1300),
  })

  if (company.isError) {
    return (
      <div className="container py-24 text-center">
        <p className="eyebrow">Not found</p>
        <h1 className="mt-2 font-display text-title font-semibold">
          No company called {upper}
        </h1>
        <Link to="/" className="mt-5 inline-block text-sm text-primary hover:underline">
          Back to search
        </Link>
      </div>
    )
  }

  if (!company.data) {
    return (
      <div className="container py-24">
        <div className="max-w-md space-y-3">
          <div className="h-3 w-24 animate-pulse rounded bg-muted" />
          <div className="h-10 w-72 animate-pulse rounded bg-muted" />
          <div className="h-3 w-48 animate-pulse rounded bg-muted" />
        </div>
      </div>
    )
  }

  const c = company.data
  const q = c.quote
  const k = c.key_ratios
  const cls = c.classification
  const breadcrumb = [cls.macro_sector, cls.industry, cls.sector, cls.sub_industry].filter(
    (v, i, arr) => v && arr.indexOf(v) === i,
  )

  const chartData = (prices.data?.prices ?? []).map((p) => ({
    date: p.quote_date,
    close: p.close,
  }))

  // The API falls back to the other set when the requested one is absent -
  // only 2,510 of 5,630 companies file consolidated statements - and reports
  // which it actually used. Label what is on screen, not what was asked for.
  const shown = quarterly.data?.statement_type ?? statementType
  const fellBack = Boolean(quarterly.data) && shown !== statementType
  const statementNote =
    (shown === "s" ? "Standalone figures in Rs. Crore" : "Consolidated figures in Rs. Crore") +
    (fellBack
      ? shown === "s"
        ? " · no consolidated statements filed"
        : " · no standalone statements filed"
      : "")

  const readouts: [string, string][] = [
    ["Market cap", q?.market_cap != null ? `₹${formatCrore(q.market_cap, 0)} Cr` : "—"],
    ["Stock P/E", k.pe != null ? k.pe.toFixed(2) : "—"],
    ["Book value", k.book_value != null ? `₹${k.book_value.toFixed(2)}` : "—"],
    ["Dividend yield", k.dividend_yield != null ? formatPercent(k.dividend_yield) : "—"],
    ["ROCE", k.roce3yearsavg != null ? formatPercent(k.roce3yearsavg) : "—"],
    ["ROE", k.returnonequity != null ? formatPercent(k.returnonequity) : "—"],
    ["Debt / equity", k.totaldebttoequity != null ? k.totaldebttoequity.toFixed(2) : "—"],
    ["EV / EBITDA", k.ev_ebitda != null ? k.ev_ebitda.toFixed(2) : "—"],
    ["Promoter", k.promoter_holding != null ? formatPercent(k.promoter_holding) : "—"],
    ["10Y return", k.price_cagr_10y != null ? formatPercent(k.price_cagr_10y, 1) : "—"],
  ]

  return (
    <div className="container min-w-0 space-y-4 py-6 md:py-10">
      {/* Hero. The price is what people came for, so it gets the scale. */}
      <header className="animate-fade-up">
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
              <span className="eyebrow">{c.symbol}</span>
              {c.nse_code ? <span className="eyebrow">NSE</span> : null}
              {c.bse_code ? <span className="eyebrow">BSE</span> : null}
              {c.schema_kind ? (
                <span className="eyebrow rounded border px-1.5 py-0.5">
                  {SCHEMA_LABEL[c.schema_kind] ?? c.schema_kind}
                </span>
              ) : null}
            </div>

            <h1 className="mt-2 font-display text-title font-semibold">{c.name}</h1>

            {breadcrumb.length ? (
              <nav aria-label="Sector" className="mt-2.5 flex flex-wrap items-center gap-1.5">
                {breadcrumb.map((part, i) => (
                  <span key={part} className="flex items-center gap-1.5">
                    {i > 0 ? <span className="text-muted-foreground/40">/</span> : null}
                    <span className="text-micro text-muted-foreground">{part}</span>
                  </span>
                ))}
              </nav>
            ) : null}
          </div>

          <div className="shrink-0 lg:text-right">
            <div className="tabular font-display text-hero font-semibold leading-none">
              {q?.current_price != null ? `₹${q.current_price.toFixed(2)}` : "—"}
            </div>
            {q?.change_pct != null ? (
              <div
                className={cn(
                  "tabular mt-2 font-mono text-sm font-medium",
                  q.change_pct >= 0 ? "text-gain" : "text-loss",
                )}
              >
                {q.change_pct >= 0 ? "▲" : "▼"} {q.change_pct >= 0 ? "+" : ""}
                {q.change_pct.toFixed(2)}%
              </div>
            ) : null}
            {q?.trade_time ? <div className="eyebrow mt-1">{formatIst(q.trade_time)}</div> : null}

            {q?.high52 != null && q?.low52 != null && q?.current_price != null ? (
              <div className="mt-4 w-full lg:w-64">
                <RangeTrack low={q.low52} high={q.high52} current={q.current_price} />
              </div>
            ) : null}
          </div>
        </div>

        {c.indices.length ? (
          <div className="mt-5 flex flex-wrap items-center gap-1.5">
            <span className="eyebrow mr-1">Part of</span>
            {c.indices.slice(0, 5).map((index) => (
              <span
                key={index.symbol}
                className="rounded border bg-raised px-2 py-0.5 text-micro text-muted-foreground"
              >
                {index.name}
              </span>
            ))}
            {c.indices.length > 5 ? (
              <span className="text-micro text-muted-foreground">+{c.indices.length - 5}</span>
            ) : null}
          </div>
        ) : null}
      </header>

      {/* Readout strip. Ten figures, mono, one grid. */}
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-3 lg:grid-cols-5">
        {readouts.map(([label, value]) => (
          <Readout key={label} label={label} value={value} />
        ))}
      </div>

      {c.description ? (
        <p className="max-w-prose pt-1 text-sm leading-relaxed text-muted-foreground">
          {c.description}
        </p>
      ) : null}

      {chartData.length > 1 ? (
        <Section title="Price" eyebrow="Daily close">
          <div className="h-52 w-full sm:h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.28} />
                    <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11, fontFamily: "ui-monospace, monospace" }}
                  stroke="hsl(var(--muted-foreground))"
                  minTickGap={64}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(d: string) => d.slice(0, 7)}
                />
                <YAxis
                  tick={{ fontSize: 11, fontFamily: "ui-monospace, monospace" }}
                  stroke="hsl(var(--muted-foreground))"
                  domain={["auto", "auto"]}
                  width={52}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: "hsl(var(--popover))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: 8,
                    fontSize: 12,
                    fontFamily: "ui-monospace, monospace",
                    color: "hsl(var(--popover-foreground))",
                    boxShadow: "var(--shadow-pop)",
                  }}
                  formatter={(v) => [typeof v === "number" ? `₹${v.toFixed(2)}` : "—", "Close"]}
                />
                <Area
                  type="monotone"
                  dataKey="close"
                  stroke="hsl(var(--primary))"
                  strokeWidth={1.5}
                  fill="url(#priceFill)"
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Section>
      ) : null}

      <Section
        title="Quarterly results"
        eyebrow="Profit and loss"
        action={<StatementSwitch symbol={upper} consolidated={consolidated} />}
      >
        <StatementTable
          headers={quarterly.data?.headers ?? []}
          rows={quarterly.data?.rows ?? []}
          note={statementNote}
        />
      </Section>

      <Section title="Profit and loss" eyebrow="Annual">
        <StatementTable
          headers={annual.data?.headers ?? []}
          rows={annual.data?.rows ?? []}
          note={statementNote}
        />
      </Section>

      <Section title="Balance sheet" eyebrow="Annual">
        <StatementTable
          headers={balance.data?.headers ?? []}
          rows={balance.data?.rows ?? []}
          note={statementNote}
        />
      </Section>

      <Section title="Cash flows" eyebrow="Annual">
        <StatementTable
          headers={cash.data?.headers ?? []}
          rows={cash.data?.rows ?? []}
          note={statementNote}
        />
      </Section>

      <Section title="Ratios" eyebrow="Working capital">
        <SeriesTable data={ratios.data} />
      </Section>

      <Section title="Shareholding" eyebrow="By quarter">
        <SeriesTable data={holding.data} />
      </Section>

      <Section title="Peer comparison" eyebrow={peers.data?.group ?? undefined}>
        {peers.data?.peers.length ? (
          <div className="scroll-slim min-w-0 overflow-x-auto rounded-md border">
            <table className="w-full min-w-max">
              <thead>
                <tr className="border-b bg-raised text-left">
                  <th className="eyebrow px-3 py-2.5">Name</th>
                  <th className="eyebrow px-3 py-2.5 text-right">CMP</th>
                  <th className="eyebrow px-3 py-2.5 text-right">P/E</th>
                  <th className="eyebrow px-3 py-2.5 text-right">Mar cap</th>
                  <th className="eyebrow px-3 py-2.5 text-right">Div yld</th>
                  <th className="eyebrow px-3 py-2.5 text-right">ROE</th>
                </tr>
              </thead>
              <tbody>
                {peers.data.peers.map((peer) => (
                  <tr
                    key={peer.symbol}
                    className={cn(
                      "border-b border-grid last:border-0 hover:bg-accent/40",
                      peer.symbol === upper && "bg-accent/60",
                    )}
                  >
                    <td className="px-3 py-2 text-data">
                      <Link
                        to={`/company/${peer.symbol}`}
                        className={cn(
                          "hover:underline",
                          peer.symbol === upper ? "font-semibold" : "text-primary",
                        )}
                      >
                        {peer.name}
                      </Link>
                    </td>
                    <td className="tabular px-3 py-2 text-right font-mono text-data">
                      {peer.current_price?.toFixed(2) ?? "—"}
                    </td>
                    <td className="tabular px-3 py-2 text-right font-mono text-data">
                      {peer.pe?.toFixed(2) ?? "—"}
                    </td>
                    <td className="tabular px-3 py-2 text-right font-mono text-data">
                      {peer.market_cap != null ? formatCrore(peer.market_cap, 0) : "—"}
                    </td>
                    <td className="tabular px-3 py-2 text-right font-mono text-data">
                      {peer.dividend_yield?.toFixed(2) ?? "—"}
                    </td>
                    <td className="tabular px-3 py-2 text-right font-mono text-data">
                      {peer.returnonequity?.toFixed(2) ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            Peers appear once more companies in {peers.data?.group ?? "this sector"} are loaded.
          </p>
        )}
      </Section>
    </div>
  )
}

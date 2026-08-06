import { useState } from "react"
import { Link, useParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { StatementTable } from "@/components/statement-table"
import { api, type SeriesResponse } from "@/lib/api"
import { cn, formatCrore, formatIst, formatPercent } from "@/lib/utils"

function Section({
  title,
  action,
  children,
}: {
  title: string
  action?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section className="rounded-lg border bg-card p-5 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  )
}

function Toggle<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <div className="inline-flex rounded-md border p-0.5" role="group">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          aria-pressed={value === option.value}
          className={cn(
            "rounded px-3 py-1 text-xs font-medium transition",
            value === option.value
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

function SeriesTable({ data }: { data: SeriesResponse | undefined }) {
  if (!data?.available) {
    return <p className="py-4 text-sm text-muted-foreground">Not available yet.</p>
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

export function CompanyPage() {
  const { symbol = "" } = useParams()
  const upper = symbol.toUpperCase()
  const [statementType, setStatementType] = useState<"c" | "s">("c")

  const company = useQuery({
    queryKey: ["company", upper],
    queryFn: () => api.company(upper),
  })
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
      <div className="container py-16 text-center">
        <h1 className="text-xl font-semibold">Company not found</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          No company with the symbol {upper}.
        </p>
        <Link to="/" className="mt-4 inline-block text-sm text-primary hover:underline">
          Back to search
        </Link>
      </div>
    )
  }

  if (!company.data) {
    return <div className="container py-16 text-sm text-muted-foreground">Loading {upper}...</div>
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

  const statementNote =
    quarterly.data?.statement_type === "s"
      ? "Standalone figures in Rs. Crore"
      : "Consolidated figures in Rs. Crore"

  return (
    <div className="container space-y-5 py-8">
      {/* Header */}
      <section className="rounded-lg border bg-card p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-tight">{c.name}</h1>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span className="font-mono">{c.symbol}</span>
              {c.nse_code ? <span>NSE: {c.nse_code}</span> : null}
              {c.bse_code ? <span>BSE: {c.bse_code}</span> : null}
              {c.website ? (
                <a
                  href={`https://${c.website.replace(/^https?:\/\//, "")}`}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-primary hover:underline"
                >
                  {c.website}
                </a>
              ) : null}
            </div>
            {breadcrumb.length ? (
              <nav aria-label="Sector" className="mt-3 flex flex-wrap items-center gap-1 text-xs">
                {breadcrumb.map((part, i) => (
                  <span key={part} className="flex items-center gap-1">
                    {i > 0 ? <span className="text-muted-foreground">/</span> : null}
                    <span className="text-muted-foreground">{part}</span>
                  </span>
                ))}
              </nav>
            ) : null}
          </div>

          <div className="text-right">
            <div className="tabular text-3xl font-semibold">
              {q?.current_price != null ? `₹${q.current_price.toFixed(2)}` : "-"}
            </div>
            {q?.change_pct != null ? (
              <div
                className={cn(
                  "tabular text-sm font-medium",
                  q.change_pct >= 0 ? "text-gain" : "text-loss",
                )}
              >
                {q.change_pct >= 0 ? "+" : ""}
                {q.change_pct.toFixed(2)}%
              </div>
            ) : null}
            {q?.trade_time ? (
              <div className="mt-1 text-xs text-muted-foreground">{formatIst(q.trade_time)}</div>
            ) : null}
          </div>
        </div>

        {c.indices.length ? (
          <div className="mt-4 flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-muted-foreground">Part of</span>
            {c.indices.slice(0, 6).map((index) => (
              <span
                key={index.symbol}
                className="rounded border bg-secondary px-2 py-0.5 text-xs text-secondary-foreground"
              >
                {index.name}
              </span>
            ))}
            {c.indices.length > 6 ? (
              <span className="text-xs text-muted-foreground">
                +{c.indices.length - 6} more
              </span>
            ) : null}
          </div>
        ) : null}

        {c.description ? (
          <p className="mt-4 max-w-4xl text-sm leading-relaxed text-muted-foreground">
            {c.description}
          </p>
        ) : null}

        {c.schema_kind ? (
          <p className="mt-3 text-xs text-muted-foreground">
            {SCHEMA_LABEL[c.schema_kind] ?? c.schema_kind}
          </p>
        ) : null}
      </section>

      {/* Key ratios */}
      <section className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-3 lg:grid-cols-6">
        {[
          ["Market Cap", q?.market_cap != null ? `₹${formatCrore(q.market_cap, 0)} Cr` : "-"],
          ["Current Price", q?.current_price != null ? `₹${q.current_price.toFixed(2)}` : "-"],
          [
            "High / Low",
            q?.high52 != null && q?.low52 != null
              ? `₹${q.high52.toFixed(0)} / ₹${q.low52.toFixed(0)}`
              : "-",
          ],
          ["Stock P/E", k.pe != null ? k.pe.toFixed(2) : "-"],
          ["Book Value", k.book_value != null ? `₹${k.book_value.toFixed(2)}` : "-"],
          ["Dividend Yield", k.dividend_yield != null ? formatPercent(k.dividend_yield) : "-"],
          ["ROCE", k.roce3yearsavg != null ? formatPercent(k.roce3yearsavg) : "-"],
          ["ROE", k.returnonequity != null ? formatPercent(k.returnonequity) : "-"],
          ["Debt to equity", k.totaldebttoequity != null ? k.totaldebttoequity.toFixed(2) : "-"],
          ["EV / EBITDA", k.ev_ebitda != null ? k.ev_ebitda.toFixed(2) : "-"],
          ["Promoter holding", k.promoter_holding != null ? formatPercent(k.promoter_holding) : "-"],
          ["10Y return", k.price_cagr_10y != null ? formatPercent(k.price_cagr_10y, 1) : "-"],
        ].map(([label, value]) => (
          <div key={label} className="bg-card px-4 py-3">
            <div className="text-xs text-muted-foreground">{label}</div>
            <div className="tabular mt-0.5 text-sm font-medium">{value}</div>
          </div>
        ))}
      </section>

      {/* Price chart */}
      {chartData.length > 1 ? (
        <Section title="Price">
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
                <defs>
                  <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11 }}
                  stroke="hsl(var(--muted-foreground))"
                  minTickGap={60}
                  tickFormatter={(d: string) => d.slice(0, 7)}
                />
                <YAxis
                  tick={{ fontSize: 11 }}
                  stroke="hsl(var(--muted-foreground))"
                  domain={["auto", "auto"]}
                  width={56}
                />
                <Tooltip
                  contentStyle={{
                    background: "hsl(var(--popover))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: 6,
                    fontSize: 12,
                    color: "hsl(var(--popover-foreground))",
                  }}
                  formatter={(v) => [
                    typeof v === "number" ? `₹${v.toFixed(2)}` : "-",
                    "Close",
                  ]}
                />
                <Area
                  type="monotone"
                  dataKey="close"
                  stroke="hsl(var(--primary))"
                  strokeWidth={1.5}
                  fill="url(#priceFill)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Section>
      ) : null}

      <Section
        title="Quarterly Results"
        action={
          <Toggle
            options={[
              { value: "c", label: "Consolidated" },
              { value: "s", label: "Standalone" },
            ]}
            value={statementType}
            onChange={setStatementType}
          />
        }
      >
        <StatementTable
          headers={quarterly.data?.headers ?? []}
          rows={quarterly.data?.rows ?? []}
          note={statementNote}
        />
      </Section>

      <Section title="Profit &amp; Loss">
        <StatementTable
          headers={annual.data?.headers ?? []}
          rows={annual.data?.rows ?? []}
          note={statementNote}
        />
      </Section>

      <Section title="Balance Sheet">
        <StatementTable
          headers={balance.data?.headers ?? []}
          rows={balance.data?.rows ?? []}
          note={statementNote}
        />
      </Section>

      <Section title="Cash Flows">
        <StatementTable
          headers={cash.data?.headers ?? []}
          rows={cash.data?.rows ?? []}
          note={statementNote}
        />
      </Section>

      <Section title="Ratios">
        <SeriesTable data={ratios.data} />
      </Section>

      <Section title="Shareholding Pattern">
        <SeriesTable data={holding.data} />
      </Section>

      <Section title="Peer comparison">
        {peers.data?.peers.length ? (
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full min-w-max text-sm">
              <thead>
                <tr className="border-b bg-muted/50 text-left">
                  <th className="px-3 py-2 font-medium">Name</th>
                  <th className="px-3 py-2 text-right font-medium">CMP</th>
                  <th className="px-3 py-2 text-right font-medium">P/E</th>
                  <th className="px-3 py-2 text-right font-medium">Mar Cap Rs.Cr.</th>
                  <th className="px-3 py-2 text-right font-medium">Div Yld %</th>
                  <th className="px-3 py-2 text-right font-medium">ROE %</th>
                </tr>
              </thead>
              <tbody>
                {peers.data.peers.map((peer) => (
                  <tr
                    key={peer.symbol}
                    className={cn(
                      "border-b border-border/50 last:border-0",
                      peer.symbol === upper && "bg-accent/50 font-medium",
                    )}
                  >
                    <td className="px-3 py-2">
                      <Link to={`/company/${peer.symbol}`} className="text-primary hover:underline">
                        {peer.name}
                      </Link>
                    </td>
                    <td className="tabular px-3 py-2 text-right">
                      {peer.current_price?.toFixed(2) ?? "-"}
                    </td>
                    <td className="tabular px-3 py-2 text-right">{peer.pe?.toFixed(2) ?? "-"}</td>
                    <td className="tabular px-3 py-2 text-right">
                      {peer.market_cap != null ? formatCrore(peer.market_cap, 0) : "-"}
                    </td>
                    <td className="tabular px-3 py-2 text-right">
                      {peer.dividend_yield?.toFixed(2) ?? "-"}
                    </td>
                    <td className="tabular px-3 py-2 text-right">
                      {peer.returnonequity?.toFixed(2) ?? "-"}
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

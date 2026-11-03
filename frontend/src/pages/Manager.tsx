import { Download } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ErrorCard } from '@/components/ErrorCard'
import { Initials, Spark, StatusChip } from '@/components/manager/Shared'
import { ApiError, getManager, type ManagerAgent, type ManagerPayload } from '@/lib/api'
import { audio } from '@/lib/audioEngine'
import { AUTOSTART } from '@/lib/autostart'
import {
  agentsCsv, downloadCsv, exampleCall, isReviewOnly, num, pct, plural, reviewNote, ruleCount, ruleIds, ruleTitle, shortDate,
  SORT_LABEL, sortAgents, type SortKey,
} from '@/lib/manager'
import { usePageTitle } from '@/lib/usePageTitle'

/** Where violation counts appear: what they include and what is counted apart. */
const COUNT_NOTE = 'Includes R2 advisory flags. R6 is reviewed separately.'
const AXIS = { fontSize: 11, fill: '#5b6577' }
const barColor = (n: number) => (n >= 4 ? 'var(--mc-violation)' : n > 0 ? 'var(--mc-advisory)' : '#e5e7eb')

export function Manager() {
  usePageTitle('Manager · Maryada')
  const [range, setRange] = useState<{ from: string; to: string }>({ from: '', to: '' })
  const [data, setData] = useState<ManagerPayload | null>(null)
  const [missing, setMissing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    setError(null)
    setBusy(true)
    const ctl = new AbortController()
    getManager({ from: range.from || undefined, to: range.to || undefined }, ctl.signal)
      .then((d) => { setData(d); setMissing(false); setBusy(false) })
      .catch((e: Error) => {
        if (e.name === 'AbortError') return
        setBusy(false)
        if (e instanceof ApiError && e.code === 'no_manager_data') setMissing(true)
        else setError(e.message)
      })
    return () => ctl.abort()
  }, [range])
  useEffect(() => load(), [load])

  if (missing) {
    return (
      <section className="card mx-auto max-w-xl p-6" role="status">
        <h1 className="text-[17px] font-semibold tracking-tight">No team data yet</h1>
        <p className="mt-1 text-[13.5px] leading-relaxed text-[var(--mc-text-2)]">
          The team results file has not been built, so there are no numbers to show. It is built from the saved evaluation results
          with <code>tools/build_manager_data.py</code>.
        </p>
      </section>
    )
  }
  if (error && !data) return <ErrorCard message={error} onRetry={load} />
  if (!data) return <ManagerSkeleton />
  return <Dashboard data={data} range={range} setRange={setRange} busy={busy} error={error} retry={load} />
}

function ManagerSkeleton() {
  return (
    <div className="space-y-5" aria-busy="true" aria-label="Loading team compliance">
      <div className="skeleton h-14" />
      <div className="skeleton h-12" />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-6">
        {[0, 1, 2, 3, 4, 5].map((i) => <div key={i} className="skeleton h-28" />)}
      </div>
      <div className="skeleton h-96" />
      <div className="grid gap-5 md:grid-cols-2"><div className="skeleton h-64" /><div className="skeleton h-64" /></div>
    </div>
  )
}

function Dashboard({ data, range, setRange, busy, error, retry }: {
  data: ManagerPayload
  range: { from: string; to: string }
  setRange: (r: { from: string; to: string }) => void
  busy: boolean
  error: string | null
  retry: () => void
}) {
  const { kpis, source } = data
  const first = data.range.first_day ?? undefined
  const last = data.range.last_day ?? undefined
  const search = new URLSearchParams(Object.entries(range).filter(([, v]) => v)).toString()
  const filtered = Boolean(range.from || range.to)
  const attention = data.attention.map((id) => data.agents.find((a) => a.id === id)).filter((a): a is ManagerAgent => Boolean(a))
  const dayCount = data.by_day.length
  const [picked, setPicked] = useState<string[]>([])
  const shownRules = picked.length ? ruleIds(data).filter((r) => picked.includes(r)) : ruleIds(data)

  return (
    <div className={`flex flex-col gap-6 ${error ? "opacity-60" : ""}`} aria-busy={busy}>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[28px] font-bold tracking-[-0.025em]">Team compliance</h1>
          <p className="mt-0.5 text-sm text-[var(--mc-muted)]">Where coaching is needed across the team, from every call Maryada analysed.</p>
        </div>
        <div className="flex flex-wrap items-end gap-2.5">
          <DateField id="from" label="From" value={range.from} min={first} max={range.to || last} onChange={(v) => setRange({ ...range, from: v })} />
          <DateField id="to" label="To" value={range.to} min={range.from || first} max={last} onChange={(v) => setRange({ ...range, to: v })} />
          {filtered && <button type="button" className="btn" onClick={() => setRange({ from: '', to: '' })}>All dates</button>}
          <button type="button" className="btn" disabled={!data.agents.length} onClick={() => downloadCsv('maryada-agents.csv', agentsCsv(data, data.agents, ruleIds(data)))}>
            <Download className="h-3.5 w-3.5" aria-hidden /> Export CSV
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-[var(--mc-accent-ring)] bg-[var(--mc-accent-tint)] px-4 py-3 text-[13px] font-medium text-[var(--mc-accent-dark)]">
        <span>
          Sample data: {data.batch_label ?? 'synthetic calls'}. {source.note} Counts are small and not a performance assessment of real people.
        </span>
      </div>

      <RuleChips data={data} picked={picked} setPicked={setPicked} />

      {error && <div role="alert" className="banner-error rounded-xl px-4 py-3 text-[13px]">{error} <button type="button" className="font-semibold underline" onClick={retry}>Try again</button></div>}

      {kpis.calls === 0 ? (
        <section className="card p-6" role="status">
          <h2 className="text-[17px] font-semibold tracking-tight">No calls in this date range</h2>
          <p className="mt-1 text-[13.5px] text-[var(--mc-text-2)]">
            The saved calls run from {first ? shortDate(first) : '–'} to {last ? shortDate(last) : '–'}. Pick dates inside that period, or show all dates.
          </p>
        </section>
      ) : (
        <>
          <div className="flex flex-col gap-2">
            <Kpis data={data} dayCount={dayCount} />
            <p className="text-xs text-[var(--mc-muted)]">{COUNT_NOTE}</p>
          </div>
          <div className="flex flex-wrap items-start gap-5">
            <Leaderboard data={data} search={search} rules={shownRules} filtered={picked.length > 0} />
            <ByRule data={data} rules={shownRules} />
          </div>
          <div className="flex flex-wrap items-start gap-5">
            <Heatmap data={data} rules={shownRules} />
            <PerDay data={data} />
            <ByHour data={data} />
          </div>
          <Attention data={data} agents={attention} search={search} />
        </>
      )}

      <p className="text-xs text-[var(--mc-muted)]">
        All data is synthetic and the sample is small. Flags are for coaching and are not a performance assessment of real people or grounds for disciplinary action.
      </p>
    </div>
  )
}

function DateField({ id, label, value, min, max, onChange }: {
  id: string; label: string; value: string; min?: string; max?: string; onChange: (v: string) => void
}) {
  return (
    <label htmlFor={id} className="flex flex-col gap-1">
      <span className="lbl">{label}</span>
      <input
        id={id} type="date" value={value} min={min} max={max} onChange={(e) => onChange(e.target.value)}
        className="h-[38px] rounded-[10px] border border-[var(--mc-field)] bg-white px-3 text-[13px] font-medium text-[var(--mc-text-2)]"
      />
    </label>
  )
}

type Delta = { text: string; tone: string }
/** Later half minus earlier half. `lowerIsBetter` decides the colour; the arrow and sign carry the meaning without it. */
function delta(d: number | undefined, unit: 'pts' | 'risk', lowerIsBetter: boolean): Delta | undefined {
  if (d === undefined) return undefined
  const v = unit === 'pts' ? Math.round(d * 100) : Math.round(d)
  if (v === 0) return { text: 'no change vs first half', tone: 'text-[var(--mc-muted)]' }
  const good = lowerIsBetter ? v < 0 : v > 0
  return {
    text: `${v > 0 ? '▲ +' : '▼ −'}${Math.abs(v)}${unit === 'pts' ? ' pts' : ''} vs first half`,
    tone: good ? 'text-[var(--mc-good-practice-ink)]' : 'text-[var(--mc-violation-ink)]',
  }
}

function Kpi({ label, value, sub, tone, delta: dl }: { label: string; value: string; sub: string; tone?: string; delta?: Delta }) {
  return (
    <div className="card px-5 py-[18px]">
      <div className="lbl">{label}</div>
      <div className={`mt-1 text-[30px] font-bold leading-tight tracking-[-0.03em] ${tone ?? ''}`}>{value}</div>
      <div className="text-xs text-[var(--mc-muted)]">{sub}</div>
      {dl && <div className={`text-xs font-semibold ${dl.tone}`}>{dl.text}</div>}
    </div>
  )
}

function Kpis({ data, dayCount }: { data: ManagerPayload; dayCount: number }) {
  const k = data.kpis
  const withCalls = data.agents.filter((a) => a.calls)
  const lo = Math.min(...withCalls.map((a) => a.calls))
  const hi = Math.max(...withCalls.map((a) => a.calls))
  const dl = data.kpi_deltas ?? undefined
  const rulesHit = Object.values(data.rule_totals).filter((n) => n > 0).length
  return (
    <section aria-label="Summary" className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
      <Kpi label="Calls analysed" value={String(k.calls)} sub={`over ${plural(dayCount, 'day')}`} />
      <Kpi label="Agents" value={String(k.agents)} sub={lo === hi ? `${lo} calls each` : `${lo} to ${hi} calls each`} />
      <Kpi label="Violations" value={String(k.violations)} sub={`across ${plural(rulesHit, 'rule')}`} tone="text-[var(--mc-violation-ink)]" />
      <Kpi label="Violation rate" value={pct(k.violation_rate)} sub={`${k.calls_with_violation} of ${k.calls} calls`} delta={delta(dl?.violation_rate, 'pts', true)} />
      <Kpi label="Average risk" value={num(k.avg_risk)} sub="out of 100, peak of each call" delta={delta(dl?.avg_risk, 'risk', true)} />
      <Kpi label="Clean calls" value={pct(k.clean_rate)} sub={`${k.clean_calls} of ${k.calls} calls, no violations`} tone="text-[var(--mc-good-practice-ink)]" delta={delta(dl?.clean_rate, 'pts', false)} />
    </section>
  )
}

function RuleChips({ data, picked, setPicked }: { data: ManagerPayload; picked: string[]; setPicked: (r: string[]) => void }) {
  const toggle = (id: string) => setPicked(picked.includes(id) ? picked.filter((x) => x !== id) : [...picked, id])
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Filter by rule">
      <span className="lbl">Rules</span>
      {data.rules.map((r) => {
        const on = picked.includes(r.id)
        return (
          <button
            key={r.id} type="button" aria-pressed={on} title={`${r.title}${r.review_only ? ' (needs review only)' : ''}`} onClick={() => toggle(r.id)}
            className={`inline-flex h-8 items-center rounded-full border px-3 text-xs font-semibold ${on ? 'border-[var(--mc-accent)] bg-[var(--mc-accent-tint)] text-[var(--mc-accent-dark)]' : 'border-[var(--mc-field)] bg-white text-[var(--mc-text-2)]'}`}
          >
            {r.id}
          </button>
        )
      })}
      {picked.length > 0 && <button type="button" className="text-xs font-semibold underline" onClick={() => setPicked([])}>All rules</button>}
    </div>
  )
}

const DESC_FIRST: SortKey[] = ['calls', 'violations', 'avg_risk']

function Leaderboard({ data, search, rules, filtered }: { data: ManagerPayload; search: string; rules: string[]; filtered: boolean }) {
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'default', desc: false })
  const cols = 'md:grid md:grid-cols-[minmax(0,2.2fr)_.6fr_.9fr_.8fr_.8fr_1.3fr_1fr] md:items-center md:gap-3'
  // With a rule filter, only agents with a finding in the chosen rules stay, and their count covers those rules only.
  const counts = (a: ManagerAgent) => {
    let v = 0, r = 0
    for (const id of rules) { if (isReviewOnly(data, id)) r += ruleCount(data, a, id); else v += ruleCount(data, a, id) }
    return { v, r }
  }
  const rows = sortAgents(data.agents.filter((a) => !filtered || counts(a).v + counts(a).r > 0), sort.key, sort.desc, (a) => (filtered ? counts(a).v : a.violations))
  const heads: [string, SortKey | null][] = [['Agent', 'name'], ['Calls', 'calls'], ['Violations', 'violations'], ['Avg risk', 'avg_risk'], ['Top rule', 'top_rule'], ['Status', 'status'], ['Risk trend', null]]
  const click = (k: SortKey) => setSort((s) => (s.key !== k ? { key: k, desc: DESC_FIRST.includes(k) } : s.desc === DESC_FIRST.includes(k) ? { key: k, desc: !s.desc } : { key: 'default', desc: false })) // third click: back to the default order
  return (
    <section className="card min-w-0 flex-[999_1_640px] overflow-hidden" aria-labelledby="lb-h">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--mc-line)] px-6 py-4">
        <h2 id="lb-h" className="text-base font-semibold">Agent leaderboard</h2>
        <label className="flex items-center gap-2 text-xs text-[var(--mc-muted)] md:hidden">
          Sort by
          <select
            className="h-8 rounded-[10px] border border-[var(--mc-field)] bg-white px-2 text-[13px] font-medium text-[var(--mc-text-2)]"
            value={sort.key} onChange={(e) => setSort({ key: e.target.value as SortKey, desc: DESC_FIRST.includes(e.target.value as SortKey) })}
          >
            {(Object.keys(SORT_LABEL) as SortKey[]).map((k) => <option key={k} value={k}>{SORT_LABEL[k]}</option>)}
          </select>
        </label>
        <span className="hidden text-xs text-[var(--mc-muted)] md:inline" title={data.status_rule}>Click a heading to sort (a third click resets). Hover or focus a status for the rule.</span>
      </div>
      <div className={`hidden border-b border-[var(--mc-line)] bg-[#f9fafb] px-6 py-2.5 ${cols}`}>
        {heads.map(([h, k]) => k ? (
          <span key={h} className="th" aria-sort={sort.key === k ? (sort.desc ? 'descending' : 'ascending') : 'none'}>
            <button type="button" className="inline-flex items-center gap-1 font-[inherit] uppercase" onClick={() => click(k)}>
              {h}{sort.key === k ? (sort.desc ? ' ▼' : ' ▲') : ''}
            </button>
          </span>
        ) : <span key={h} className="th">{h}</span>)}
      </div>
      {rows.length === 0 && <p className="px-6 py-5 text-[13.5px] text-[var(--mc-text-2)]">No agent has a finding in the chosen rules.</p>}
      <ul>
        {rows.map((a) => {
          const c = counts(a)
          return (
            <li key={a.id} className={`flex flex-col gap-2 border-b border-[var(--mc-line-soft)] px-6 py-3.5 last:border-b-0 ${cols}`}>
              <Link to={`/manager/agent/${a.id}${search ? `?${search}` : ''}`} className="flex min-w-0 items-center gap-3 rounded-lg" aria-label={`${a.name}, ${a.team}: open their calls`}>
                <Initials name={a.name} status={a.status} />
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold text-[var(--mc-text)]">{a.name}</span>
                  <span className="block truncate text-xs text-[var(--mc-muted)]">{a.team}</span>
                </span>
              </Link>
              <Col label="Calls">{a.calls}</Col>
              <Col label="Violations">
                <span><b className="font-semibold">{filtered ? c.v : a.violations}</b>{filtered && c.r > 0 && <span className="text-xs text-[var(--mc-needs-review-ink)]"> +{c.r} to review</span>}</span>
              </Col>
              <Col label="Avg risk">{num(a.avg_risk)}</Col>
              <Col label="Top rule">
                {a.top_rule ? <span className="inline-flex h-[22px] items-center rounded-full bg-[var(--mc-line-soft)] px-2.5 text-[11px] font-bold text-[var(--mc-text-2)]" title={ruleTitle(data, a.top_rule)}>{a.top_rule}</span> : <span aria-label="none">–</span>}
              </Col>
              <Col label="Status"><StatusChip status={a.status} rule={data.status_rule} /></Col>
              <Col label="Risk trend"><Spark values={a.risk_trend} status={a.status} name={a.name} /></Col>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

/** One table cell: a "label value" pair on a phone, a plain cell from md up. */
function Col({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm tabular-nums md:block">
      <span className="text-xs text-[var(--mc-muted)] md:hidden">{label}</span>
      {children}
    </div>
  )
}

function ByRule({ data, rules }: { data: ManagerPayload; rules: string[] }) {
  const rows = rules.map((id) => {
    const review = isReviewOnly(data, id)
    return { id, name: ruleTitle(data, id), review, count: (review ? data.review_totals : data.rule_totals)[id] ?? 0 }
  })
  const unit = (r: { review: boolean; count: number }) => (r.review ? `${r.count} to review` : String(r.count))
  const summary = rows.map((r) => `${r.id} ${r.name}: ${unit(r)}`).join('; ')
  const note = reviewNote(data)
  return (
    <section className="card flex min-w-[300px] flex-[1_1_340px] flex-col gap-3 px-6 py-5" aria-labelledby="br-h">
      <h2 id="br-h" className="text-base font-semibold">Violations by rule</h2>
      <div role="img" aria-label={`Violations by rule. ${summary}`} style={{ height: Math.max(90, rows.length * 45) }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 28, bottom: 0, left: 0 }} accessibilityLayer={false}>
            <XAxis type="number" hide domain={[0, 'dataMax']} />
            <YAxis type="category" dataKey="id" width={30} tick={{ ...AXIS, fontWeight: 600 }} axisLine={false} tickLine={false} />
            <Bar dataKey="count" radius={[0, 6, 6, 0]} barSize={14} isAnimationActive={false} background={{ fill: '#f2f4f7', radius: 6 }}>
              {rows.map((r) => <Cell key={r.id} fill={r.review ? 'var(--mc-needs-review)' : barColor(r.count)} />)}
              <LabelList dataKey="count" position="right" style={{ fontSize: 12, fontWeight: 600, fill: '#0f172a' }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <ul className="grid gap-x-4 gap-y-0.5 text-xs text-[var(--mc-muted)] sm:grid-cols-2">
        {rows.map((r) => <li key={r.id}><b className="font-semibold text-[var(--mc-text-2)]">{r.id}</b> {r.name}: {unit(r)}</li>)}
      </ul>
      <p className="text-xs text-[var(--mc-muted)]">{COUNT_NOTE}</p>
      {note && rows.some((r) => r.review) && <p className="text-xs text-[var(--mc-muted)]">{note}</p>}
    </section>
  )
}

const cellTone = (n: number) =>
  n === 0 ? 'bg-[#f9fafb] text-[#667085]' : n === 1 ? 'bg-[#fee4e2] text-[#b42318]' : n === 2 ? 'bg-[#fda29b] text-[#7a271a]' : 'bg-[#d92d20] text-white'

function Heatmap({ data, rules }: { data: ManagerPayload; rules: string[] }) {
  const rows = data.agents.filter((a) => a.calls)
  return (
    <section className="card flex min-w-0 flex-[1.3_1_480px] flex-col gap-3 px-6 py-5" aria-labelledby="hm-h">
      <div className="flex items-center justify-between gap-2">
        <h2 id="hm-h" className="text-base font-semibold">Agent by rule</h2>
        <span className="text-xs text-[var(--mc-muted)]">Violations per agent</span>
      </div>
      <table className="w-full table-fixed border-separate border-spacing-1.5 text-left">
        <thead>
          <tr>
            <th scope="col" className="w-[34%] sm:w-[150px]"><span className="sr-only">Agent</span></th>
            {rules.map((r) => <th key={r} scope="col" className="th text-center" title={ruleTitle(data, r)}>{r}{isReviewOnly(data, r) ? '*' : ''}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => (
            <tr key={a.id}>
              <th scope="row" className="truncate pr-1 text-[13px] font-medium" title={a.name}>{a.name}</th>
              {rules.map((r) => {
                const review = isReviewOnly(data, r)
                const n = ruleCount(data, a, r)
                const tone = review ? (n ? 'bg-[var(--mc-needs-review-tint)] text-[var(--mc-needs-review-ink)]' : 'bg-[#f9fafb] text-[#667085]') : cellTone(n)
                return (
                  <td key={r} className={`h-[30px] rounded-lg text-center text-xs font-semibold tabular-nums ${tone}`} aria-label={`${a.name}, ${r}: ${review ? `${plural(n, 'case')} to review` : plural(n, 'violation')}`}>
                    {n}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {rules.some((r) => isReviewOnly(data, r)) && <p className="text-xs text-[var(--mc-muted)]">* {reviewNote(data)}</p>}
    </section>
  )
}

function PerDay({ data }: { data: ManagerPayload }) {
  const rows = data.by_day.map((d) => ({ ...d, label: shortDate(d.date) }))
  const summary = rows.filter((d) => d.violations).map((d) => `${d.label}: ${d.violations}`).join('; ') || 'none'
  return (
    <section className="card flex min-w-0 flex-[1_1_340px] flex-col gap-3 px-6 py-5" aria-labelledby="pd-h">
      <h2 id="pd-h" className="text-base font-semibold">Violations per day</h2>
      <div role="img" aria-label={`Violations per day, with days that had violations: ${summary}`} className="h-[170px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 14, right: 4, bottom: 0, left: -24 }} accessibilityLayer={false}>
            <CartesianGrid vertical={false} stroke="#eaecf0" />
            <XAxis dataKey="label" tick={AXIS} tickLine={false} interval="preserveStartEnd" minTickGap={24} />
            <YAxis allowDecimals={false} tick={AXIS} axisLine={false} tickLine={false} />
            <Tooltip cursor={{ fill: '#f2f4f7' }} formatter={(v) => [String(v), 'Violations']} />
            <Bar dataKey="violations" radius={[4, 4, 0, 0]} isAnimationActive={false}>
              {rows.map((d) => <Cell key={d.date} fill={barColor(d.violations)} />)}
              <LabelList dataKey="violations" position="top" formatter={(v: unknown) => (v ? String(v) : '')} style={{ fontSize: 11, fontWeight: 600, fill: '#0f172a' }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-[var(--mc-muted)]">{plural(data.kpis.calls, 'call')} on {plural(rows.length, 'day')}; the label is the number of violations.</p>
    </section>
  )
}

function ByHour({ data }: { data: ManagerPayload }) {
  const rows = data.by_hour.map((h) => ({ ...h, label: `${h.hour}:00`, ok: h.calls - h.r1_calls }))
  const summary = rows.filter((h) => h.calls).map((h) => `${h.label}: ${h.calls}${h.r1_calls ? ` (${h.r1_calls} outside permitted hours)` : ''}`).join('; ')
  return (
    <section className="card flex min-w-0 flex-[1_1_340px] flex-col gap-3 px-6 py-5" aria-labelledby="bh-h">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="bh-h" className="text-base font-semibold">Calls by hour</h2>
        <span className="chip chip-violation !text-[11px]">Outside permitted hours = R1</span>
      </div>
      <div role="img" aria-label={`Calls by start hour. ${summary}`} className="h-[170px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 14, right: 4, bottom: 0, left: -24 }} accessibilityLayer={false}>
            <CartesianGrid vertical={false} stroke="#eaecf0" />
            <XAxis dataKey="hour" tick={AXIS} tickLine={false} interval="preserveStartEnd" minTickGap={12} />
            <YAxis allowDecimals={false} tick={AXIS} axisLine={false} tickLine={false} />
            <Tooltip cursor={{ fill: '#f2f4f7' }} formatter={(v, k) => [String(v), k === 'r1_calls' ? 'Outside permitted hours' : 'Calls']} />
            <Bar dataKey="ok" stackId="h" fill="var(--mc-accent)" isAnimationActive={false} />
            <Bar dataKey="r1_calls" stackId="h" fill="var(--mc-violation)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-[var(--mc-muted)]">Hour the call started (IST). Red bars hold calls where the engine found R1.</p>
    </section>
  )
}

function Attention({ data, agents, search }: { data: ManagerPayload; agents: ManagerAgent[]; search: string }) {
  if (!agents.length) {
    return (
      <section aria-labelledby="na-h" className="card p-5">
        <h2 id="na-h" className="text-base font-semibold">Where coaching is needed</h2>
        <p className="mt-1 text-[13.5px] text-[var(--mc-text-2)]">No agent has a violation in this period, so there are no coaching cards.</p>
      </section>
    )
  }
  return (
    <section aria-labelledby="na-h" className="flex flex-col gap-3.5">
      <h2 id="na-h" className="text-lg font-semibold tracking-tight">Where coaching is needed</h2>
      <ul className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {agents.map((a) => {
          const ex = exampleCall(data, a)
          const rule = data.rules.find((r) => r.id === a.top_rule)
          const n = a.top_rule ? a.by_rule[a.top_rule] : 0
          return (
            <li key={a.id} className="card flex flex-col gap-3 p-5">
              <div className="flex items-center justify-between gap-2">
                <Link to={`/manager/agent/${a.id}${search ? `?${search}` : ''}`} className="text-[15px] font-semibold text-[var(--mc-text)] hover:underline">{a.name}</Link>
                <StatusChip status={a.status} rule={data.status_rule} />
              </div>
              <p className="text-[13px] text-[var(--mc-muted)]">
                Top rule: {a.top_rule} {rule?.title.toLowerCase()}, {plural(n, 'time')}; {plural(a.violations, 'violation')} in {plural(a.calls, 'call')}
              </p>
              {rule?.coach_line && (
                <p className="rounded-[10px] bg-[#f9fafb] px-3.5 py-3 text-[13.5px] leading-relaxed">
                  Practise this rule in role-play. Coach line: “{rule.coach_line}”
                </p>
              )}
              {ex &&
                (ex.has_replay ? (
                  <Link to={`/call/${ex.call_id}`} state={AUTOSTART} onClick={() => audio.unlock()} className="text-[13px] font-semibold">
                    Review example call (recorded run): {ex.title} →
                  </Link>
                ) : (
                  <p className="text-[13px] text-[var(--mc-muted)]">Example call: {ex.title}</p>
                ))}
            </li>
          )
        })}
      </ul>
    </section>
  )
}

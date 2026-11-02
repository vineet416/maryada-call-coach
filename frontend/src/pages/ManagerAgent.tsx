import { ArrowLeft } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ErrorCard } from '@/components/ErrorCard'
import { Initials, RecordedChip, StatusChip } from '@/components/manager/Shared'
import { ApiError, getManager, type ManagerCall, type ManagerPayload } from '@/lib/api'
import { RULE_IDS, num, plural, ruleTitle, shortDate } from '@/lib/manager'
import { usePageTitle } from '@/lib/usePageTitle'

const KIND_LABEL: Record<string, string> = { violation: 'violation', advisory: 'advisory', needs_review: 'needs review', good_practice: 'good practice' }
const AXIS = { fontSize: 11, fill: '#5b6577' }

export function ManagerAgent() {
  const { id = '' } = useParams()
  const search = useLocation().search // keeps the date range chosen on the Manager page
  const q = new URLSearchParams(search)
  const from = q.get('from') ?? undefined
  const to = q.get('to') ?? undefined
  const [data, setData] = useState<ManagerPayload | null>(null)
  const [missing, setMissing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const agent = data?.agents.find((a) => a.id === id)
  usePageTitle(`${agent?.name ?? 'Agent'} · Manager · Maryada`)

  const load = useCallback(() => {
    setError(null)
    setData(null)
    const ctl = new AbortController()
    getManager({ from, to }, ctl.signal)
      .then((d) => { setData(d); setMissing(false) })
      .catch((e: Error) => {
        if (e.name === 'AbortError') return
        if (e instanceof ApiError && e.code === 'no_manager_data') setMissing(true)
        else setError(e.message)
      })
    return () => ctl.abort()
  }, [from, to])
  useEffect(() => load(), [load])

  const back = (
    <Link to={`/manager${search}`} className="inline-flex items-center gap-1.5 text-[13px] font-semibold">
      <ArrowLeft className="h-3.5 w-3.5" aria-hidden /> Team compliance
    </Link>
  )
  const note = (title: string, text: string) => (
    <div className="flex flex-col gap-4">
      {back}
      <section className="card max-w-xl p-6" role="status">
        <h1 className="text-[17px] font-semibold">{title}</h1>
        <p className="mt-1 text-[13.5px] text-[var(--mc-text-2)]">{text}</p>
      </section>
    </div>
  )
  if (missing) return note('No team data yet', 'The team results file has not been built, so there is nothing to show for this agent.')
  if (error) return <ErrorCard message={error} onRetry={load} />
  if (!data) {
    return (
      <div className="space-y-5" aria-busy="true" aria-label="Loading the agent">
        <div className="skeleton h-10 w-48" /><div className="skeleton h-24" /><div className="skeleton h-72" />
      </div>
    )
  }
  if (!agent) return note('Agent not found', 'There is no agent with that id in the team data.')

  const calls = data.calls.filter((c) => c.agent_id === agent.id)
  const trend = calls.map((c) => ({ label: shortDate(c.call_date), risk: c.risk_peak }))
  const h = agent.first_half_vs_second_half
  return (
    <div className="flex flex-col gap-6">
      {back}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3.5">
          <Initials name={agent.name} status={agent.status} />
          <div>
            <h1 className="text-[28px] font-bold leading-tight tracking-[-0.025em]">{agent.name}</h1>
            <p className="text-sm text-[var(--mc-muted)]">{agent.team} · fictional agent</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusChip status={agent.status} />
          <RecordedChip note="Results come from a saved evaluation run, not a live one" savedOn={data.generated_at} />
        </div>
      </div>
      <p className="rounded-xl border border-[var(--mc-accent-ring)] bg-[var(--mc-accent-tint)] px-4 py-3 text-[13px] font-medium text-[var(--mc-accent-dark)]">
        {data.source.note} Flags are for coaching, not a performance assessment of a real person.
      </p>

      {agent.calls === 0 ? (
        <section className="card p-6" role="status">
          <h2 className="text-[17px] font-semibold">No calls in this date range</h2>
          <p className="mt-1 text-[13.5px] text-[var(--mc-text-2)]">This agent has no calls in the period you chose. Go back and pick other dates.</p>
        </section>
      ) : (
        <>
          <section aria-label="Summary" className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <Stat label="Calls" value={String(agent.calls)} sub={`${agent.calls_with_violation} with a violation`} />
            <Stat label="Violations" value={String(agent.violations)} sub={`${agent.needs_review} more to review`} />
            <Stat label="Average risk" value={num(agent.avg_risk)} sub={`peak ${num(agent.peak_risk)} of 100`} />
            <Stat label="Earlier vs later calls" value={`${h.first} → ${h.second}`} sub={`violations in ${plural(h.calls_first, 'earlier call')} and ${plural(h.calls_second, 'later call')}`} />
          </section>

          <div className="flex flex-wrap items-start gap-5">
            <section className="card flex min-w-[280px] flex-[1_1_320px] flex-col gap-3 px-6 py-5" aria-labelledby="mix-h">
              <h2 id="mix-h" className="text-base font-semibold">Rule mix</h2>
              <ul className="flex flex-col gap-1.5">
                {RULE_IDS.map((r) => (
                  <li key={r} className="flex items-center justify-between gap-3 text-[13px]">
                    <span><b className="font-semibold">{r}</b> <span className="text-[var(--mc-muted)]">{ruleTitle(data, r)}</span></span>
                    <b className="font-semibold tabular-nums">{agent.by_rule[r] ?? 0}</b>
                  </li>
                ))}
              </ul>
            </section>
            <section className="card flex min-w-[280px] flex-[2_1_420px] flex-col gap-3 px-6 py-5" aria-labelledby="rt-h">
              <h2 id="rt-h" className="text-base font-semibold">Risk per call</h2>
              <div role="img" aria-label={`Peak risk per call, oldest first: ${calls.map((c) => c.risk_peak).join(', ')}`} className="h-[170px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trend} margin={{ top: 8, right: 12, bottom: 0, left: -24 }} accessibilityLayer={false}>
                    <CartesianGrid vertical={false} stroke="#eaecf0" />
                    <XAxis dataKey="label" tick={AXIS} tickLine={false} />
                    <YAxis domain={[0, 100]} tick={AXIS} axisLine={false} tickLine={false} />
                    <Tooltip formatter={(v) => [String(v), 'Peak risk']} />
                    <Line type="monotone" dataKey="risk" stroke="var(--mc-accent)" strokeWidth={2} dot isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </section>
          </div>

          <section className="card overflow-hidden" aria-labelledby="calls-h">
            <h2 id="calls-h" className="border-b border-[var(--mc-line)] px-6 py-4 text-base font-semibold">Calls</h2>
            <ul>{calls.map((c) => <CallRow key={c.call_id} c={c} />)}</ul>
          </section>
        </>
      )}
      <p className="text-xs text-[var(--mc-muted)]">All data is synthetic and the sample is small. Not a performance assessment of real people.</p>
    </div>
  )
}

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="card px-5 py-[18px]">
      <div className="lbl">{label}</div>
      <div className="mt-1 text-[28px] font-bold leading-tight tracking-[-0.03em]">{value}</div>
      <div className="text-xs text-[var(--mc-muted)]">{sub}</div>
    </div>
  )
}

function CallRow({ c }: { c: ManagerCall }) {
  const shown = c.findings.filter((f) => f.kind !== 'good_practice')
  const good = c.findings.filter((f) => f.kind === 'good_practice').length
  return (
    <li className="flex flex-col gap-2 border-b border-[var(--mc-line-soft)] px-6 py-3.5 last:border-b-0 md:flex-row md:items-center md:justify-between md:gap-5">
      <div className="min-w-0">
        <div className="text-sm font-semibold">{c.title}</div>
        <div className="text-xs text-[var(--mc-muted)]">{shortDate(c.call_date)} at {c.call_time} · peak risk {c.risk_peak} of 100</div>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 md:flex-1 md:justify-end">
        {shown.length === 0 && <span className="text-xs text-[var(--mc-muted)]">No flags</span>}
        {shown.map((f) => (
          <span key={`${f.turn_idx}-${f.rule_id}`} className={`chip chip-${f.kind}`} title={f.quote}>
            {f.rule_id} {KIND_LABEL[f.kind]}, turn {f.turn_idx}
          </span>
        ))}
        {good > 0 && <span className="chip chip-good_practice">Good practice ×{good}</span>}
      </div>
      <Link to={`/call/${c.call_id}`} className="btn btn-sm self-start md:self-center">
        {c.has_replay ? 'Open recorded run' : 'Open call'}
      </Link>
    </li>
  )
}

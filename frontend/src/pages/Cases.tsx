import { Clock, Headset, Mic, Play, Search, ShieldAlert } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ErrorCard } from '@/components/ErrorCard'
import { getEval, getRules, getScenarios, type LatencyRow, type Rule, type ScenarioSummary } from '@/lib/api'
import { usePageTitle } from '@/lib/usePageTitle'
import { useHasKeys } from '@/store/keysStore'

const lengthLabel = (s: number | null) => {
  if (!s) return ''
  const m = Math.floor(s / 60)
  return m ? `${m} min ${String(Math.round(s % 60)).padStart(2, '0')} s` : `${Math.round(s)} s`
}
const plain = (s: string) => s.replace(/^HERO\.\s*/, '')
/** Chip tone of a rule tag: G = good practice, R6 = context, R1/R2 = advisory, the rest violations. */
const tagKind = (t: string) =>
  t.startsWith('G') ? 'good_practice' : t === 'R6' ? 'needs_review' : t === 'R1' || t === 'R2' ? 'advisory' : 'violation'

export function Cases() {
  usePageTitle('Maryada · live RBI-conduct coach for loan-recovery agents')
  const [cases, setCases] = useState<ScenarioSummary[] | null>(null)
  const [rules, setRules] = useState<Rule[]>([])
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [flag, setFlag] = useState<LatencyRow | null>(null)

  const load = useCallback(() => {
    setError(null)
    setCases(null)
    const ctl = new AbortController()
    getScenarios(ctl.signal)
      .then(setCases)
      .catch((e: Error) => e.name !== 'AbortError' && setError(e.message))
    getRules(ctl.signal)
      .then(setRules)
      .catch(() => undefined) // rule names are only a label; the page works without them
    getEval(ctl.signal)
      .then((e) => setFlag(e.latency.rows.find((r) => r.p50_ms !== null && r.n > 0) ?? null))
      .catch(() => undefined) // the time-to-flag fact is hidden when it cannot be read
    return () => ctl.abort()
  }, [])
  useEffect(() => load(), [load])

  const hero = cases?.find((c) => c.hero)
  // Recorded runs first (they play with no keys); the original order is kept inside each group
  const all = useMemo(() => [...(cases ?? [])].sort((a, b) => Number(b.has_replay) - Number(a.has_replay)), [cases])
  const recorded = all.filter((c) => c.has_replay).length
  const families = rules.filter((r) => r.id.startsWith('R')).length
  const ruleTags = useMemo(
    () => [...new Set(all.flatMap((c) => c.tags))].filter((t) => t.startsWith('R')).sort(),
    [all],
  )
  const name = (id: string) => rules.find((r) => r.id === id)?.title
  const shown = all.filter((c) => {
    const q = query.trim().toLowerCase()
    if (q && !`${c.id} ${c.title} ${c.summary}`.toLowerCase().includes(q)) return false
    if (filter === 'all') return true
    if (filter === 'recorded') return c.has_replay
    if (filter === 'clean') return !c.tags.some((t) => t.startsWith('R'))
    return c.tags.includes(filter)
  })

  if (error) return <ErrorCard message={error} onRetry={load} />

  return (
    <div className="flex flex-col gap-7">
      {!cases ? (
        <div className="space-y-5" aria-busy="true" aria-label="Loading cases">
          <div className="skeleton h-72" />
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="skeleton h-40" />
            ))}
          </div>
        </div>
      ) : (
        <>
          <ProductLine calls={all.length} families={families} flag={flag} />
          {hero && <Hero c={hero} name={name} />}
          <section aria-labelledby="samples-h" className="flex flex-col gap-4">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <h2 id="samples-h" className="text-xl font-semibold tracking-tight">Sample calls</h2>
                <p className="mt-0.5 text-[13px] text-[var(--mc-muted)]">
                  {all.length} synthetic recovery calls with known rule labels. Pick one to run it through Maryada.
                </p>
              </div>
              <label className="relative block w-full sm:w-auto">
                <span className="sr-only">Search calls</span>
                <Search className="pointer-events-none absolute left-3 top-1/2 h-[15px] w-[15px] -translate-y-1/2 text-[#667085]" aria-hidden />
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search calls"
                  className="input h-[38px] pl-9 sm:w-[260px]"
                />
              </label>
            </div>
            <div role="group" aria-label="Filter calls" className="flex flex-wrap gap-2">
              <FilterChip on={filter === 'all'} onClick={() => setFilter('all')}>All {all.length}</FilterChip>
              <FilterChip on={filter === 'recorded'} onClick={() => setFilter('recorded')}>Recorded runs {recorded}</FilterChip>
              {ruleTags.map((t) => (
                <FilterChip key={t} on={filter === t} onClick={() => setFilter(t)}>
                  {t}
                  {name(t) ? ` ${name(t)}` : ''}
                </FilterChip>
              ))}
              <FilterChip on={filter === 'clean'} onClick={() => setFilter('clean')}>Clean calls</FilterChip>
            </div>
            {shown.length === 0 ? (
              <p role="status" className="card p-8 text-center text-sm text-[var(--mc-muted)]">
                No calls match. Clear the search or pick another filter.
              </p>
            ) : (
              <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
                {shown.map((c) => (
                  <CaseCard key={c.id} c={c} />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}

/** One line on what Maryada is, with facts read from the data: call count, rule families, measured time to flag. */
function ProductLine({ calls, families, flag }: { calls: number; families: number; flag: LatencyRow | null }) {
  const facts = [
    calls > 0 && `${calls} synthetic calls`,
    families > 0 && `${families} rule families`,
    flag?.p50_ms != null && `median ${(flag.p50_ms / 1000).toFixed(1)} s to first flag in the recorded runs`,
  ].filter(Boolean) as string[]
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-lg font-semibold tracking-tight">A live RBI-conduct coach for loan-recovery agents</p>
      {facts.length > 0 && (
        <ul className="flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-[var(--mc-muted)]" aria-label="Facts">
          {facts.map((f) => (
            <li key={f} className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--mc-accent)]" aria-hidden />
              {f}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function FilterChip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={`chip cursor-pointer ${on ? '!border-[var(--mc-accent)] !bg-[var(--mc-accent)] !font-semibold !text-white' : 'hover:bg-[var(--mc-line-soft)]'}`}
    >
      {children}
    </button>
  )
}

function Hero({ c, name }: { c: ScenarioSummary; name: (id: string) => string | undefined }) {
  const hasKeys = useHasKeys()
  return (
    <section className="card flex flex-wrap overflow-hidden" aria-label="Featured call">
      <div className="flex min-w-0 flex-[1_1_520px] flex-col justify-center gap-4 p-6 sm:p-10">
        <span className="chip chip-accent self-start">Featured call · {c.id.toUpperCase()}</span>
        <h1 className="text-[28px] font-bold leading-[1.15] tracking-[-0.025em] sm:text-[34px]">{c.title}</h1>
        <p className="max-w-[560px] text-base leading-relaxed text-[#475467]">{plain(c.summary)}</p>
        <div className="flex flex-wrap gap-2">
          {c.duration_s ? (
            <span className="chip">
              <Clock className="h-3.5 w-3.5" aria-hidden /> {lengthLabel(c.duration_s)}
            </span>
          ) : null}
          {c.tags.map((t) => (
            <span key={t} className={`chip chip-${tagKind(t)}`}>
              {t}
              {name(t) ? ` ${name(t)}` : ''}
            </span>
          ))}
        </div>
        <div className="mt-1.5 flex flex-wrap gap-3">
          <Link to={`/call/${c.id}`} className="btn btn-lg btn-primary">
            <Play className="h-3.5 w-3.5 fill-current" aria-hidden /> {c.has_replay ? 'Play recorded run' : 'Open the call'}
          </Link>
          <Link to={`/call/${c.id}`} className="btn btn-lg">
            Start live call
            {!hasKeys && <span className="chip chip-warn h-5 text-[11px]">Needs your keys</span>}
          </Link>
        </div>
      </div>
      <div className="flex min-w-0 flex-[1_1_420px] items-center justify-center bg-[#f3f4ff] p-6 sm:p-10">
        <div className="card flex w-full max-w-[420px] flex-col gap-3 p-[18px] shadow-[0_12px_32px_rgb(67_56_202/0.12)]">
          <span className="lbl">What you will see</span>
          <Peek icon={<Mic className="h-4 w-4" aria-hidden />} title="Live transcript" text="Every agent sentence, checked against the rules as it is spoken." />
          <Peek icon={<ShieldAlert className="h-4 w-4" aria-hidden />} title="Risk and findings" text="Underlined phrases, a 0 to 100 risk meter and the rule behind each flag." />
          <Peek icon={<Headset className="h-4 w-4" aria-hidden />} title="Coach nudge" text="A short line for the agent only, as a card and, if you wish, a voice." />
        </div>
      </div>
    </section>
  )
}

function Peek({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return (
    <div className="flex items-start gap-3 rounded-[10px] bg-[var(--mc-accent-tint)] px-3 py-2.5">
      <span className="mt-0.5 text-[var(--mc-accent)]">{icon}</span>
      <div>
        <div className="text-[13px] font-semibold text-[var(--mc-accent-dark)]">{title}</div>
        <div className="text-[12.5px] leading-snug text-[var(--mc-text-2)]">{text}</div>
      </div>
    </div>
  )
}

function CaseCard({ c }: { c: ScenarioSummary }) {
  return (
    <Link to={`/call/${c.id}`} className="card flex flex-col gap-3 p-5 transition hover:border-[var(--mc-accent-ring)] hover:shadow-md">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold tracking-wide text-[var(--mc-muted)]">{c.id.toUpperCase()}</span>
        {c.has_replay ? (
          <span className="text-xs text-[var(--mc-muted)]">Recorded run</span>
        ) : (
          <span className="chip h-5 text-[11px]" title="No recorded run: this call needs your own keys">Live only</span>
        )}
      </div>
      <h3 className="text-base font-semibold leading-snug tracking-tight">{c.title}</h3>
      <p className="line-clamp-3 text-[13px] leading-normal text-[var(--mc-muted)]">{plain(c.summary)}</p>
      {c.tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {c.tags.map((t) => (
            <span key={t} className={`chip chip-${tagKind(t)} h-6 px-[9px] text-[11.5px]`}>{t}</span>
          ))}
        </div>
      )}
      <div className="mt-auto flex items-center justify-between border-t border-[var(--mc-line-soft)] pt-3 text-xs text-[var(--mc-muted)]">
        <span>{lengthLabel(c.duration_s)}</span>
        <span className="flex items-center gap-1 font-semibold text-[var(--mc-accent)]">
          {c.has_replay && <Play className="h-3 w-3 fill-current" aria-hidden />}
          {c.has_replay ? 'Play recorded run' : 'Live with your keys'}
        </span>
      </div>
    </Link>
  )
}

import { Clock, Play } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ErrorCard } from '@/components/ErrorCard'
import { getScenarios, type ScenarioSummary } from '@/lib/api'

export function Cases() {
  const [cases, setCases] = useState<ScenarioSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setError(null)
    setCases(null)
    const ctl = new AbortController()
    getScenarios(ctl.signal)
      .then(setCases)
      .catch((e: Error) => e.name !== 'AbortError' && setError(e.message))
    return () => ctl.abort()
  }, [])
  useEffect(() => load(), [load])

  if (error) return <ErrorCard message={error} onRetry={load} />
  const hero = cases?.find((c) => c.hero)
  const rest = cases?.filter((c) => !c.hero) ?? []

  return (
    <div>
      <p className="mb-5 max-w-2xl text-[15px] text-[var(--mc-muted)]">
        Maryada listens to a recovery call as it happens and whispers to the <em>human</em> agent when a line would cross an RBI
        conduct rule. Pick a synthetic call and watch it work.
      </p>

      {!cases ? (
        <div className="space-y-4" aria-busy="true" aria-label="Loading cases">
          <div className="skeleton h-48" />
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="skeleton h-32" />
            ))}
          </div>
        </div>
      ) : (
        <>
          {hero && <Hero c={hero} />}
          <h2 className="mb-3 mt-8 text-xs font-semibold uppercase tracking-widest text-[var(--mc-muted)]">More calls</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {rest.map((c) => (
              <CaseCard key={c.id} c={c} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function Hero({ c }: { c: ScenarioSummary }) {
  return (
    <section
      className="rise relative overflow-hidden rounded-3xl border border-[var(--mc-line)] bg-[var(--mc-surface)] p-6 sm:p-9"
      aria-label="Featured call"
    >
      {/* the boundary line: the one idea of the product, drawn large */}
      <div aria-hidden className="absolute inset-y-0 right-10 hidden w-px bg-gradient-to-b from-transparent via-[var(--mc-violation)] to-transparent opacity-60 sm:block" />
      <div aria-hidden className="absolute right-10 top-1/2 hidden -translate-y-1/2 translate-x-3 rotate-90 text-[10px] font-semibold uppercase tracking-[0.4em] text-[var(--mc-violation)]/70 sm:block">
        maryada
      </div>
      <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-[var(--mc-accent)]">The demo call</p>
      <h1 className="max-w-xl text-3xl font-semibold leading-tight sm:text-4xl">{c.title}</h1>
      <p className="mt-3 max-w-xl text-[var(--mc-muted)]">{c.summary.replace(/^HERO\.\s*/, '')}</p>
      <div className="mt-6 flex flex-wrap items-center gap-4">
        <Link
          to={`/call/${c.id}`}
          className="inline-flex items-center gap-2 rounded-full bg-[var(--mc-accent)] px-6 py-3 text-sm font-semibold text-white shadow-[0_8px_30px_-8px_var(--mc-accent)] transition hover:brightness-110"
        >
          <Play className="h-4 w-4 fill-current" aria-hidden /> Watch the demo call
        </Link>
        {c.duration_s && (
          <span className="mono flex items-center gap-1.5 text-sm text-[var(--mc-muted)]">
            <Clock className="h-4 w-4" aria-hidden /> about {Math.round(c.duration_s / 60 * 10) / 10 || 1} min
          </span>
        )}
      </div>
    </section>
  )
}

function CaseCard({ c }: { c: ScenarioSummary }) {
  return (
    <Link
      to={`/call/${c.id}`}
      className="group flex flex-col rounded-2xl border border-[var(--mc-line)] bg-[var(--mc-surface)] p-4 transition hover:-translate-y-0.5 hover:border-[var(--mc-accent)]/60"
    >
      <p className="mono mb-1 text-[11px] text-[var(--mc-muted)]">{c.id.toUpperCase()}</p>
      <h3 className="mb-1 font-semibold leading-snug">{c.title}</h3>
      <p className="mb-3 line-clamp-3 flex-1 text-sm text-[var(--mc-muted)]">{c.summary}</p>
      <div className="flex items-center justify-between text-xs text-[var(--mc-muted)]">
        <span className="mono">{c.duration_s ? `${c.duration_s}s` : ''}</span>
        <span className="flex items-center gap-1 text-[var(--mc-accent)] opacity-0 transition group-hover:opacity-100">
          <Play className="h-3 w-3 fill-current" aria-hidden /> Open
        </span>
      </div>
    </Link>
  )
}

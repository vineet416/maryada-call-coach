import { useEffect, useState } from 'react'
import { useSessionStore } from '@/store/sessionStore'

const BAND_COLOR = { low: 'var(--mc-risk-low)', medium: 'var(--mc-risk-medium)', high: 'var(--mc-risk-high)' } as const
const BAND_LABEL = { low: 'Low risk', medium: 'Medium risk', high: 'High risk' } as const

const R = 80
const ARC = Math.PI * R

/** Semicircle gauge. It follows risk.update events only, so a reconnect cannot make it jump. */
export function RiskMeter() {
  const risk = useSessionStore((s) => s.risk)
  const color = BAND_COLOR[risk.band]
  const [delta, setDelta] = useState<{ n: number; rule: string | null; key: number } | null>(null)

  useEffect(() => {
    if (risk.delta === 0) return
    setDelta({ n: risk.delta, rule: risk.reasonRule, key: Date.now() })
    const t = window.setTimeout(() => setDelta(null), 3500)
    return () => window.clearTimeout(t)
  }, [risk.score, risk.delta, risk.reasonRule])

  return (
    <section aria-label="Risk meter" className="rounded-2xl border border-[var(--mc-line)] bg-[var(--mc-surface)] p-4">
      <div className="mb-1 flex items-center justify-between text-xs text-[var(--mc-muted)]">
        <span className="font-semibold uppercase tracking-wide">Risk</span>
        <span style={{ color }}>{BAND_LABEL[risk.band]}</span>
      </div>
      <div className="relative mx-auto w-full max-w-[190px]">
        <svg viewBox="0 0 200 112" className="w-full" role="img" aria-label={`Risk ${risk.score} out of 100, ${risk.band}`}>
          <path d="M20 100 A80 80 0 0 1 180 100" fill="none" stroke="var(--mc-line)" strokeWidth="12" strokeLinecap="round" />
          <path
            d="M20 100 A80 80 0 0 1 180 100"
            fill="none"
            stroke={color}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={`${(risk.score / 100) * ARC} ${ARC}`}
            style={{ transition: 'stroke-dasharray 0.7s cubic-bezier(.2,.8,.2,1), stroke 0.4s' }}
          />
        </svg>
        <div className="absolute inset-x-0 bottom-1 text-center">
          <span className="mono text-3xl font-semibold" style={{ color }}>
            {risk.score}
          </span>
        </div>
      </div>
      <div className="h-5 text-center" aria-live="polite">
        {delta && (
          <span key={delta.key} className="rise mono inline-block rounded-full bg-[var(--mc-line)] px-2.5 py-0.5 text-xs">
            {delta.n > 0 ? '+' : ''}
            {delta.n} {delta.rule ?? ''}
          </span>
        )}
      </div>
    </section>
  )
}

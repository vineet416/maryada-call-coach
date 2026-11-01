import { useEffect, useState } from 'react'
import { useSessionStore } from '@/store/sessionStore'

const BAND_COLOR = { low: 'var(--mc-risk-low)', medium: 'var(--mc-risk-medium)', high: 'var(--mc-risk-high)' } as const
const BAND_INK = { low: 'var(--mc-good-practice-ink)', medium: 'var(--mc-advisory-ink)', high: 'var(--mc-violation-ink)' } as const
const BAND_LABEL = { low: 'Low risk', medium: 'Medium risk', high: 'High risk' } as const
const BAND_CHIP = { low: 'good_practice', medium: 'advisory', high: 'violation' } as const

const R = 90
const ARC = Math.PI * R

/** Semicircle gauge (a bar on phones). It follows risk.update events only, so a reconnect cannot make it jump. */
export function RiskMeter() {
  const risk = useSessionStore((s) => s.risk)
  const color = BAND_COLOR[risk.band]
  const ink = BAND_INK[risk.band]
  const [delta, setDelta] = useState<{ n: number; rule: string | null; key: number } | null>(null)

  useEffect(() => {
    if (risk.delta === 0) return
    setDelta({ n: risk.delta, rule: risk.reasonRule, key: Date.now() })
    const t = window.setTimeout(() => setDelta(null), 3500)
    return () => window.clearTimeout(t)
  }, [risk.score, risk.delta, risk.reasonRule])

  const deltaChip = delta && (
    <span key={delta.key} className={`rise chip chip-${BAND_CHIP[risk.band]} mono`}>
      {delta.n > 0 ? '+' : ''}
      {delta.n} {delta.rule ? `· ${delta.rule}` : ''}
    </span>
  )

  return (
    <section aria-label="Risk meter" className="card p-3.5 sm:p-5">
      {/* Phone: compact number and bar */}
      <div className="flex items-center gap-3 sm:hidden">
        <div className="mono text-[26px] font-bold leading-none tracking-tight" style={{ color: ink }} role="img" aria-label={`Risk ${risk.score} out of 100, ${risk.band}`}>
          {risk.score}
        </div>
        <div className="flex flex-1 flex-col gap-1.5">
          <div className="flex items-center justify-between text-[11px]">
            <span className="font-semibold" style={{ color: ink }}>{BAND_LABEL[risk.band]}</span>
            <span className="min-h-4" aria-live="polite">{deltaChip}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-[#eaecf0]">
            <div className="h-full rounded-full transition-[width] duration-700" style={{ width: `${risk.score}%`, background: color }} />
          </div>
        </div>
      </div>

      {/* Larger screens: gauge */}
      <div className="hidden flex-col items-center gap-1.5 sm:flex">
        <div className="flex w-full items-center justify-between">
          <span className="lbl">Risk</span>
          <span className={`chip chip-${BAND_CHIP[risk.band]} font-semibold`}>{BAND_LABEL[risk.band]}</span>
        </div>
        <div className="relative mt-1.5 h-[124px] w-[220px]">
          <svg width="220" height="124" viewBox="0 0 220 124" role="img" aria-label={`Risk ${risk.score} out of 100, ${risk.band}`}>
            <path d="M20 112 A90 90 0 0 1 200 112" fill="none" stroke="#eaecf0" strokeWidth="16" strokeLinecap="round" />
            <path
              d="M20 112 A90 90 0 0 1 200 112"
              fill="none"
              stroke={color}
              strokeWidth="16"
              strokeLinecap="round"
              strokeDasharray={`${(risk.score / 100) * ARC} ${ARC}`}
              style={{ transition: 'stroke-dasharray 0.7s cubic-bezier(.2,.8,.2,1), stroke 0.4s' }}
            />
          </svg>
          <div className="mono absolute inset-x-0 bottom-0.5 text-center text-[40px] font-bold leading-none tracking-tight" style={{ color: ink }}>
            {risk.score}
          </div>
        </div>
        <div className="flex w-[196px] justify-between text-[11px] text-[var(--mc-muted)]" aria-hidden>
          <span>0</span>
          <span>100</span>
        </div>
        <div className="mt-1 h-[26px]" aria-live="polite">{deltaChip}</div>
      </div>
    </section>
  )
}

import { useEffect, useState } from 'react'
import { findingAt } from '@/lib/findings'
import type { Finding } from '@/lib/events'
import type { TurnView } from '@/store/sessionStore'
import { WordToken } from '@/components/WordToken'
import { ShimmerLine } from '@/components/ShimmerLine'

const WHO = {
  agent: { label: 'Agent', color: 'var(--mc-agent)' },
  borrower: { label: 'Borrower', color: 'var(--mc-borrower)' },
  third_party: { label: 'Third party', color: 'var(--mc-third)' },
} as const

const fmt = (ms: number) => {
  const s = Math.floor(ms / 1000)
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

interface Props {
  turn: TurnView
  offsetMs: number
  findings: Finding[]
  onOpen: (f: Finding) => void
}

export function Bubble({ turn, offsetMs, findings, onOpen }: Props) {
  const who = WHO[turn.speaker]
  const agent = turn.speaker === 'agent'
  const waiting = turn.tokens.length === 0
  const slow = useSlow(turn)
  const reveal = !turn.instant
  const n = Math.max(1, Math.max(0, ...turn.tokens.map((t) => t.n)))
  const step = Math.min(40, 1200 / n)

  return (
    <article
      aria-label={`${who.label} turn ${turn.idx}`}
      className={`rise flex ${agent ? 'justify-start' : 'justify-end'}`}
    >
      <div
        className="w-full max-w-[94%] rounded-xl border border-[var(--mc-line)] bg-[var(--mc-surface)] px-4 py-3"
        style={{ borderLeft: agent ? `3px solid ${who.color}` : undefined, borderRight: agent ? undefined : `3px solid ${who.color}` }}
      >
        <header className="mb-1 flex items-center gap-2 text-xs">
          <span className="font-semibold" style={{ color: who.color }}>
            {who.label}
          </span>
          <span className="mono text-[var(--mc-muted)]">{fmt(offsetMs)}</span>
        </header>
        {waiting ? (
          <div className="space-y-2 py-1.5" aria-label="Listening">
            <div className="shimmer w-4/5" />
            <div className="shimmer w-2/5" />
          </div>
        ) : (
          <p className="text-[17px] leading-[1.7]" style={{ fontFamily: 'var(--font-transcript)' }}>
            {turn.tokens.map((t) => (
              <WordToken
                key={t.i}
                turnIdx={turn.idx}
                token={t}
                finding={findingAt(findings, turn.idx, t.i)}
                reveal={reveal}
                step={step}
                onOpen={onOpen}
              />
            ))}
          </p>
        )}
        {turn.analysing && !waiting && <ShimmerLine label="Checking against the rulebook" />}
        {slow && <p className="mt-1 text-xs text-[var(--mc-advisory)]">Taking longer than usual…</p>}
      </div>
    </article>
  )
}

/** True when an agent turn has waited more than 8 s for its transcript or check. */
function useSlow(turn: TurnView) {
  const [slow, setSlow] = useState(false)
  const pending = turn.speaker === 'agent' && !turn.ended
  useEffect(() => {
    if (!pending) {
      setSlow(false)
      return
    }
    const wait = Math.max(0, 8000 - (Date.now() - turn.startedAt))
    const t = window.setTimeout(() => setSlow(true), wait + turn.durationMs)
    return () => window.clearTimeout(t)
  }, [pending, turn.startedAt, turn.durationMs])
  return slow
}

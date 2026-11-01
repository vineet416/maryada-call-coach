import { useEffect, useState } from 'react'
import { findingAt } from '@/lib/findings'
import type { Finding } from '@/lib/events'
import type { TurnView } from '@/store/sessionStore'
import { WordToken } from '@/components/WordToken'
import { ShimmerLine } from '@/components/ShimmerLine'

const WHO = {
  agent: { label: 'Agent', initials: 'AG', avatar: 'bg-[var(--mc-accent-tint)] text-[var(--mc-accent-dark)]' },
  borrower: { label: 'Borrower', initials: 'BR', avatar: 'bg-[#f2f4f7] text-[#475467]' },
  third_party: { label: 'Third party', initials: 'TP', avatar: 'bg-[#f2f4f7] text-[#475467]' },
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
  const flagged = findings.filter((f) => f.turn_idx === turn.idx && f.kind !== 'good_practice').length

  return (
    <article
      aria-label={`${who.label} turn ${turn.idx}`}
      className={`rise flex gap-2.5 sm:gap-3 ${agent ? 'max-w-[94%] sm:max-w-[88%]' : 'max-w-[94%] flex-row-reverse self-end sm:max-w-[80%]'}`}
    >
      <div
        className={`flex h-[26px] w-[26px] flex-none items-center justify-center rounded-full text-[10px] font-bold sm:h-8 sm:w-8 sm:text-xs ${who.avatar}`}
        aria-hidden
      >
        {who.initials}
      </div>
      <div className={`flex min-w-0 flex-col gap-1.5 ${agent ? '' : 'items-end'}`}>
        <div className="text-xs text-[var(--mc-muted)]">
          <b className="font-semibold text-[var(--mc-text)]">{who.label}</b> · <span className="mono">{fmt(offsetMs)}</span>
          {flagged > 0 && (
            <>
              {' · '}
              <span className="font-semibold text-[var(--mc-violation-ink)]">
                {flagged} finding{flagged === 1 ? '' : 's'}
              </span>
            </>
          )}
        </div>
        <div
          className={`px-4 py-3 ${
            agent
              ? `rounded-[4px_14px_14px_14px] bg-[#f6f7fb] ${flagged ? 'border border-[var(--mc-violation-edge)]' : ''}`
              : 'rounded-[14px_4px_14px_14px] border border-[var(--mc-line)] bg-white'
          }`}
        >
          {waiting ? (
            <div className="w-40 space-y-2 py-1.5" aria-label="Listening">
              <div className="shimmer w-4/5" />
              <div className="shimmer w-2/5" />
            </div>
          ) : (
            <p className="text-left text-[15px] leading-[1.9] [word-spacing:normal]" style={{ fontFamily: 'var(--font-transcript)' }}>
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
          {slow && <p className="mt-1 text-xs text-[var(--mc-advisory-ink)]">Taking longer than usual…</p>}
        </div>
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

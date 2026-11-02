import { useEffect, useMemo, useState } from 'react'
import { findingAt } from '@/lib/findings'
import type { Finding } from '@/lib/events'
import type { TokenView, TurnView } from '@/store/sessionStore'
import { Phrase, Word } from '@/components/WordToken'
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
  /** Speak live: the agent is the visitor, so the speaker label reads "You" */
  you?: boolean
}

export function Bubble({ turn, offsetMs, findings, onOpen, you = false }: Props) {
  const who = you ? { ...WHO.agent, label: 'You', initials: 'YOU' } : WHO[turn.speaker]
  const agent = turn.speaker === 'agent'
  const waiting = turn.tokens.length === 0
  const slow = useSlow(turn)
  const reveal = !turn.instant
  const n = Math.max(1, Math.max(0, ...turn.tokens.map((t) => t.n)))
  const step = Math.min(40, 1200 / n)
  const flagged = findings.filter((f) => f.turn_idx === turn.idx && f.kind !== 'good_practice').length
  const { groups, broadGood } = useMemo(() => group(turn, findings), [turn, findings])

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
          {broadGood && (
            <>
              {' · '}
              <button
                type="button"
                onClick={() => onOpen(broadGood)}
                aria-label="Good practice in this turn, press Enter for details"
                className="chip chip-good_practice h-5 cursor-pointer px-2 text-[11px] hover:brightness-95"
              >
                Good practice
              </button>
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
              {groups.map((g) =>
                g.finding ? (
                  <Phrase key={g.tokens[0].i} turnIdx={turn.idx} tokens={g.tokens} finding={g.finding} reveal={reveal} step={step} onOpen={onOpen} />
                ) : (
                  g.tokens.map((t) => <Word key={t.i} turnIdx={turn.idx} token={t} reveal={reveal} step={step} />)
                ),
              )}
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

/** A good-practice span longer than this share of the turn is not painted: a tag on the bubble shows it instead. */
const BROAD_SHARE = 0.7

interface Group {
  finding: Finding | null
  tokens: TokenView[]
}

/** Consecutive words under the same finding become one phrase. Returns the broad good-practice finding, if any. */
function group(turn: TurnView, findings: Finding[]): { groups: Group[]; broadGood: Finding | null } {
  let broadGood: Finding | null = null
  const groups: Group[] = []
  for (const t of turn.tokens) {
    let f = findingAt(findings, turn.idx, t.i)
    if (f && f.kind === 'good_practice') {
      const covered = turn.tokens.filter((x) => x.i >= f!.token_range[0] && x.i < f!.token_range[1]).length
      if (covered / turn.tokens.length > BROAD_SHARE) {
        broadGood = broadGood ?? f
        f = null
      }
    }
    const last = groups[groups.length - 1]
    if (last && last.finding?.id === f?.id && (f !== null || last.finding === null)) last.tokens.push(t)
    else groups.push({ finding: f, tokens: [t] })
  }
  return { groups, broadGood }
}

import type { Mode, SessionStatus } from '@/store/sessionStore'

/** What the call is doing now: Ready before a start, Recorded for a recorded run, Live only for a running live session. */
export function ModeBadge({ mode, status }: { mode: Mode; status: SessionStatus }) {
  const recorded = mode === 'replay'
  const live = !recorded && status === 'live'
  const label = recorded ? 'Recorded' : live ? 'Live' : status === 'ended' ? 'Ended' : 'Ready'
  const tone = recorded ? 'chip-warn' : live ? 'chip-ok' : ''
  const dot = recorded ? 'var(--mc-advisory)' : live ? 'var(--mc-good-practice)' : '#98a2b3'
  return (
    <span title={recorded ? 'Recorded run: not a live check' : undefined} className={`chip ${tone}`}>
      <span className={`h-[7px] w-[7px] rounded-full ${live ? 'pulse-dot' : ''}`} style={{ background: dot }} aria-hidden />
      {label}
    </span>
  )
}

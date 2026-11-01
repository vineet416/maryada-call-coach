import type { Mode, SessionStatus } from '@/store/sessionStore'

/** What the call is doing now: Ready before a start, Recorded for a replay, Live only for a running live session. */
export function ModeBadge({ mode, status }: { mode: Mode; status: SessionStatus }) {
  const replay = mode === 'replay'
  const live = !replay && status === 'live'
  const label = replay ? 'Recorded' : live ? 'Live' : status === 'ended' ? 'Ended' : 'Ready'
  return (
    <span
      title={replay ? 'Replay mode: a recorded run, not a live check' : undefined}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${
        replay
          ? 'border-[var(--mc-advisory)]/50 bg-[var(--mc-advisory)]/10 text-[var(--mc-advisory)]'
          : live
            ? 'border-[var(--mc-good-practice)]/50 bg-[var(--mc-good-practice)]/10 text-[var(--mc-good-practice)]'
            : 'border-[var(--mc-line)] text-[var(--mc-muted)]'
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full bg-current ${live ? 'pulse-dot' : ''}`} aria-hidden />
      {label}
    </span>
  )
}

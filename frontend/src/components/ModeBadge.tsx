import type { Mode } from '@/store/sessionStore'

/** "Replay mode" must be visible whenever recorded results are used (CLAUDE.md rule 4). */
export function ModeBadge({ mode }: { mode: Mode }) {
  const replay = mode === 'replay'
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${
        replay
          ? 'border-[var(--mc-advisory)]/50 bg-[var(--mc-advisory)]/10 text-[var(--mc-advisory)]'
          : 'border-[var(--mc-good-practice)]/50 bg-[var(--mc-good-practice)]/10 text-[var(--mc-good-practice)]'
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full bg-current ${replay ? '' : 'pulse-dot'}`} aria-hidden />
      {replay ? 'Replay mode' : 'Live mode'}
    </span>
  )
}

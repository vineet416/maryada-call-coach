import { useSessionStore } from '@/store/sessionStore'

const STEPS = [
  { key: 'listening', label: 'Listening' },
  { key: 'transcribing', label: 'Transcribing' },
  { key: 'checking', label: 'Checking rules' },
  { key: 'coaching', label: 'Coaching' },
] as const

/** "Listening → Transcribing → Checking rules → Coaching": the real stage, always visible. */
export function StageLine() {
  const stage = useSessionStore((s) => s.stage)
  const status = useSessionStore((s) => s.status)
  const current = stage?.stage ?? (status === 'connecting' ? 'connecting' : 'listening')
  const at = STEPS.findIndex((s) => s.key === current)
  return (
    <div role="status" aria-live="polite" className="text-xs">
      <ol className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
        {STEPS.map((s, i) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <span
              className={
                i === at
                  ? 'font-semibold text-[var(--mc-text)]'
                  : 'text-[var(--mc-muted)]/70'
              }
            >
              {i === at && <span className="pulse-dot mr-1 inline-block h-1.5 w-1.5 rounded-full bg-[var(--mc-accent)]" aria-hidden />}
              {s.label}
            </span>
            {i < STEPS.length - 1 && <span aria-hidden className="text-[var(--mc-line)]">→</span>}
          </li>
        ))}
      </ol>
      <p className="mt-1 text-[var(--mc-muted)]">{stage?.text ?? (current === 'connecting' ? 'Connecting' : 'Ready')}</p>
    </div>
  )
}

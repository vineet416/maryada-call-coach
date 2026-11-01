import { Check } from 'lucide-react'
import { useSessionStore } from '@/store/sessionStore'

const STEPS = [
  { key: 'listening', label: 'Listening' },
  { key: 'transcribing', label: 'Transcribing' },
  { key: 'checking', label: 'Checking rules' },
  { key: 'coaching', label: 'Coaching' },
] as const

/** "Listening, Transcribing, Checking rules, Coaching": the real stage, always visible. */
export function StageLine() {
  const stage = useSessionStore((s) => s.stage)
  const status = useSessionStore((s) => s.status)
  const current = stage?.stage ?? (status === 'connecting' ? 'connecting' : 'listening')
  const at = STEPS.findIndex((s) => s.key === current)
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Stage"
      className="flex flex-wrap items-center gap-x-2.5 gap-y-2 border-t border-[#eaecf0] px-4 py-3.5 text-[13px] sm:px-6"
    >
      {STEPS.map((s, i) => (
        <span key={s.key} className="flex items-center gap-2.5">
          {i === at ? (
            <span className="inline-flex items-center gap-2 rounded-full bg-[var(--mc-accent-tint)] px-3 py-1 font-semibold text-[var(--mc-accent-dark)]">
              <span className="pulse-dot h-2 w-2 rounded-full bg-[var(--mc-accent)]" aria-hidden />
              {s.label}
            </span>
          ) : (
            <span className={`inline-flex items-center gap-2 font-medium ${at >= 0 && i < at ? 'text-[var(--mc-good-practice-ink)]' : 'text-[var(--mc-muted)]'}`}>
              {at >= 0 && i < at && <Check className="h-4 w-4" strokeWidth={2.5} aria-hidden />}
              {s.label}
            </span>
          )}
          {i < STEPS.length - 1 && <span aria-hidden className="text-[#d0d5dd]">—</span>}
        </span>
      ))}
      <span className="w-full text-xs text-[var(--mc-muted)] sm:ml-auto sm:w-auto">
        {stage?.text ?? (current === 'connecting' ? 'Connecting' : 'Each agent turn is checked against the rulebook as it is spoken')}
      </span>
    </div>
  )
}

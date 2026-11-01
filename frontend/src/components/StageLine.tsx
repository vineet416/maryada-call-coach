import { Check } from 'lucide-react'
import { useSessionStore } from '@/store/sessionStore'

const OTHER = { borrower: 'Borrower', third_party: 'Third party' } as const

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
  const turns = useSessionStore((s) => s.turns)
  // Only agent turns are checked: while someone else speaks, the line reads "Listening"
  const latest = Math.max(stage?.turnIdx ?? -1, turns.length ? turns[turns.length - 1].idx : -1)
  const speaker = turns.find((t) => t.idx === latest)?.speaker
  const other = speaker && speaker !== 'agent' ? OTHER[speaker] : null
  const current = other ? 'listening' : (stage?.stage ?? (status === 'connecting' ? 'connecting' : 'listening'))
  const at = STEPS.findIndex((s) => s.key === current)
  const label = at >= 0 ? STEPS[at].label : ''
  const detail = other
    ? `${other} is speaking. Only agent turns are checked`
    : (stage?.text ?? (current === 'connecting' ? 'Connecting' : 'Each agent turn is checked against the rulebook as it is spoken'))
  // The detail line never repeats the step name that is already highlighted
  const showDetail = detail.trim().toLowerCase() !== label.toLowerCase()
  return (
    <div role="status" aria-live="polite" aria-label="Stage" className="flex flex-col gap-2 border-t border-[#eaecf0] px-4 py-2.5 text-[13px] sm:flex-row sm:flex-wrap sm:items-center sm:px-6">
      <ol className="flex flex-wrap items-center gap-x-1.5 gap-y-1.5 sm:gap-x-2.5">
        {STEPS.map((s, i) => {
          const done = at >= 0 && i < at
          return (
            <li key={s.key} className="flex items-center gap-1.5 sm:gap-2.5">
              {i === at ? (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-[var(--mc-accent-tint)] px-2.5 py-1 text-xs font-semibold text-[var(--mc-accent-dark)] sm:gap-2 sm:px-3 sm:text-[13px]">
                  <span className="pulse-dot h-2 w-2 rounded-full bg-[var(--mc-accent)]" aria-hidden />
                  {s.label}
                </span>
              ) : (
                <span className={`inline-flex items-center gap-1 text-xs font-medium sm:gap-2 sm:text-[13px] ${done ? 'text-[var(--mc-good-practice-ink)]' : 'text-[var(--mc-muted)]'}`}>
                  {done && <Check className="h-3.5 w-3.5 sm:h-4 sm:w-4" strokeWidth={2.5} aria-hidden />}
                  {s.label}
                </span>
              )}
              {i < STEPS.length - 1 && <span aria-hidden className="hidden text-[#d0d5dd] sm:inline">—</span>}
            </li>
          )
        })}
      </ol>
      {showDetail && <span className="text-xs text-[var(--mc-muted)] sm:ml-auto">{detail}</span>}
    </div>
  )
}

import { Headset } from 'lucide-react'
import type { Rule } from '@/lib/api'
import { audio } from '@/lib/audioEngine'
import { useSessionStore } from '@/store/sessionStore'

/** The coach nudge: the card is the primary channel, the voice (optional) plays at the pause. */
export function CoachCard({ rules, voiceOn, onVoice }: { rules: Rule[]; voiceOn: boolean; onVoice: (v: boolean) => void }) {
  const nudge = useSessionStore((s) => s.nudge)
  const hold = useSessionStore((s) => s.coachHold)
  const rule = nudge ? rules.find((r) => r.id === nudge.ruleId) : null

  return (
    <section
      aria-label="Coach"
      className="relative overflow-hidden rounded-2xl border bg-[var(--mc-surface)] p-4"
      style={{ borderColor: nudge ? 'color-mix(in srgb, var(--mc-coach) 55%, transparent)' : 'var(--mc-line)' }}
    >
      <div className="mb-2 flex items-center gap-2">
        <span
          className="flex h-8 w-8 items-center justify-center rounded-full"
          style={{ background: 'color-mix(in srgb, var(--mc-coach) 16%, transparent)', color: 'var(--mc-coach)' }}
        >
          <Headset className="h-4 w-4" aria-hidden />
        </span>
        <div className="leading-tight">
          <p className="text-sm font-semibold">Coach</p>
          <p className="text-[11px] text-[var(--mc-muted)]">Heard only by the agent</p>
        </div>
        <label className="ml-auto flex cursor-pointer items-center gap-1.5 text-xs text-[var(--mc-muted)]">
          <input
            type="checkbox"
            checked={voiceOn}
            onChange={(e) => {
              audio.setCoachVoice(e.target.checked)
              onVoice(e.target.checked)
            }}
            className="accent-[var(--mc-coach)]"
          />
          Coach voice
        </label>
      </div>

      {nudge ? (
        <div key={nudge.findingId ?? nudge.text} className="rise">
          <p className="mb-1 text-xs font-medium uppercase tracking-wide" style={{ color: 'var(--mc-coach)' }}>
            {nudge.ruleId} · {rule?.title ?? 'Rule'}
          </p>
          <p className="text-[15px] leading-relaxed">{nudge.text}</p>
          <div className="mt-2 flex items-center gap-2 text-xs text-[var(--mc-muted)]" aria-live="polite">
            {nudge.speaking ? (
              <>
                <span className="flex h-3 items-end gap-0.5" aria-hidden>
                  {[0, 1, 2, 3].map((i) => (
                    <span key={i} className="wave h-3 w-0.5 rounded bg-[var(--mc-coach)]" style={{ animationDelay: `${i * 0.1}s` }} />
                  ))}
                </span>
                Speaking in the agent's headset
              </>
            ) : voiceOn ? (
              'Voice plays at the next pause'
            ) : (
              'Voice is off. The card still shows.'
            )}
          </div>
        </div>
      ) : (
        <p className="py-2 text-sm text-[var(--mc-muted)]">Quiet so far. The coach speaks up when a rule is at risk.</p>
      )}

      {hold && (
        <p className="mt-3 rounded-md bg-[var(--mc-coach)]/10 px-2.5 py-1.5 text-xs" style={{ color: 'var(--mc-coach)' }}>
          Demo: call paused while the coach speaks
        </p>
      )}
    </section>
  )
}

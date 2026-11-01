import { Headset } from 'lucide-react'
import type { Rule } from '@/lib/api'
import { audio } from '@/lib/audioEngine'
import { useSessionStore } from '@/store/sessionStore'
import { Switch } from '@/components/Switch'

const KIND: Record<string, string> = { violation: 'violation', advisory: 'advisory', needs_review: 'needs_review', good_practice: 'good_practice' }

/** The coach nudge: the card is the primary channel, the voice (optional) plays over the call, quieter than the callers. */
export function CoachCard({ rules, voiceOn, onVoice }: { rules: Rule[]; voiceOn: boolean; onVoice: (v: boolean) => void }) {
  const nudge = useSessionStore((s) => s.nudge)
  const hold = useSessionStore((s) => s.coachHold)
  const rule = nudge ? rules.find((r) => r.id === nudge.ruleId) : null
  const tone = KIND[rule?.kind_default ?? 'violation'] ?? 'violation'

  return (
    <section
      aria-label="Coach"
      className="card flex flex-col gap-3.5 p-4 sm:p-5"
      style={nudge ? { borderColor: 'var(--mc-accent-ring)', boxShadow: '0 0 0 4px var(--mc-accent-tint)' } : undefined}
    >
      <div className="flex items-center gap-3">
        <span className="flex h-[38px] w-[38px] flex-none items-center justify-center rounded-full bg-[var(--mc-accent-tint)] text-[var(--mc-accent)]">
          <Headset className="h-5 w-5" aria-hidden />
        </span>
        <div className="flex-1 leading-tight">
          <p className="text-[15px] font-semibold">Coach</p>
          <p className="text-xs text-[var(--mc-muted)]">Heard only by the agent</p>
        </div>
        <label className="inline-flex items-center gap-2 text-xs text-[#475467]">
          Voice
          <Switch
            small
            label="Coach voice"
            checked={voiceOn}
            onChange={(v) => {
              audio.setCoachVoice(v)
              onVoice(v)
            }}
          />
        </label>
      </div>

      {nudge ? (
        <div key={nudge.findingId ?? nudge.text} className="rise flex flex-col gap-3.5">
          <div>
            <span className={`chip chip-${tone} text-[11px] font-semibold uppercase tracking-wide`}>
              {nudge.ruleId} · {rule?.title ?? 'Rule'}
            </span>
          </div>
          <p className="text-[17px] font-medium leading-normal tracking-[-0.005em]">{nudge.text}</p>
          <div className="flex items-center gap-2.5 text-[13px] text-[#475467]" aria-live="polite">
            {nudge.speaking ? (
              <>
                <span className="flex h-4 items-end gap-0.5" aria-hidden>
                  {[0, 1, 2, 3].map((i) => (
                    <span key={i} className="wave w-[3px] rounded-sm bg-[var(--mc-accent)]" style={{ height: [8, 14, 10, 16][i], animationDelay: `${i * 0.1}s` }} />
                  ))}
                </span>
                Speaking in the agent's headset
              </>
            ) : voiceOn ? (
              'Voice plays with the nudge'
            ) : (
              'Voice is off. The card still shows.'
            )}
          </div>
        </div>
      ) : (
        <p className="py-1 text-sm text-[var(--mc-muted)]">Quiet so far. The coach speaks up when a rule is at risk.</p>
      )}

      {hold && <div className="banner">Demo: the call is paused while the coach speaks</div>}
    </section>
  )
}

import { Check } from 'lucide-react'
import type { Finding } from '@/lib/events'
import { KIND_LABEL } from '@/lib/events'
import { absenceLine, tokId } from '@/lib/findings'
import type { Rule } from '@/lib/api'

export function scrollToFinding(f: Finding) {
  const el = document.getElementById(tokId(f.turn_idx, f.token_range[0]))
  if (!el) return
  const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  el.scrollIntoView({ block: 'center', behavior: calm ? 'auto' : 'smooth' })
  el.classList.add('tok-flash')
  window.setTimeout(() => el.classList.remove('tok-flash'), 1300)
}

interface Props {
  findings: Finding[]
  rules: Rule[]
  onOpen: (f: Finding) => void
  callTime?: string | null
}

export function FindingList({ findings: all, rules, onOpen, callTime }: Props) {
  const findings = all.filter((f) => f.kind !== 'good_practice')
  const good = all.length - findings.length
  return (
    <section aria-label="Findings" className="card flex min-h-0 flex-col gap-3 p-4 sm:p-5 lg:h-full">
      <div className="flex items-center justify-between">
        <h2 className="lbl">Findings</h2>
        <span className="text-xs text-[var(--mc-muted)]">{findings.length} this call</span>
      </div>
      {findings.length === 0 ? (
        <p className="text-sm text-[var(--mc-muted)]">Nothing flagged yet.</p>
      ) : (
        <ul className="findings-scroll flex min-h-0 flex-col overflow-y-auto">
          {findings.map((f) => {
            const ms = f.latency?.total_ms
            const title = rules.find((r) => r.id === f.rule_id)?.title ?? KIND_LABEL[f.kind]
            return (
              <li key={f.id} className="rise border-b border-[var(--mc-line-soft)] last:border-0">
                <button
                  onClick={() => {
                    scrollToFinding(f)
                    onOpen(f)
                  }}
                  className="flex w-full items-start gap-2.5 rounded-lg py-2.5 text-left hover:bg-[var(--mc-bg)]"
                >
                  <span className="sr-only">{KIND_LABEL[f.kind]}</span>
                  <span className={`chip chip-${f.kind} h-[22px]`}>{f.rule_id}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-medium">{title}</span>
                    <span lang={absenceLine(f, callTime) ? undefined : 'hi'} className="block truncate text-xs text-[var(--mc-muted)]">
                      {absenceLine(f, callTime) ?? (f.kind === 'violation' ? `“${f.quote}”` : `${KIND_LABEL[f.kind]} · “${f.quote}”`)}
                    </span>
                  </span>
                  <span className="mono flex-none text-right text-xs leading-snug text-[var(--mc-muted)]">
                    <span className="block">Turn {f.turn_idx}</span>
                    {typeof ms === 'number' && <span className="block">flagged in {(ms / 1000).toFixed(1)} s</span>}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
      {good > 0 && (
        <p className="flex flex-none items-center gap-2 rounded-[10px] bg-[var(--mc-good-practice-tint)] px-3 py-[9px] text-[12.5px] font-medium text-[var(--mc-good-practice-ink)]">
          <Check className="h-[15px] w-[15px] flex-none" strokeWidth={2.5} aria-hidden />
          {good} good-practice moment{good === 1 ? '' : 's'} in the transcript
        </p>
      )}
    </section>
  )
}

import { Check } from 'lucide-react'
import type { Finding } from '@/lib/events'
import { KIND_LABEL } from '@/lib/events'
import { tokId } from '@/lib/findings'
import type { Rule } from '@/lib/api'

const fmt = (ms: number) => {
  const s = Math.floor(ms / 1000)
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

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
  /** Start of a turn in the call, in ms, for the time on each row */
  offsetOf?: (turnIdx: number) => number | null
}

export function FindingList({ findings: all, rules, onOpen, offsetOf }: Props) {
  const findings = all.filter((f) => f.kind !== 'good_practice')
  const good = all.length - findings.length
  return (
    <section aria-label="Findings" className="card flex flex-col gap-3 p-4 sm:p-5">
      <div className="flex items-center justify-between">
        <h2 className="lbl">Findings</h2>
        <span className="text-xs text-[var(--mc-muted)]">{findings.length} this call</span>
      </div>
      {findings.length === 0 ? (
        <p className="text-sm text-[var(--mc-muted)]">Nothing flagged yet.</p>
      ) : (
        <ul className="flex flex-col">
          {findings.map((f) => {
            const at = offsetOf?.(f.turn_idx)
            const title = rules.find((r) => r.id === f.rule_id)?.title ?? KIND_LABEL[f.kind]
            return (
              <li key={f.id} className="rise border-b border-[var(--mc-line-soft)] last:border-0">
                <button
                  onClick={() => {
                    scrollToFinding(f)
                    onOpen(f)
                  }}
                  className="flex w-full items-start gap-2.5 rounded-lg py-2.5 text-left hover:bg-[var(--mc-bg)]"
                  aria-label={`${KIND_LABEL[f.kind]} ${f.rule_id}: ${title}. Open details`}
                >
                  <span className={`chip chip-${f.kind} h-[22px]`}>{f.rule_id}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-medium">{title}</span>
                    <span lang="hi" className="block truncate text-xs text-[var(--mc-muted)]">
                      {f.kind === 'violation' ? `“${f.quote}”` : `${KIND_LABEL[f.kind]} · “${f.quote}”`}
                    </span>
                  </span>
                  {at != null && <span className="mono text-xs text-[var(--mc-muted)]">{fmt(at)}</span>}
                </button>
              </li>
            )
          })}
        </ul>
      )}
      {good > 0 && (
        <p className="flex items-center gap-2 rounded-[10px] bg-[var(--mc-good-practice-tint)] px-3 py-[9px] text-[12.5px] font-medium text-[var(--mc-good-practice-ink)]">
          <Check className="h-[15px] w-[15px] flex-none" strokeWidth={2.5} aria-hidden />
          {good} good-practice moment{good === 1 ? '' : 's'}, highlighted green in the transcript
        </p>
      )}
    </section>
  )
}

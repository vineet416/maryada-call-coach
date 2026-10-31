import type { Finding } from '@/lib/events'
import { KIND_LABEL } from '@/lib/events'
import { KIND_COLOR, tokId } from '@/lib/findings'
import type { Rule } from '@/lib/api'

const DECOR = { violation: 'solid', advisory: 'dotted', needs_review: 'dashed', good_practice: 'none' } as const

export function scrollToFinding(f: Finding) {
  const el = document.getElementById(tokId(f.turn_idx, f.token_range[0]))
  if (!el) return
  el.scrollIntoView({ block: 'center', behavior: 'smooth' })
  el.classList.add('tok-flash')
  window.setTimeout(() => el.classList.remove('tok-flash'), 1300)
}

export function FindingList({ findings: all, rules, onOpen }: { findings: Finding[]; rules: Rule[]; onOpen: (f: Finding) => void }) {
  const findings = all.filter((f) => f.kind !== 'good_practice')
  const good = all.length - findings.length
  return (
    <section aria-label="Findings" className="rounded-2xl border border-[var(--mc-line)] bg-[var(--mc-surface)] p-4">
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--mc-muted)]">Findings</h2>
      {findings.length === 0 ? (
        <p className="text-sm text-[var(--mc-muted)]">Nothing flagged yet.</p>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {findings.map((f) => (
            <li key={f.id} className="rise">
              <button
                onClick={() => {
                  scrollToFinding(f)
                  onOpen(f)
                }}
                title={`${KIND_LABEL[f.kind]}: ${rules.find((r) => r.id === f.rule_id)?.title ?? f.rule_id}`}
                className="flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs hover:brightness-125"
                style={{ borderColor: KIND_COLOR[f.kind], color: KIND_COLOR[f.kind], borderStyle: DECOR[f.kind] === 'none' ? 'solid' : DECOR[f.kind] }}
              >
                <span className="font-semibold">{f.rule_id}</span>
                <span className="text-[var(--mc-text)]">{rules.find((r) => r.id === f.rule_id)?.title ?? KIND_LABEL[f.kind]}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {good > 0 && (
        <p className="mt-3 text-xs" style={{ color: 'var(--mc-good-practice)' }}>
          ✓ {good} good-practice moment{good === 1 ? '' : 's'} (highlighted green in the transcript)
        </p>
      )}
    </section>
  )
}

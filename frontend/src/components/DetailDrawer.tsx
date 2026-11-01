import { Check, Copy, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { Rule } from '@/lib/api'
import type { Finding } from '@/lib/events'
import { KIND_LABEL } from '@/lib/events'
import { SOURCE_LABEL, confidenceLabel } from '@/lib/findings'

const QUOTE_BG = {
  violation: 'bg-[var(--mc-violation-tint)]',
  advisory: 'bg-[var(--mc-advisory-tint)]',
  needs_review: 'bg-[var(--mc-needs-review-tint)]',
  good_practice: 'bg-[var(--mc-good-practice-tint)]',
} as const

/** Right-side drawer on desktop, bottom sheet on mobile. Esc or a tap outside closes it. */
export function DetailDrawer({ finding, rule, onClose }: { finding: Finding | null; rule?: Rule; onClose: () => void }) {
  const closeBtn = useRef<HTMLButtonElement>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!finding) return
    const opener = document.activeElement as HTMLElement | null
    closeBtn.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    setCopied(false)
    return () => {
      window.removeEventListener('keydown', onKey)
      opener?.focus?.()
    }
  }, [finding, onClose])

  if (!finding) return null
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(finding.rewrite)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard may be blocked; the text stays selectable */
    }
  }
  const latency = finding.latency?.total_ms

  return (
    <div className="fixed inset-0 z-40" role="presentation" onClick={onClose}>
      <div className="absolute inset-0 bg-[#0f172a]/40" />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`${rule?.title ?? finding.rule_id} details`}
        onClick={(e) => e.stopPropagation()}
        className="absolute inset-x-0 bottom-0 flex max-h-[88vh] flex-col overflow-hidden rounded-t-2xl bg-white shadow-[0_-16px_48px_rgb(15_23_42/0.18)] sm:inset-y-0 sm:left-auto sm:right-0 sm:max-h-none sm:w-[500px] sm:rounded-none sm:shadow-[-16px_0_48px_rgb(15_23_42/0.18)]"
        style={{ animation: 'sheet-in 0.25s ease both' }}
      >
        <div className="flex items-center justify-between gap-3 border-b border-[#eaecf0] px-5 py-5 sm:px-6">
          <div className="flex min-w-0 items-center gap-2.5">
            <span className={`chip chip-${finding.kind}`}>{finding.rule_id}</span>
            <h2 className="text-base font-semibold leading-snug">{rule?.title ?? finding.rule_id}</h2>
          </div>
          <button
            ref={closeBtn}
            onClick={onClose}
            aria-label="Close details"
            className="flex h-[34px] w-[34px] flex-none items-center justify-center rounded-[9px] border border-[var(--mc-line)] bg-white hover:bg-[var(--mc-line-soft)]"
          >
            <X className="h-4 w-4 text-[#475467]" aria-hidden />
          </button>
        </div>

        <div className="flex flex-col gap-[22px] overflow-y-auto p-5 sm:p-6">
          <div className="flex flex-wrap gap-2">
            <span className={`chip chip-${finding.kind} font-semibold`}>{KIND_LABEL[finding.kind]}</span>
            <span className="chip">Agent turn {finding.turn_idx}</span>
            <span className="chip">Confidence: {confidenceLabel(finding)}</span>
            {(finding.rbi_ref || rule?.rbi_ref) && <span className="chip mono">RBI para {finding.rbi_ref || rule?.rbi_ref}</span>}
          </div>

          <Block title="What the agent said">
            <blockquote lang="hi" className={`rounded-xl px-4 py-3.5 text-[17px] leading-[1.8] ${QUOTE_BG[finding.kind]}`}>
              “<span className={`tok tok-${finding.kind}`}>{finding.quote}</span>”
            </blockquote>
          </Block>

          {finding.reason && <Block title="Why it is flagged"><p className="text-sm leading-relaxed text-[var(--mc-text-2)]">{finding.reason}</p></Block>}
          {rule?.why && (
            <Block title="Why this matters">
              <p className="whitespace-pre-line text-sm leading-relaxed text-[var(--mc-text-2)]">{rule.why}</p>
            </Block>
          )}

          {finding.rewrite && (
            <Block title="Suggested rewording">
              <div className="rounded-xl bg-[var(--mc-good-practice-tint)] px-4 py-3.5">
                <p lang="hi" className="text-[15px] leading-[1.8] text-[#054f31]">“{finding.rewrite}”</p>
                <button onClick={copy} className="mt-2 flex items-center gap-1.5 text-xs font-semibold text-[var(--mc-good-practice-ink)]">
                  {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  {copied ? 'Copied' : 'Copy'}
                </button>
              </div>
            </Block>
          )}

          <Block title="How it was detected">
            <dl className="overflow-hidden rounded-xl border border-[#eaecf0] text-[13px]">
              <div className="flex justify-between border-b border-[#eaecf0] px-3.5 py-2.5">
                <dt className="text-[var(--mc-muted)]">Found by</dt>
                <dd className="font-semibold">{SOURCE_LABEL[finding.source]}</dd>
              </div>
              <div className={`flex justify-between px-3.5 py-2.5 ${latency ? 'border-b border-[#eaecf0]' : ''}`}>
                <dt className="text-[var(--mc-muted)]">Confidence</dt>
                <dd className="font-semibold">{confidenceLabel(finding)}</dd>
              </div>
              {latency ? (
                <div className="flex justify-between px-3.5 py-2.5">
                  <dt className="text-[var(--mc-muted)]">Time to flag</dt>
                  <dd className="mono font-semibold">{(latency / 1000).toFixed(1)} s</dd>
                </div>
              ) : null}
            </dl>
          </Block>

          <p className="text-xs leading-normal text-[var(--mc-muted)]">Illustrative guidance for a synthetic demo. Not legal advice.</p>
        </div>
      </aside>
    </div>
  )
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="lbl">{title}</h3>
      {children}
    </section>
  )
}

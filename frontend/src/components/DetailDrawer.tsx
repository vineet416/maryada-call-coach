import { Check, Copy, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { Rule } from '@/lib/api'
import type { Finding } from '@/lib/events'
import { KIND_LABEL } from '@/lib/events'
import { KIND_COLOR, SOURCE_LABEL, confidenceLabel } from '@/lib/findings'

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
  const color = KIND_COLOR[finding.kind]
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(finding.rewrite)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard may be blocked; the text stays selectable */
    }
  }

  return (
    <div className="fixed inset-0 z-40" role="presentation" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50" />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`${rule?.title ?? finding.rule_id} details`}
        onClick={(e) => e.stopPropagation()}
        className="absolute inset-x-0 bottom-0 max-h-[85vh] overflow-y-auto rounded-t-2xl border-t border-[var(--mc-line)] bg-[var(--mc-surface)] p-5 shadow-2xl sm:inset-y-0 sm:left-auto sm:right-0 sm:max-h-none sm:w-[420px] sm:rounded-none sm:border-l sm:border-t-0"
        style={{ animation: 'sheet-in 0.25s ease both' }}
      >
        <div className="mb-3 flex items-start gap-3">
          <div className="flex-1">
            <p className="mb-1 flex flex-wrap items-center gap-2 text-xs">
              <span className="rounded px-1.5 py-0.5 font-semibold" style={{ color, background: `color-mix(in srgb, ${color} 14%, transparent)` }}>
                {KIND_LABEL[finding.kind]}
              </span>
              <span className="text-[var(--mc-muted)]">{finding.rule_id}</span>
            </p>
            <h2 className="text-lg font-semibold leading-snug">{rule?.title ?? finding.rule_id}</h2>
            {(finding.rbi_ref || rule?.rbi_ref) && (
              <p className="mono mt-0.5 text-xs text-[var(--mc-muted)]">RBI para {finding.rbi_ref || rule?.rbi_ref}</p>
            )}
          </div>
          <button ref={closeBtn} onClick={onClose} aria-label="Close details" className="rounded-md p-1.5 hover:bg-[var(--mc-line)]">
            <X className="h-4 w-4" />
          </button>
        </div>

        <Block title="What was said">
          <blockquote lang="hi" className="border-l-2 pl-3 leading-[1.7]" style={{ borderColor: color, fontFamily: 'var(--font-transcript)' }}>
            {finding.quote}
          </blockquote>
        </Block>

        {finding.reason && <Block title="Why it was flagged">{finding.reason}</Block>}
        {rule?.why && <Block title="Why this matters"><span className="whitespace-pre-line">{rule.why}</span></Block>}

        {finding.rewrite && (
          <Block title="Try saying instead">
            <div className="rounded-lg border border-[var(--mc-good-practice)]/40 bg-[var(--mc-good-practice)]/8 p-3">
              <p lang="hi" className="leading-[1.7]" style={{ fontFamily: 'var(--font-transcript)' }}>
                {finding.rewrite}
              </p>
              <button onClick={copy} className="mt-2 flex items-center gap-1.5 text-xs text-[var(--mc-good-practice)]">
                {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
          </Block>
        )}

        <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-2 border-t border-[var(--mc-line)] pt-3 text-xs">
          <div>
            <dt className="text-[var(--mc-muted)]">Confidence</dt>
            <dd className="font-medium">{confidenceLabel(finding)}</dd>
          </div>
          <div>
            <dt className="text-[var(--mc-muted)]">Found by</dt>
            <dd className="font-medium">{SOURCE_LABEL[finding.source]}</dd>
          </div>
        </dl>
      </aside>
    </div>
  )
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-4">
      <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-[var(--mc-muted)]">{title}</h3>
      <div className="text-sm">{children}</div>
    </section>
  )
}

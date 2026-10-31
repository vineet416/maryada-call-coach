import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { Rule } from '@/lib/api'
import type { Finding } from '@/lib/events'
import type { Summary } from '@/store/sessionStore'

interface Props {
  summary: Summary
  findings: Finding[]
  rules: Rule[]
  onRunAgain: () => void
  onClose: () => void
}

export function SummaryModal({ summary, findings, rules, onRunAgain, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const [copied, setCopied] = useState(false)
  const good = findings.filter((f) => f.kind === 'good_practice').length

  useEffect(() => {
    ref.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const share = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard may be blocked */
    }
  }
  const rows = Object.entries(summary.by_rule)

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/60 p-0 sm:items-center sm:p-4" onClick={onClose}>
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label="Call summary"
        onClick={(e) => e.stopPropagation()}
        className="rise w-full max-w-md rounded-t-2xl border border-[var(--mc-line)] bg-[var(--mc-surface)] p-6 sm:rounded-2xl"
      >
        <h2 className="text-lg font-semibold">{summary.stopped ? 'Call stopped' : 'Call complete'}</h2>
        <div className="my-4 grid grid-cols-3 gap-3 text-center">
          <Stat label="Risk peak" value={String(summary.risk_peak)} />
          <Stat label="Findings" value={String(summary.findings_count)} />
          <Stat label="Went well" value={String(good)} />
        </div>
        {rows.length > 0 && (
          <ul className="mb-4 divide-y divide-[var(--mc-line)] rounded-lg border border-[var(--mc-line)] text-sm">
            {rows.map(([id, n]) => (
              <li key={id} className="flex justify-between px-3 py-2">
                <span>
                  <span className="mono mr-2 text-[var(--mc-muted)]">{id}</span>
                  {rules.find((r) => r.id === id)?.title ?? id}
                </span>
                <span className="mono">{n}</span>
              </li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap gap-2">
          <button onClick={onRunAgain} className="rounded-md bg-[var(--mc-accent)] px-4 py-2 text-sm font-medium text-white hover:brightness-110">
            Run again
          </button>
          <Link to="/eval" className="rounded-md border border-[var(--mc-line)] px-4 py-2 text-sm hover:bg-[var(--mc-line)]">
            See evaluation
          </Link>
          <button onClick={share} className="rounded-md border border-[var(--mc-line)] px-4 py-2 text-sm hover:bg-[var(--mc-line)]">
            {copied ? 'Link copied' : 'Share this'}
          </button>
          <button onClick={onClose} className="ml-auto px-2 py-2 text-sm text-[var(--mc-muted)] hover:text-[var(--mc-text)]">
            Review transcript
          </button>
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-[var(--mc-bg)] py-3">
      <div className="mono text-2xl font-semibold">{value}</div>
      <div className="text-[11px] text-[var(--mc-muted)]">{label}</div>
    </div>
  )
}

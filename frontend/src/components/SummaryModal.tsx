import { X } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import type { Rule, ScenarioDetail } from '@/lib/api'
import type { Finding } from '@/lib/events'
import { useFocusTrap } from '@/lib/useFocusTrap'
import { useNextRecorded } from '@/lib/useNextRecorded'
import type { Mode, Summary } from '@/store/sessionStore'

interface Props {
  scenario: ScenarioDetail
  summary: Summary
  findings: Finding[]
  rules: Rule[]
  mode: Mode
  onRunAgain: () => void
  onClose: () => void
}

const len = (ms: number | null) => {
  if (!ms) return ''
  const s = Math.round(ms / 1000)
  return s >= 60 ? `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, '0')} s` : `${s} s`
}

export function SummaryModal({ scenario, summary, findings, rules, mode, onRunAgain, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const good = findings.filter((f) => f.kind === 'good_practice').length
  const flagged = findings.filter((f) => f.kind !== 'good_practice')
  const violations = flagged.filter((f) => f.kind === 'violation').length

  useFocusTrap(ref, true, () => document.getElementById('call-transcript'))
  useEffect(() => {
    ref.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const next = useNextRecorded(scenario.id)

  const rows = Object.entries(summary.by_rule)

  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center overflow-y-auto bg-[#0f172a]/40 sm:items-start sm:px-6 sm:pt-16" onClick={onClose}>
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label="Call summary"
        onClick={(e) => e.stopPropagation()}
        className="rise flex outline-none max-h-[92vh] w-full max-w-[760px] flex-col overflow-hidden rounded-t-[18px] bg-white shadow-[0_24px_64px_rgb(15_23_42/0.28)] sm:max-h-none sm:rounded-[18px]"
      >
        <div className="flex items-start justify-between gap-4 border-b border-[#eaecf0] px-5 pb-4 pt-5 sm:px-7 sm:pt-6">
          <div className="min-w-0">
            <div className="lbl">Call summary · {scenario.id.toUpperCase()}</div>
            <h2 className="mb-0.5 mt-1 text-xl font-semibold tracking-tight sm:text-[22px]">{summary.stopped ? 'Call stopped' : 'Call complete'}</h2>
            <p className="text-[13px] text-[var(--mc-muted)]">
              {scenario.title} · {mode === 'replay' ? 'Recorded run' : 'Live call'}
              {scenario.duration_ms ? ` · ${len(scenario.duration_ms)}` : ''}
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close summary"
            className="flex h-[34px] w-[34px] flex-none items-center justify-center rounded-[9px] border border-[var(--mc-line)] bg-white hover:bg-[var(--mc-line-soft)]"
          >
            <X className="h-4 w-4 text-[#475467]" aria-hidden />
          </button>
        </div>

        <div className="flex flex-col gap-6 overflow-y-auto px-5 py-5 sm:px-7 sm:py-6">
          <div className="grid grid-cols-3 gap-3">
            <Stat label="Peak risk" value={String(summary.risk_peak)} tone="bg-[#f9fafb]" ink="text-[var(--mc-text)]" note="out of 100" />
            <Stat
              label="Findings"
              value={String(summary.findings_count)}
              tone="bg-[var(--mc-violation-tint)]"
              ink="text-[var(--mc-violation-ink)]"
              note={`${violations} violation${violations === 1 ? '' : 's'}, ${flagged.length - violations} other`}
            />
            <Stat label="Went well" value={String(good)} tone="bg-[var(--mc-good-practice-tint)]" ink="text-[var(--mc-good-practice-ink)]" note="good-practice moments" />
          </div>

          {rows.length > 0 && (
            <div className="flex flex-col gap-3">
              <span className="lbl">Findings by rule</span>
              <ul className="flex flex-col gap-2.5">
                {rows.map(([id, n]) => (
                  <li key={id} className="flex items-center gap-2.5">
                    <span className={`chip chip-${flagged.find((f) => f.rule_id === id)?.kind ?? 'violation'} h-[22px]`}>{id}</span>
                    <span className="flex-1 text-[13px]">{rules.find((r) => r.id === id)?.title ?? id}</span>
                    <b className="mono font-semibold">{n}</b>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#eaecf0] bg-[#f9fafb] px-5 py-4 sm:px-7">
          <span className="text-xs text-[var(--mc-muted)]">Synthetic call. Detections are by Maryada, not a legal finding.</span>
          <div className="flex flex-wrap gap-2.5">
            <button onClick={onClose} className="btn">Review transcript</button>
            <Link to="/" className="btn">Back to cases</Link>
            {next && (
              <Link to={`/call/${next}`} className="btn">Try another recorded run</Link>
            )}
            <button onClick={onRunAgain} className="btn btn-primary">Run again</button>
          </div>
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value, tone, ink, note }: { label: string; value: string; tone: string; ink: string; note: string }) {
  return (
    <div className={`rounded-xl px-4 py-3.5 ${tone}`}>
      <div className={`lbl ${ink}`}>{label}</div>
      <div className={`mono text-[28px] font-bold leading-tight tracking-tight ${ink}`}>{value}</div>
      <div className={`text-xs ${ink === 'text-[var(--mc-text)]' ? 'text-[var(--mc-muted)]' : ink}`}>{note}</div>
    </div>
  )
}

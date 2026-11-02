import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { Bubble } from '@/components/Bubble'
import { DetailDrawer } from '@/components/DetailDrawer'
import { ErrorCard } from '@/components/ErrorCard'
import { ModeBadge } from '@/components/ModeBadge'
import { RiskChart } from '@/components/report/RiskChart'
import { ApiError, getReport, getRules, getSessionReport, type CallReport as Report, type Rule } from '@/lib/api'
import type { Finding } from '@/lib/events'
import { KIND_LABEL } from '@/lib/events'
import { absenceLine } from '@/lib/findings'
import { clock, shortDate, spoken } from '@/lib/format'
import { usePageTitle } from '@/lib/usePageTitle'
import { useNextRecorded } from '@/lib/useNextRecorded'
import type { TurnView } from '@/store/sessionStore'

type State = { kind: 'loading' } | { kind: 'ready'; report: Report; rules: Rule[] } | { kind: 'gone' } | { kind: 'error'; message: string }

const QUOTE_BG = {
  violation: 'bg-[var(--mc-violation-tint)]',
  advisory: 'bg-[var(--mc-advisory-tint)]',
  needs_review: 'bg-[var(--mc-needs-review-tint)]',
  good_practice: 'bg-[var(--mc-good-practice-tint)]',
} as const

// Whether the last input was the keyboard: only then does the focused heading show its ring
let lastInputKeyboard = false
if (typeof window !== 'undefined') {
  window.addEventListener('keydown', () => (lastInputKeyboard = true), true)
  window.addEventListener('pointerdown', () => (lastInputKeyboard = false), true)
}

const BAND_LABEL = { low: 'Low band', medium: 'Medium band', high: 'High band' } as const
const LEGEND = ['violation', 'advisory', 'needs_review', 'good_practice'] as const

/** Summary of one finished call, built from the call's events. A recorded run is rebuilt from its saved events, so a refresh works. */
export function CallReport({ live = false }: { live?: boolean }) {
  const params = useParams()
  const id = (live ? params.sid : params.id) ?? ''
  const notice = (useLocation().state as { notice?: string } | null)?.notice
  const [state, setState] = useState<State>({ kind: 'loading' })
  const [open, setOpen] = useState<Finding | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const next = useNextRecorded(live ? '' : id)
  usePageTitle(live ? 'Speak live call report · Maryada' : `${id.toUpperCase() || 'Call'} call report · Maryada`)

  const load = useCallback(() => {
    setState({ kind: 'loading' })
    const ctl = new AbortController()
    Promise.all([live ? getSessionReport(id, ctl.signal) : getReport(id, ctl.signal), getRules(ctl.signal)])
      .then(([report, rules]) => setState({ kind: 'ready', report, rules }))
      .catch((e: Error) => {
        if (e.name === 'AbortError') return
        setState(e instanceof ApiError && e.code === 'no_report' ? { kind: 'gone' } : { kind: 'error', message: e.message })
      })
    return () => ctl.abort()
  }, [id, live])

  useEffect(() => load(), [load])
  useEffect(() => {
    if (state.kind === 'ready') {
      window.scrollTo(0, 0)
      heading.current?.toggleAttribute('data-kbd', lastInputKeyboard)
      heading.current?.focus({ preventScroll: true })
    }
  }, [state.kind])

  const closeDrawer = useCallback(() => setOpen(null), [])
  const turns = useMemo<TurnView[]>(
    () =>
      state.kind !== 'ready'
        ? []
        : state.report.turns.map((t) => {
            const first = t.tokens[0]?.i ?? 0
            return {
              idx: t.idx,
              speaker: t.speaker,
              audioUrl: '',
              durationMs: t.duration_ms,
              tokens: t.tokens.map((k) => ({ ...k, d: k.i - first, n: t.tokens.length })),
              analysing: false,
              ended: true,
              instant: true,
              startedAt: 0,
            }
          }),
    [state],
  )

  if (state.kind === 'loading')
    return (
      <div aria-busy="true" className="space-y-5">
        <p role="status" className="text-sm font-medium text-[var(--mc-muted)]">Loading the call report… the server may take a few seconds to wake up.</p>
        <div className="skeleton h-32" />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">{[0, 1, 2, 3].map((k) => <div key={k} className="skeleton h-24" />)}</div>
        <div className="skeleton h-64" />
      </div>
    )

  if (state.kind === 'gone')
    return (
      <section role="status" className="card rise mx-auto flex max-w-md flex-col items-center gap-2.5 p-8 text-center">
        <h1 className="text-[17px] font-semibold tracking-tight">This report is no longer available</h1>
        <p className="max-w-[300px] text-[13.5px] leading-relaxed text-[var(--mc-muted)]">Reports are not saved. Run the call again to see it.</p>
        <Link to={live ? '/speak' : '/'} className="btn btn-primary mt-1.5">{live ? 'Speak live again' : 'Back to cases'}</Link>
      </section>
    )

  if (state.kind === 'error')
    return (
      <ErrorCard title="Could not load the report" message={state.message} onRetry={load}>
        <Link to="/" className="btn">Back to cases</Link>
      </ErrorCard>
    )

  const { report, rules } = state
  const { scenario, kpis, by_rule: byRule, coaching, good } = report
  const recorded = report.source === 'replay'
  const turnAt = (n: number) => report.turns.find((t) => t.idx === n)?.offset_ms ?? 0
  const rule = (f: Finding | null) => rules.find((r) => r.id === f?.rule_id)
  const subline = [
    recorded ? 'Recorded run' : 'Live call',
    scenario.duration_ms ? spoken(scenario.duration_ms) : null,
    scenario.call_date && !live ? `call dated ${shortDate(scenario.call_date)}` : null,
  ].filter(Boolean)
  const jumpToTranscript = () => {
    const el = document.getElementById('report-transcript')
    el?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' })
    el?.focus({ preventScroll: true })
  }

  return (
    <div className="mx-auto flex max-w-[1100px] flex-col gap-5 sm:gap-6">
      <header className="card flex flex-col gap-4 p-4 sm:px-6 sm:py-5">
        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
          <div className="flex min-w-0 flex-col gap-1">
            <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-1.5 text-xs text-[var(--mc-muted)]">
              <Link to="/" className="link !font-normal">Cases</Link>
              <span aria-hidden>/</span>
              {live ? (
                <Link to="/speak" className="link !font-normal">Speak live</Link>
              ) : (
                <Link to={`/call/${scenario.id}`} className="link !font-normal">{scenario.id.toUpperCase()}</Link>
              )}
              <span aria-hidden>/</span>
              <span aria-current="page">Call report</span>
            </nav>
            <h1 ref={heading} tabIndex={-1} className="text-xl font-semibold leading-tight tracking-tight sm:text-2xl">{scenario.title}</h1>
            <p className="flex flex-wrap items-center gap-2 text-[13px] text-[var(--mc-muted)]">
              {recorded && <ModeBadge mode="replay" status="ended" />}
              <span>{subline.join(' · ')}</span>
            </p>
          </div>
          <div className="flex flex-wrap gap-2.5">
            <button type="button" onClick={jumpToTranscript} className="btn">Review transcript</button>
            {live ? (
              <>
                <Link to={next ? `/call/${next}` : '/'} className="btn">Try a recorded run</Link>
                <Link to="/speak" className="btn btn-primary">Speak again</Link>
              </>
            ) : (
              <>
                <Link to={next ? `/call/${next}` : '/'} className="btn">Try another call</Link>
                <Link to={`/call/${scenario.id}`} className="btn btn-primary">Run again</Link>
              </>
            )}
          </div>
        </div>
      </header>

      {notice && <p role="status" className="banner banner-warn">{notice}</p>}

      <section aria-label="Key figures" className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <Kpi label="Peak risk" value={String(kpis.peak_risk)} note={BAND_LABEL[kpis.peak_band]} tone="bg-[#f9fafb]" ink="text-[var(--mc-text)]" />
        <Kpi label="Findings" value={String(kpis.findings_count)} note={kpis.findings_count === 1 ? 'flag raised' : 'flags raised'}
          tone={kpis.findings_count ? 'bg-[var(--mc-violation-tint)]' : 'bg-[#f9fafb]'} ink={kpis.findings_count ? 'text-[var(--mc-violation-ink)]' : 'text-[var(--mc-text)]'} />
        <Kpi label="Good practice" value={String(kpis.good_count)} note={kpis.good_count === 1 ? 'moment' : 'moments'} tone="bg-[var(--mc-good-practice-tint)]" ink="text-[var(--mc-good-practice-ink)]" />
        <Kpi
          label="Time to first flag"
          value={kpis.first_flag_ms === null ? 'None' : clock(kpis.first_flag_ms)}
          note={kpis.first_flag_ms === null ? 'nothing was flagged' : 'from the start of the call'}
          tone="bg-[#f9fafb]"
          ink="text-[var(--mc-text)]"
        />
      </section>

      <Panel id="risk-h" title="Risk over time" hint="Risk after each agent turn. Markers show when a flag appeared.">
        <RiskChart report={report} />
        {report.flags.length > 0 && (
          <ol className="mt-3 flex flex-col gap-1.5 border-t border-[#eaecf0] pt-3 text-[13px]" aria-label="Flags in order">
            {report.flags.map((f) => (
              <li key={f.finding_id} className="flex flex-wrap items-center gap-2">
                <span className="mono w-12 text-[var(--mc-muted)]">{clock(f.t_ms)}</span>
                <span className={`chip chip-${f.kind} h-[22px]`}>{f.rule_id}</span>
                <span>{rules.find((r) => r.id === f.rule_id)?.title ?? f.rule_id}</span>
                <span className="text-[var(--mc-muted)]">· {KIND_LABEL[f.kind]}</span>
              </li>
            ))}
          </ol>
        )}
      </Panel>

      <Panel id="rules-h" title="Findings by rule">
        {byRule.length === 0 ? (
          <p className="text-sm text-[var(--mc-text-2)]">No rule was flagged in this call.</p>
        ) : (
          <ul className="flex flex-col gap-2.5">
            {byRule.map((r) => (
              <li key={r.rule_id} className="flex items-center gap-2.5">
                <span className={`chip chip-${r.kind} h-[22px]`}>{r.rule_id}</span>
                <span className="flex-1 text-[13.5px]">{r.title}</span>
                <b className="mono font-semibold">{r.count}</b>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <section aria-labelledby="transcript-h" className="card">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#eaecf0] px-4 py-3 sm:px-6">
          <h2 id="transcript-h" className="text-[15px] font-semibold">Transcript</h2>
          <ul className="flex flex-wrap gap-x-3.5 gap-y-1 text-xs text-[#475467]" aria-label="Legend">
            {LEGEND.map((k) => (
              <li key={k}><span className={`tok tok-${k}`}>{KIND_LABEL[k]}</span></li>
            ))}
          </ul>
        </div>
        <div id="report-transcript" tabIndex={-1} aria-label="Call transcript" className="flex flex-col gap-[18px] px-4 py-4 outline-none sm:px-6">
          {turns.map((t) => (
            <Bubble key={t.idx} turn={t} offsetMs={turnAt(t.idx)} findings={report.findings} onOpen={setOpen} you={live} />
          ))}
        </div>
      </section>

      <Panel id="coach-h" title="Coaching cards">
        {coaching.length === 0 ? (
          <p className="text-sm text-[var(--mc-text-2)]">Nothing was flagged, so there is nothing to coach.</p>
        ) : (
          <ul className="flex flex-col gap-4">
            {coaching.map((c) => {
              const f = c.finding
              const absence = absenceLine(f, scenario.call_time)
              return (
                <li key={f.id}>
                  <article className="flex flex-col gap-3.5 rounded-xl border border-[var(--mc-line)] p-4 sm:p-5" aria-label={`${c.rule_title}, turn ${f.turn_idx}`}>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`chip chip-${f.kind}`}>{f.rule_id}</span>
                      <h3 className="text-[15px] font-semibold">{c.rule_title}</h3>
                      <span className={`chip chip-${f.kind} font-semibold`}>{KIND_LABEL[f.kind]}</span>
                      <span className="text-xs text-[var(--mc-muted)]">Agent turn {f.turn_idx} · <span className="mono">{clock(turnAt(f.turn_idx))}</span></span>
                    </div>
                    <Field label={absence ? 'What was found' : 'What the agent said'}>
                      {absence ? (
                        <p className={`rounded-lg px-3.5 py-3 text-[14px] leading-relaxed ${QUOTE_BG[f.kind]}`}>{absence}</p>
                      ) : (
                        <blockquote lang="hi" className={`rounded-lg px-3.5 py-3 text-[16px] leading-[1.8] ${QUOTE_BG[f.kind]}`}>
                          “<span className={`tok tok-${f.kind}`}>{f.quote}</span>”
                        </blockquote>
                      )}
                    </Field>
                    {c.why && <Field label="Why it matters"><p className="whitespace-pre-line text-[13.5px] leading-relaxed text-[var(--mc-text-2)]">{c.why}</p></Field>}
                    {c.coach_line && <Field label="Coach said"><p className="text-[14px] leading-relaxed">{c.coach_line}</p></Field>}
                    {c.rewrite && (
                      <Field label="Suggested rewording">
                        <p lang="hi" className="rounded-lg bg-[var(--mc-good-practice-tint)] px-3.5 py-3 text-[15px] leading-[1.8] text-[#054f31]">“{c.rewrite}”</p>
                      </Field>
                    )}
                  </article>
                </li>
              )
            })}
          </ul>
        )}
      </Panel>

      <Panel id="good-h" title="What went well">
        {good.length === 0 ? (
          <p className="text-sm text-[var(--mc-text-2)]">No good-practice moments were detected in this call.</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {good.map((g) => (
              <li key={g.finding.id} className="flex flex-col gap-1.5">
                <span className="text-xs text-[var(--mc-muted)]">Agent turn {g.finding.turn_idx} · <span className="mono">{clock(turnAt(g.finding.turn_idx))}</span></span>
                <blockquote lang="hi" className={`rounded-lg px-3.5 py-3 text-[15px] leading-[1.8] ${QUOTE_BG.good_practice}`}>“{g.finding.quote}”</blockquote>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <p className="text-center text-xs text-[var(--mc-muted)]">{live ? 'Your own spoken call. ' : 'Synthetic call. '}Detections are by Maryada, not a legal finding.</p>

      <DetailDrawer finding={open} rule={rule(open)} onClose={closeDrawer} callTime={scenario.call_time} />
    </div>
  )
}

function Kpi({ label, value, note, tone, ink }: { label: string; value: string; note: string; tone: string; ink: string }) {
  return (
    <div className={`rounded-xl px-4 py-3.5 ${tone}`}>
      <div className={`lbl ${ink}`}>{label}</div>
      <div className={`mono text-[28px] font-bold leading-tight tracking-tight ${ink}`}>{value}</div>
      <div className={`text-xs ${ink === 'text-[var(--mc-text)]' ? 'text-[var(--mc-muted)]' : ink}`}>{note}</div>
    </div>
  )
}

function Panel({ id, title, hint, children }: { id: string; title: string; hint?: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="card flex flex-col gap-3 p-4 sm:p-6">
      <div>
        <h2 id={id} className="text-[15px] font-semibold">{title}</h2>
        {hint && <p className="mt-0.5 text-xs text-[var(--mc-muted)]">{hint}</p>}
      </div>
      {children}
    </section>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="lbl">{label}</span>
      {children}
    </div>
  )
}

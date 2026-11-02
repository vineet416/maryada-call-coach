import { useCallback, useEffect, useState } from 'react'
import { ErrorCard } from '@/components/ErrorCard'
import { Switch } from '@/components/Switch'
import {
  getEval,
  getRules,
  type EvalPayload,
  type EvalResults,
  type Prf,
  type Rule,
  type RunResult,
  type ScoreBlock,
} from '@/lib/api'
import { usePageTitle } from '@/lib/usePageTitle'

/** Noise conditions in the order shown: clean first, then the least noise first. Only conditions with a full-engine run are shown. */
const snrOf = (id: string) => (id === 'clean' ? Infinity : Number(id.replace(/\D/g, '')) || 0)
const condLabel = (id: string) => (id === 'clean' ? 'Clean audio' : /^snr\d+$/.test(id) ? `${id.slice(3)} dB` : id)
const f2 = (x: number | null) => (x === null ? '–' : x.toFixed(2))
const ratio = (num: number, den: number) => `${num} of ${den}`
const NOTES_URL = 'https://github.com/vineet416/maryada-call-coach/blob/main/docs/EVAL-NOTES.md'
const dateOf = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
const seconds = (ms: number | null | undefined) => (ms == null ? null : `${(ms / 1000).toFixed(1)} s`)
const found = (p: Prf) => ratio(p.tp, p.tp + p.fn)

/** The one run the headline is about: the full engine on clean audio, all calls. */
const FULL = 'full'
const CLEAN = 'clean'

export function Evaluation() {
  usePageTitle('Evaluation · Maryada')
  const [data, setData] = useState<EvalPayload | null>(null)
  const [rules, setRules] = useState<Rule[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setError(null)
    setData(null)
    const ctl = new AbortController()
    getEval(ctl.signal)
      .then(setData)
      .catch((e: Error) => e.name !== 'AbortError' && setError(e.message))
    getRules(ctl.signal)
      .then(setRules)
      .catch(() => undefined) // rule names are only labels; the page works without them
    return () => ctl.abort()
  }, [])
  useEffect(() => load(), [load])

  if (error) return <ErrorCard message={error} onRetry={load} />
  if (!data) {
    return (
      <div className="space-y-5" aria-busy="true" aria-label="Loading the evaluation">
        <div className="skeleton h-16" />
        <div className="grid items-start gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-28" />)}
        </div>
        <div className="skeleton h-80" />
      </div>
    )
  }

  const results = data.results
  const run = results?.[FULL]?.[CLEAN] ?? null
  const all = run?.all ?? null
  const rowOf = (label: string) => data.latency.rows.find((r) => r.label === label)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[28px] font-bold tracking-[-0.025em]">Evaluation</h1>
          <p className="mt-0.5 max-w-[720px] text-sm text-[var(--mc-muted)]">
            How well Maryada finds rule violations in {results ? results.n_calls : 'the'} labelled synthetic calls. Numbers are read from the saved results.
          </p>
        </div>
        {results && (
          <span className="chip chip-warn" title="Saved results, not a live run">
            Results saved {dateOf(results.generated_at)}
          </span>
        )}
      </div>

      {!results || !run || !all ? (
        <section className="card p-6" role="status">
          <h2 className="text-[17px] font-semibold tracking-tight">No evaluation results are published yet</h2>
          <p className="mt-1 max-w-[680px] text-[13.5px] leading-relaxed text-[var(--mc-text-2)]">
            The full engine has not been run on clean audio, so there are no scores to show.
          </p>
        </section>
      ) : (
        <>
          <Headline run={run} off={results.ablation_llm_off?.[CLEAN] ?? null} />
          <RuleTable run={run} rules={rules} />
          <Noise results={results} />
        </>
      )}

      <Speed fast={seconds(rowOf('Fast phrase check')?.p50_ms)} deep={seconds(rowOf('Deep language check')?.p50_ms)} runs={data.latency.calls.length} />
      <p className="text-[12.5px] text-[var(--mc-muted)]">
        <a href={NOTES_URL} target="_blank" rel="noopener noreferrer" className="link">
          Limits, method notes and the two worst mistakes: see docs/EVAL-NOTES.md
        </a>
      </p>
    </div>
  )
}

function Card({ label, value, lines }: { label: string; value?: string; lines: string[] }) {
  return (
    <div className="card p-5">
      <div className="lbl">{label}</div>
      {value && <div className="mt-1 text-[34px] font-bold leading-tight tracking-[-0.03em]">{value}</div>}
      <div className={`${value ? '' : 'mt-1.5'} flex flex-col gap-0.5 text-[12.5px] text-[var(--mc-muted)]`}>
        {lines.map((l) => <span key={l}>{l}</span>)}
      </div>
    </div>
  )
}

/** The four headline cards: full engine, clean audio, all calls. */
function Headline({ run, off }: { run: RunResult; off: RunResult | null }) {
  const all = run.all!
  const held = run.held_out ?? null
  const s = all.overall.strict
  const rulesOnly = off?.all?.overall.strict ?? null
  return (
    <section aria-label="Headline scores" className="flex flex-col gap-3">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card label="Violations found" value={f2(s.r)} lines={[`${found(s)} labelled`, 'strict recall']} />
        <Card label="Correct flags" value={f2(s.p)} lines={[`${ratio(s.tp, s.tp + s.fp)} flags`, 'strict precision']} />
        {held ? (
          <Card label="Held-out calls found" value={f2(held.overall.strict.r)} lines={[`${found(held.overall.strict)} labelled`, `recall, ${held.n_calls} calls`]} />
        ) : (
          <Card label="Held-out calls found" lines={['Not in this run.']} />
        )}
        <Card
          label="Language model vs rules only"
          lines={[`With the model: ${found(s)} found`, rulesOnly ? `Rules only: ${found(rulesOnly)} found` : 'Rules only: not run yet']}
        />
      </div>
      <p className="text-[12.5px] text-[var(--mc-muted)]">
        Full engine (rules and language model), clean audio, all {all.n_calls} calls. Strict counts violations and advisories only. A unit is one agent turn and one rule.
      </p>
    </section>
  )
}

/** One table of strict numbers; the toggle shows the same table with needs-review counted as found. */
function RuleTable({ run, rules }: { run: RunResult; rules: Rule[] }) {
  const [withReview, setWithReview] = useState(false)
  const all = run.all!
  const name = (id: string) => rules.find((r) => r.id === id)?.title ?? ''
  const kind = (id: string) => rules.find((r) => r.id === id)?.kind_default ?? 'violation'
  const pick = (b: ScoreBlock): Prf => (withReview ? b.with_review : b.strict)
  const rows: [string, ScoreBlock][] = [...Object.entries(all.per_rule), ['All', all.overall]]
  const th = 'th px-3 py-2.5 text-left'
  return (
    <section className="card overflow-hidden" aria-labelledby="rule-h">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--mc-line)] px-6 py-4">
        <h2 id="rule-h" className="text-base font-semibold">Results by rule</h2>
        <label className="flex items-center gap-2.5 text-[13px] text-[var(--mc-text-2)]">
          Count needs-review as found
          <Switch label="Count needs-review as found" checked={withReview} onChange={setWithReview} />
        </label>
      </div>
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Results by rule (scrolls sideways on narrow screens)">
        <table className="w-full min-w-[640px] border-collapse text-[13.5px] tabular-nums">
          <caption className="sr-only">Found, missed, extra, precision and recall for each rule, {withReview ? 'with needs-review counted as found' : 'strict'}</caption>
          <thead className="bg-[#f9fafb]">
            <tr>
              {['Rule', 'Found', 'Missed', 'Extra', 'Precision', 'Recall'].map((h, i) => (
                <th key={h} scope="col" className={`${th} ${i === 0 ? 'pl-6' : ''}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(([id, b]) => {
              const p = pick(b)
              return (
                <tr key={id} className={`border-t border-[var(--mc-line-soft)] ${id === 'All' ? 'bg-[#f9fafb] font-semibold' : ''}`}>
                  <th scope="row" className="py-3 pl-6 pr-3 text-left font-medium">
                    <span className="flex flex-wrap items-center gap-2">
                      {id === 'All' ? <span>All rules</span> : <span className={`chip chip-${kind(id)} h-[22px] min-w-[34px] justify-center px-2 text-[11px] font-bold`}>{id}</span>}
                      {id !== 'All' && <span className="text-[13px]">{name(id)}</span>}
                    </span>
                  </th>
                  <td className="px-3 py-3">{p.tp}</td>
                  <td className="px-3 py-3">{p.fn}</td>
                  <td className="px-3 py-3">{p.fp}</td>
                  <td className="px-3 py-3" title={p.p === null ? 'No flags, so precision is undefined' : undefined}>{f2(p.p)}</td>
                  <td className="px-3 py-3" title={p.r === null ? 'Nothing labelled, so recall is undefined' : undefined}>{f2(p.r)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {rules
          .filter((r) => r.kind_default === 'needs_review' && all.per_rule[r.id])
          .map((r) => (
            <p key={r.id} className="px-6 pt-3 text-[12.5px] text-[var(--mc-text-2)]">
              {r.id} ({r.title.toLowerCase()}) is a needs-review rule by design, so it has no strict recall; switch the toggle to count its needs-review flags as found.
            </p>
          ))}
        <p className="px-6 py-3 text-[12px] text-[var(--mc-muted)]">
          Full engine, clean audio, all calls. Found, missed and extra are counts of units (one agent turn and one rule). A dash means the score is undefined: nothing was labelled, or nothing flagged, for that rule.
        </p>
      </div>
    </section>
  )
}

/** Recall and precision of the full engine as phone-line noise increases; conditions that were not run are left out. */
function Noise({ results }: { results: EvalResults }) {
  const ids = Object.keys(results.full ?? {})
    .filter((id) => results.full[id]?.all)
    .sort((x, y) => snrOf(y) - snrOf(x))
  if (ids.length === 0) return null
  const strict = (id: string) => results.full[id].all!.overall.strict
  const perRule = (id: string, rule: string) => results.full[id].all!.per_rule[rule]?.strict
  // The explanation is shown only when the saved numbers agree with it: R2 gains extra flags at 10 dB and the model-based rules do not lose recall
  const clean = results.full[CLEAN]?.all
  const r2Clean = perRule(CLEAN, 'R2')
  const r2Noisy = results.full.snr10?.all ? perRule('snr10', 'R2') : undefined
  const modelRulesHold = clean && results.full.snr10?.all && ['R3', 'R4', 'R5'].every((r) => (perRule('snr10', r)?.r ?? 0) >= (perRule(CLEAN, r)?.r ?? 0))
  const explain = !!(r2Clean && r2Noisy && r2Noisy.fp > r2Clean.fp && modelRulesHold)
  return (
    <section className="card flex flex-col gap-3 p-6" aria-labelledby="noise-h">
      <h2 id="noise-h" className="text-base font-semibold">With phone-line noise</h2>
      <p className="-mt-1 text-[12.5px] text-[var(--mc-muted)]">Full engine, all calls, strict. Lower numbers in dB mean more noise.</p>
      <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${ids.length}, minmax(0, 1fr))` }}>
        {ids.map((id) => {
          const s = strict(id)
          return (
            <div key={id} className="flex min-w-0 flex-col gap-1 rounded-xl border border-[var(--mc-line)] p-3.5">
              <span className="lbl">{condLabel(id)}</span>
              <span className="text-[13px] tabular-nums"><b className="text-[22px] tracking-tight">{f2(s.r)}</b> recall</span>
              <span className="text-[12px] text-[var(--mc-muted)]">{found(s)} labelled</span>
              <span className="text-[13px] tabular-nums"><b className="text-[22px] tracking-tight">{f2(s.p)}</b> precision</span>
              <span className="text-[12px] text-[var(--mc-muted)]">{ratio(s.tp, s.tp + s.fp)} flags</span>
            </div>
          )
        })}
      </div>
      {explain && (
        <p className="text-[13px] leading-relaxed text-[var(--mc-text-2)]">
          At 10 dB, R2 raised extra advisory flags because the speech-to-text mis-heard the lender name; R2 has no model step to recover from that. The model-based rules were not affected.
        </p>
      )}
    </section>
  )
}

function Speed({ fast, deep, runs }: { fast: string | null; deep: string | null; runs: number }) {
  if (!fast && !deep) return null
  return (
    <section className="card flex flex-col gap-2 p-6" aria-labelledby="speed-h">
      <h2 id="speed-h" className="text-base font-semibold">Speed</h2>
      <ul className="flex flex-col gap-1 text-[14px]">
        {fast && <li>Fast phrase check: median {fast} to a flag</li>}
        {deep && <li>Deep language check: median {deep} to a flag</li>}
      </ul>
      <p className="text-[12px] text-[var(--mc-muted)]">Read from the {runs} recorded runs, not a fresh measurement.</p>
    </section>
  )
}

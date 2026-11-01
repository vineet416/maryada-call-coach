import { useCallback, useEffect, useState } from 'react'
import { ErrorCard } from '@/components/ErrorCard'
import {
  getEval,
  getRules,
  type EvalExample,
  type EvalPayload,
  type EvalResults,
  type LatencyRow,
  type Prf,
  type Rule,
  type RunResult,
  type Score,
  type ScoreBlock,
  type Unit,
} from '@/lib/api'

type Engine = 'ablation_llm_off' | 'full'
type Group = 'all' | 'tune' | 'held_out' | 'seen_in_development'

const ENGINES: { id: Engine; label: string; short: string }[] = [
  { id: 'ablation_llm_off', label: 'Rules only, no language model', short: 'Rules only' },
  { id: 'full', label: 'Full engine (rules and language model)', short: 'Full engine' },
]
const CONDITIONS = [
  { id: 'clean', label: 'Clean audio' },
  { id: 'snr10', label: '10 dB noise' },
  { id: 'snr20', label: '20 dB noise' },
  { id: 'snr5', label: '5 dB noise' },
]
const GROUPS: { id: Group; label: string; note: string }[] = [
  { id: 'all', label: 'All calls', note: 'Every labelled call, pooled.' },
  { id: 'tune', label: 'Tuning calls', note: 'The calls the phrase lists and prompt were developed on.' },
  { id: 'held_out', label: 'Held-out calls', note: 'Calls that were never run through the engine during development. Reported apart from tuning.' },
  { id: 'seen_in_development', label: 'Seen in development', note: 'Held-out calls that were run through the engine while building, so they are not unbiased.' },
]

/** Lower-case a leading capital only ("Clean audio" -> "clean audio", "10 dB noise" unchanged). */
const lc = (s: string) => s.replace(/^[A-Z](?=[a-z])/, (m) => m.toLowerCase())
const f2 = (x: number | null) => (x === null ? '–' : x.toFixed(2))
const ratio = (num: number, den: number) => `${num} of ${den}`
const SOURCE: Record<string, string> = { prefilter: 'phrase check', llm: 'language model', both: 'phrase check and language model', gate: 'rule check' }
const dateOf = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
const seconds = (ms: number | null) => (ms === null ? '–' : `${(ms / 1000).toFixed(1)} s`)

export function Evaluation() {
  const [data, setData] = useState<EvalPayload | null>(null)
  const [rules, setRules] = useState<Rule[]>([])
  const [error, setError] = useState<string | null>(null)
  const [engine, setEngine] = useState<Engine | null>(null)
  const [cond, setCond] = useState<string | null>(null)
  const [group, setGroup] = useState<Group>('all')

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

  const results = data?.results ?? null
  const ran = (e: Engine) => CONDITIONS.filter((c) => results?.[e]?.[c.id]).map((c) => c.id)
  // Default view: the full engine on clean audio as soon as the full engine has results; else the rules-only baseline.
  const eng: Engine = engine ?? (ran('full').length ? 'full' : 'ablation_llm_off')
  const available = ran(eng)
  const cd = cond ?? (available.includes('clean') ? 'clean' : (available[0] ?? 'clean'))
  const run = results?.[eng]?.[cd] ?? null

  if (error) return <ErrorCard message={error} onRetry={load} />
  if (!data) {
    return (
      <div className="space-y-5" aria-busy="true" aria-label="Loading the evaluation">
        <div className="skeleton h-16" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-28" />)}
        </div>
        <div className="skeleton h-80" />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[28px] font-bold tracking-[-0.025em]">Evaluation</h1>
          <p className="mt-0.5 max-w-[720px] text-sm text-[var(--mc-muted)]">
            How well Maryada finds rule violations in the labelled synthetic calls{results ? ` (${results.n_calls})` : ''}. Every number below is read from the saved results file; counts are shown next to each score.
          </p>
        </div>
        {results && (
          <span className="chip chip-warn" title="Saved results, not a live run">
            Results saved {dateOf(results.generated_at)}
          </span>
        )}
      </div>

      {!results ? (
        <section className="card p-6" role="status">
          <h2 className="text-[17px] font-semibold tracking-tight">No evaluation results are published yet</h2>
          <p className="mt-1 max-w-[680px] text-[13.5px] leading-relaxed text-[var(--mc-text-2)]">
            The evaluation has not been run, so there are no scores to show. The latency card below still reads the saved call recordings.
          </p>
        </section>
      ) : (
        <>
          <Coverage results={results} />
          <RunPicker results={results} eng={eng} cond={cd} setEngine={setEngine} setCond={setCond} />
          {run ? (
            <RunView run={run} results={results} rules={rules} group={group} setGroup={setGroup} eng={eng} cond={cd} />
          ) : (
            <section className="card p-6" role="status">
              <h2 className="text-[17px] font-semibold tracking-tight">Not run yet</h2>
              <p className="mt-1 text-[13.5px] text-[var(--mc-text-2)]">
                {ENGINES.find((e) => e.id === eng)?.label} on {lc(CONDITIONS.find((c) => c.id === cd)?.label ?? '')} has not been run, so there are no numbers to show for it.
                There are also no errors to show under “Where it went wrong” for this selection. Pick a run that has results above.
              </p>
            </section>
          )}
          <div className="flex flex-wrap items-start gap-5">
            <Ablation results={results} />
            <Noise results={results} eng={eng} />
          </div>
        </>
      )}

      <div className="flex flex-wrap items-start gap-5">
        <Latency rows={data.latency.rows} calls={data.latency.calls} method={data.latency.method} />
        {results && <Limits results={results} />}
      </div>
    </div>
  )
}

/** What has and has not been run, in plain words. */
function Coverage({ results }: { results: EvalResults }) {
  return (
    <section className="card border-[var(--mc-accent-ring)] bg-[#f8f8ff] p-5" aria-labelledby="cov-h">
      <h2 id="cov-h" className="text-[15px] font-semibold text-[var(--mc-accent-dark)]">What has been run</h2>
      <ul className="mt-2 grid gap-x-8 gap-y-1.5 text-[13.5px] sm:grid-cols-2">
        {ENGINES.map((e) =>
          CONDITIONS.map((c) => {
            const r = results[e.id]?.[c.id]
            return (
              <li key={`${e.id}-${c.id}`} className="flex items-baseline justify-between gap-3 border-b border-[var(--mc-line)] py-1">
                <span>{e.short}, {lc(c.label)}</span>
                <span className={r ? 'font-semibold' : 'text-[var(--mc-muted)]'}>
                  {r ? `${r.calls_run} of ${results.n_calls} calls${r.complete ? '' : ' (incomplete)'}` : 'Not run yet'}
                </span>
              </li>
            )
          }),
        )}
      </ul>
    </section>
  )
}

function RunPicker({ results, eng, cond, setEngine, setCond }: {
  results: EvalResults
  eng: Engine
  cond: string
  setEngine: (e: Engine) => void
  setCond: (c: string) => void
}) {
  const btn = (on: boolean, ran: boolean) =>
    `chip cursor-pointer ${on ? '!border-[var(--mc-accent)] !bg-[var(--mc-accent)] !font-semibold !text-white' : ran ? 'hover:bg-[var(--mc-line-soft)]' : 'border-dashed text-[var(--mc-muted)]'}`
  return (
    <div className="flex flex-col gap-3">
      <div role="group" aria-label="Engine" className="flex flex-wrap gap-2">
        {ENGINES.map((e) => {
          const ran = CONDITIONS.some((c) => results[e.id]?.[c.id])
          return (
            <button key={e.id} type="button" aria-pressed={eng === e.id} onClick={() => setEngine(e.id)} className={btn(eng === e.id, ran)}>
              {e.label}{ran ? '' : ' · not run yet'}
            </button>
          )
        })}
      </div>
      <div role="group" aria-label="Audio condition" className="flex flex-wrap gap-2">
        {CONDITIONS.map((c) => {
          const ran = Boolean(results[eng]?.[c.id])
          return (
            <button key={c.id} type="button" aria-pressed={cond === c.id} onClick={() => setCond(c.id)} className={btn(cond === c.id, ran)}>
              {c.label}{ran ? '' : ' · not run yet'}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function Stat({ label, prf, kind, note }: { label: string; prf: Prf; kind: 'r' | 'p'; note: string }) {
  const value = kind === 'r' ? prf.r : prf.p
  const num = prf.tp
  const den = kind === 'r' ? prf.tp + prf.fn : prf.tp + prf.fp
  return (
    <div className="card p-5">
      <div className="lbl">{label}</div>
      <div className="mt-1 text-[34px] font-bold leading-tight tracking-[-0.03em]">{f2(value)}</div>
      <div className="text-[12.5px] text-[var(--mc-muted)]">
        {den ? ratio(num, den) : 'nothing to measure'} · {note}
      </div>
    </div>
  )
}

function RunView({ run, results, rules, group, setGroup, eng, cond }: {
  run: RunResult
  results: EvalResults
  rules: Rule[]
  group: Group
  setGroup: (g: Group) => void
  eng: Engine
  cond: string
}) {
  const score: Score | null = run[group] ?? null
  const held = run.held_out ?? null
  const all = run.all ?? null
  const name = (id: string) => rules.find((r) => r.id === id)?.title ?? ''
  // chip tone and the needs-review label come from the rulebook (/api/rules), not from this page
  const kind = (id: string) => rules.find((r) => r.id === id)?.kind_default ?? 'violation'
  return (
    <>
      {all ? (
        <>
          <section aria-label="Headline scores" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Violations found" prf={all.overall.strict} kind="r" note="labelled units, strict" />
            <Stat label="Flags that were correct" prf={all.overall.strict} kind="p" note="flags, strict" />
            <Stat label="Found, counting needs review" prf={all.overall.with_review} kind="r" note="labelled units" />
            {held ? (
              <Stat label={`Held-out calls (${held.n_calls})`} prf={held.overall.strict} kind="r" note="labelled units, strict" />
            ) : (
              <div className="card p-5"><div className="lbl">Held-out calls</div><div className="mt-1 text-[13px] text-[var(--mc-muted)]">Not in this run.</div></div>
            )}
          </section>
          <p className="-mt-3 text-[12.5px] text-[var(--mc-muted)]">
            All headline cards: {ENGINES.find((e) => e.id === eng)?.label.toLowerCase()}, {lc(CONDITIONS.find((c) => c.id === cond)?.label ?? '')}, {all.n_calls} calls.
            Strict counts violations and advisories only. A unit is one agent turn and one rule.
          </p>
        </>
      ) : (
        <p role="status" className="card p-5 text-[13.5px] text-[var(--mc-muted)]">This run has no combined scores, so the headline cards are left out. The groups below show what exists.</p>
      )}

      <section className="card overflow-hidden" aria-labelledby="rule-h">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--mc-line)] px-6 py-4">
          <h2 id="rule-h" className="text-base font-semibold">Results by rule</h2>
          <div role="group" aria-label="Which calls" className="flex flex-wrap gap-2">
            {GROUPS.map((g) => {
              const s = run[g.id] ?? null
              return (
                <button key={g.id} type="button" disabled={!s} aria-pressed={group === g.id} onClick={() => setGroup(g.id)} title={g.note}
                  className={`chip cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 ${group === g.id ? '!border-[var(--mc-accent)] !bg-[var(--mc-accent)] !font-semibold !text-white' : 'hover:bg-[var(--mc-line-soft)]'}`}>
                  {g.label} · {s ? `${s.n_calls} calls` : 'none'}
                </button>
              )
            })}
          </div>
        </div>
        <p className="border-b border-[var(--mc-line-soft)] px-6 py-2 text-[12.5px] text-[var(--mc-muted)]">{GROUPS.find((g) => g.id === group)?.note}</p>
        {score ? <RuleTable score={score} name={name} kind={kind} /> : <p className="p-6 text-sm text-[var(--mc-muted)]">No calls from this group are in this run.</p>}
      </section>

      <Examples examples={run.examples ?? []} kind={kind} />
      {all && <PerCall score={all} />}
      <p className="text-[12px] text-[var(--mc-muted)]">
        {[
          results.model_info?.llm && `Model: ${results.model_info.llm}`,
          results.model_info?.stt && `speech: ${results.model_info.stt}`,
          results.model_info?.thresholds && `thresholds ${results.model_info.thresholds.violation} (violation) and ${results.model_info.thresholds.needs_review} (needs review)`,
          results.labels_hash && `labels ${results.labels_hash}`,
        ].filter(Boolean).join(' · ')}
      </p>
    </>
  )
}

function RuleTable({ score, name, kind }: { score: Score; name: (id: string) => string; kind: (id: string) => string }) {
  const rows: [string, ScoreBlock][] = [...Object.entries(score.per_rule), ['All', score.overall]]
  const th = 'th px-3 py-2.5 text-left'
  return (
    <div className="overflow-x-auto" tabIndex={0} role="region" aria-label="Results by rule (scrolls sideways on narrow screens)">
      <table className="w-full min-w-[920px] border-collapse text-[13.5px] tabular-nums">
        <caption className="sr-only">Precision, recall and counts for each rule, strict and with needs review counted</caption>
        <thead className="bg-[#f9fafb]">
          <tr>
            <th scope="col" rowSpan={2} className={`${th} pl-6`}>Rule</th>
            <th scope="colgroup" colSpan={4} className={`${th} border-l border-[var(--mc-line)]`}>Strict (violation and advisory)</th>
            <th scope="colgroup" colSpan={4} className={`${th} border-l border-[var(--mc-line)]`}>With needs review counted</th>
            <th scope="col" rowSpan={2} className={`${th} border-l border-[var(--mc-line)]`}>Needs review<br />on / off label</th>
          </tr>
          <tr>
            {['Precision', 'Recall', 'F1', 'Found / missed / extra'].map((h) => <th key={`s${h}`} scope="col" className={`${th} ${h === 'Precision' ? 'border-l border-[var(--mc-line)]' : ''}`}>{h}</th>)}
            {['Precision', 'Recall', 'F1', 'Found / missed / extra'].map((h) => <th key={`w${h}`} scope="col" className={`${th} ${h === 'Precision' ? 'border-l border-[var(--mc-line)]' : ''}`}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map(([id, b]) => (
            <tr key={id} className={`border-t border-[var(--mc-line-soft)] ${id === 'All' ? 'bg-[#f9fafb] font-semibold' : ''}`}>
              <th scope="row" className="py-3 pl-6 pr-3 text-left font-medium">
                <span className="flex flex-wrap items-center gap-2">
                  {id === 'All' ? <span>All rules</span> : <span className={`chip chip-${kind(id)} h-[22px] min-w-[34px] justify-center px-2 text-[11px] font-bold`}>{id}</span>}
                  {id !== 'All' && <span className="text-[13px]">{name(id)}</span>}
                  {kind(id) === 'needs_review' && <span className="chip chip-needs_review h-5 text-[11px]">needs-review rule</span>}
                </span>
              </th>
              <Cells prf={b.strict} first />
              <Cells prf={b.with_review} first />
              <td className="border-l border-[var(--mc-line)] px-3 py-3">{b.needs_review.on_label} / {b.needs_review.off_label}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="px-6 py-3 text-[12px] text-[var(--mc-muted)]">
        A dash means the score is undefined: there was nothing labelled, or nothing flagged, for that rule.
        Found / missed / extra = true positives / false negatives / false positives, in units.
      </p>
    </div>
  )
}

function Cells({ prf, first }: { prf: Prf; first?: boolean }) {
  const dash = (v: number | null, why: string) => <span title={v === null ? why : undefined}>{f2(v)}</span>
  return (
    <>
      <td className={`px-3 py-3 ${first ? 'border-l border-[var(--mc-line)]' : ''}`}>{dash(prf.p, 'No flags, so precision is undefined')}</td>
      <td className="px-3 py-3">{dash(prf.r, 'Nothing labelled, so recall is undefined')}</td>
      <td className="px-3 py-3 font-semibold">{dash(prf.f1, 'Undefined')}</td>
      <td className="px-3 py-3">{prf.tp} / {prf.fn} / {prf.fp}</td>
    </>
  )
}

const unitText = (u: Unit) => `turn ${u[1]} ${u[2]}`

function Examples({ examples, kind }: { examples: EvalExample[]; kind: (id: string) => string }) {
  if (!examples.length) return null
  return (
    <section className="card flex flex-col gap-4 p-6" aria-labelledby="ex-h">
      <h2 id="ex-h" className="text-base font-semibold">Where it went wrong</h2>
      <p className="-mt-2 text-[13px] text-[var(--mc-muted)]">Real errors from this run, with the turn as the speech service heard it. Counted against the score; nothing was adjusted.</p>
      <div className="grid gap-4 lg:grid-cols-2">
        {examples.map((e) => (
          <div key={`${e.call}-${e.turn}-${e.rule}`} className="flex flex-col gap-2 rounded-xl border border-[var(--mc-line)] p-4">
            <div className="flex flex-wrap items-center gap-2 text-[13px]">
              <b>{e.call.toUpperCase()}</b> <span className="text-[var(--mc-muted)]">agent turn {e.turn}</span>
              <span className={`chip chip-${kind(e.rule)} h-5 text-[11px]`}>{e.rule}</span>
              <span className="chip h-5 text-[11px]">{e.type === 'miss' ? 'Missed' : 'Extra flag'}</span>
            </div>
            <p lang="hi" className="rounded-lg bg-[var(--mc-advisory-tint)] px-3 py-2 text-[14px] leading-relaxed">{e.text}</p>
            <p className="text-[13px] leading-relaxed text-[var(--mc-text-2)]">
              {e.type === 'miss'
                ? `The script labels ${e.rule} here (“${e.labelled_phrase ?? 'whole turn'}”), but the engine raised nothing for this rule on this turn.`
                : e.detection
                  ? `The engine raised ${e.rule} as ${e.detection.kind.replace('_', ' ')} at confidence ${e.detection.confidence.toFixed(2)} from “${e.detection.quote}” (${SOURCE[e.detection.source] ?? e.detection.source}), but the script labels nothing here.`
                  : 'The engine raised a flag the script does not label.'}
            </p>
          </div>
        ))}
      </div>
    </section>
  )
}

function PerCall({ score }: { score: Score }) {
  return (
    <details className="card p-0">
      <summary className="cursor-pointer px-6 py-4 text-base font-semibold">Every call: found, missed, extra ({score.n_calls} calls)</summary>
      <div className="overflow-x-auto border-t border-[var(--mc-line-soft)]" tabIndex={0} role="region" aria-label="Per call outcomes (scrolls sideways on narrow screens)">
        <table className="w-full min-w-[720px] border-collapse text-[13px]">
          <caption className="sr-only">Per call outcomes</caption>
          <thead className="bg-[#f9fafb]">
            <tr>{['Call', 'Labelled', 'Found (strict)', 'Found only as needs review', 'Missed', 'Extra flags'].map((h) => <th key={h} scope="col" className="th px-3 py-2.5 text-left first:pl-6">{h}</th>)}</tr>
          </thead>
          <tbody>
            {score.per_call.map((c) => {
              const review = c.hit_with_review.filter((u) => !c.hit.some((h) => h[1] === u[1] && h[2] === u[2]))
              const list = (us: Unit[]) => (us.length ? us.map(unitText).join(', ') : '–')
              return (
                <tr key={c.call_id} className="border-t border-[var(--mc-line-soft)] align-top">
                  <th scope="row" className="py-2.5 pl-6 pr-3 text-left font-semibold">{c.call_id.toUpperCase()}{c.hard_negative ? ' · hard negative' : ''}</th>
                  <td className="px-3 py-2.5">{list(c.expected)}</td>
                  <td className="px-3 py-2.5">{list(c.hit)}</td>
                  <td className="px-3 py-2.5">{list(review)}</td>
                  <td className="px-3 py-2.5">{list(c.missed_with_review)}</td>
                  <td className="px-3 py-2.5">{list(c.false_alarms_with_review)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <p className="px-6 py-3 text-[12px] text-[var(--mc-muted)]">“Missed” is missed even when needs review is counted. “Extra flags” include needs-review items.</p>
      </div>
    </details>
  )
}

function Ablation({ results }: { results: EvalResults }) {
  const off = results.ablation_llm_off?.clean
  const on = results.full?.clean
  const row = (label: string, r?: RunResult) => {
    const s = r?.all?.overall?.strict
    return (
      <div className="flex flex-col gap-1.5">
        <div className="flex items-baseline justify-between gap-3 text-[13px]">
          <span>{label}</span>
          {s ? <b>{f2(s.r)} <span className="font-normal text-[var(--mc-muted)]">({ratio(s.tp, s.tp + s.fn)})</span></b> : <span className="text-[var(--mc-muted)]">Not run yet</span>}
        </div>
        <div className="h-2.5 overflow-hidden rounded-full bg-[#f2f4f7]" aria-hidden>
          {s?.r != null && <div className="h-full rounded-full bg-[var(--mc-accent)]" style={{ width: `${Math.round(s.r * 100)}%` }} />}
        </div>
      </div>
    )
  }
  return (
    <section className="card flex min-w-[300px] flex-[1_1_340px] flex-col gap-3 p-6" aria-labelledby="abl-h">
      <h2 id="abl-h" className="text-base font-semibold">With and without the language model</h2>
      {row('Rules only', off)}
      {row('Rules and language model', on)}
      <p className="text-[12px] text-[var(--mc-muted)]">
        Strict recall on clean audio, all calls: labelled units found.{' '}
        {on?.all && off?.all ? `The language model changes the number found from ${off.all.overall.strict.tp} to ${on.all.overall.strict.tp} of ${on.all.overall.strict.tp + on.all.overall.strict.fn}.` : 'The full engine has not been run, so there is nothing to compare yet.'}
      </p>
    </section>
  )
}

function Noise({ results, eng }: { results: EvalResults; eng: Engine }) {
  return (
    <section className="card flex min-w-[300px] flex-[2_1_480px] flex-col gap-3 p-6" aria-labelledby="noise-h">
      <h2 id="noise-h" className="text-base font-semibold">Noise robustness</h2>
      <p className="-mt-1 text-[12.5px] text-[var(--mc-muted)]">Strict recall for {ENGINES.find((e) => e.id === eng)?.label.toLowerCase()}, all calls, as phone-line noise increases.</p>
      <div className="grid grid-cols-4 gap-3">
        {CONDITIONS.map((c) => {
          const s = results[eng]?.[c.id]?.all?.overall?.strict
          return (
            <div key={c.id} className="flex flex-col items-center gap-1.5">
              <div className="flex h-[120px] w-full items-end justify-center border-b border-[var(--mc-line)]" aria-hidden>
                {s?.r != null ? (
                  <div className="w-full max-w-[64px] rounded-t-lg bg-[var(--mc-accent)]" style={{ height: `${Math.max(2, Math.round(s.r * 110))}px` }} />
                ) : (
                  <div className="h-[110px] w-full max-w-[64px] rounded-t-lg border border-dashed border-[var(--mc-field)]" />
                )}
              </div>
              <b className="text-[13px] tabular-nums">{s ? f2(s.r) : '–'}</b>
              <span className="text-center text-[11.5px] text-[var(--mc-muted)]">{c.label}<br />{s ? ratio(s.tp, s.tp + s.fn) : 'not run yet'}</span>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function Latency({ rows, calls, method }: { rows: LatencyRow[]; calls: string[]; method: string }) {
  return (
    <section className="card flex min-w-[300px] flex-[1_1_380px] flex-col gap-3 p-6" aria-labelledby="lat-h">
      <h2 id="lat-h" className="text-base font-semibold">Time to flag</h2>
      <p className="-mt-1 text-[12.5px] text-[var(--mc-muted)]">
        Computed from the {calls.length} saved call recordings ({calls.map((c) => c.toUpperCase()).join(', ')}). These are small samples; n is the number of flags behind each row. Recorded runs, not a fresh measurement.
      </p>
      <div className="overflow-hidden rounded-xl border border-[var(--mc-line)]">
        <table className="w-full border-collapse text-[13.5px] tabular-nums">
          <caption className="sr-only">Time to flag: median and 95th percentile with the number of flags</caption>
          <thead className="bg-[#f9fafb]">
            <tr>{['Check', 'n', 'p50', 'p95'].map((h) => <th key={h} scope="col" className="th px-3.5 py-2.5 text-left">{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label} className="border-t border-[var(--mc-line-soft)]">
                <th scope="row" className="px-3.5 py-2.5 text-left font-normal">{r.label}</th>
                <td className="px-3.5 py-2.5">{r.n}</td>
                <td className="px-3.5 py-2.5 font-semibold">{seconds(r.p50_ms)}</td>
                <td className="px-3.5 py-2.5 font-semibold">{seconds(r.p95_ms)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[12px] text-[var(--mc-muted)]">{method}</p>
    </section>
  )
}

function Limits({ results }: { results: EvalResults }) {
  return (
    <section className="card flex min-w-[300px] flex-[1_1_380px] flex-col gap-3 p-6" aria-labelledby="lim-h">
      <h2 id="lim-h" className="text-base font-semibold">Honest limits</h2>
      <ul className="flex list-disc flex-col gap-2 pl-5 text-[13.5px] leading-relaxed text-[var(--mc-text-2)]">
        {(results.limits ?? []).map((l) => <li key={l}>{l}</li>)}
      </ul>
      {(results.label_changes ?? []).map((c) => (
        <p key={`${c.call}-${c.turn}-${c.rule}`} className="rounded-lg bg-[var(--mc-advisory-tint)] px-3 py-2 text-[12.5px] leading-relaxed text-[var(--mc-advisory-ink)]">
          Label changed after the first run: {c.rule} {c.action} on {c.call.toUpperCase()} turn {c.turn} ({c.changed_on}; labels {c.label_hash_before} to {c.label_hash_after}). {c.reason}
        </p>
      ))}
    </section>
  )
}

import { usePageTitle } from '@/lib/usePageTitle'
import { ChevronRight, Gauge, Headset, Mic, ShieldCheck, TextAlignStart } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { getEval, getRules, type EvalPayload, type Rule } from '@/lib/api'
import { KIND_LABEL, type Kind } from '@/lib/events'

const LANGUAGE_NAME: Record<string, string> = { hi: 'Hindi', en: 'English', mr: 'Marathi' }

/** Median seconds for a time-to-flag row, from the saved recordings (null when unknown). */
const median = (p: EvalPayload | null, label: string): string | null => {
  const ms = p?.latency.rows.find((r) => r.label === label)?.p50_ms
  return ms == null ? null : `${(ms / 1000).toFixed(1)} s`
}
const joinNames = (names: string[]) => (names.length > 1 ? `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}` : (names[0] ?? ''))

function steps(p: EvalPayload | null) {
  const fast = median(p, 'Fast phrase check')
  const deep = median(p, 'Deep language check')
  return [
    { icon: Mic, title: '1. Call audio', text: 'The agent and borrower speak. Audio streams in turn by turn.' },
    {
      icon: TextAlignStart,
      title: '2. Speech to text',
      text: 'Gnani Prisma turns Indian-language speech, including Hindi and English mixed together, into a live transcript.',
    },
    {
      icon: ShieldCheck,
      title: '3. Rule check',
      text: `A fast phrase check flags first${fast ? `, in a median of ${fast}` : ''}. A deep language check confirms${deep ? ` in a median of ${deep}` : ' afterwards'}${fast || deep ? ' (from the recorded runs)' : ''}.`,
    },
    { icon: Gauge, title: '4. Risk score', text: 'Each finding adds to a 0 to 100 meter. Clean turns bring it down.' },
    { icon: Headset, title: '5. Coach voice', text: 'A short spoken nudge plays in the agent headset at the next pause.', last: true },
  ]
}

function models(p: EvalPayload | null) {
  const fast = median(p, 'Fast phrase check')
  const deep = median(p, 'Deep language check')
  const names = (p?.languages ?? []).map((c) => LANGUAGE_NAME[c] ?? c)
  return [
    {
      task: 'Speech to text',
      how: 'Gnani Prisma V3.0',
      note: `Indian-language speech, language detected automatically.${names.length ? ` Tested here on ${joinNames(names)} calls.` : ''} Your Gnani key.`,
    },
    {
      task: 'Fast phrase check',
      how: 'Rules and phrase lists, no model',
      note: `${fast ? `Median ${fast} to flag in the recorded runs. ` : ''}R1 (calling hours) and R2 (identification and recording notice) are also decided here, by fixed rules.`,
    },
    {
      task: 'Deep rule check',
      how: 'The language model you choose',
      note: `${deep ? `Median ${deep} to flag in the recorded runs. ` : ''}Tuned on gpt-5.4-mini; other models vary.`,
    },
    {
      task: 'Coach voice and call audio',
      how: 'Gnani Timbre V3.0',
      note: 'Recorded in advance, so recorded runs play with no keys.',
    },
  ]
}

const LEGEND: { kind: Kind; text: string }[] = [
  { kind: 'violation', text: 'a clear breach of a rule' },
  { kind: 'advisory', text: 'worth a second look' },
  { kind: 'needs_review', text: 'the checker is not sure' },
  { kind: 'good_practice', text: 'what a good call sounds like' },
]

export function HowItWorks() {
  usePageTitle('How it works · Maryada')
  const [rules, setRules] = useState<Rule[] | null>(null)
  const [failed, setFailed] = useState(false)
  const [facts, setFacts] = useState<EvalPayload | null>(null)
  useEffect(() => {
    const ctl = new AbortController()
    getRules(ctl.signal)
      .then(setRules)
      .catch((e: Error) => e.name !== 'AbortError' && setFailed(true))
    getEval(ctl.signal)
      .then(setFacts)
      .catch(() => undefined) // the measured times and languages are left out when they cannot be read
    return () => ctl.abort()
  }, [])

  return (
    <div className="flex flex-col gap-10">
      <div className="flex max-w-[760px] flex-col gap-2.5">
        <h1 className="text-[28px] font-bold leading-[1.15] tracking-[-0.025em] sm:text-[34px]">A compliance coach that listens while the agent talks</h1>
        <p className="text-base leading-[1.65] text-[#475467]">
          Maryada listens to a recovery call, checks every agent sentence against RBI-style conduct rules, and whispers a short correction to the agent before the next sentence. The borrower never hears it.
        </p>
      </div>

      <section aria-labelledby="flow-h" className="flex flex-col gap-3.5">
        <h2 id="flow-h" className="text-lg font-semibold tracking-tight">From voice to coaching in seconds</h2>
        <ol className="flex flex-wrap items-stretch gap-2.5">
          {steps(facts).map(({ icon: Icon, title, text, last }, i, all) => (
            <li key={title} className="contents">
              <div
                className={`card flex min-w-[200px] flex-[1_1_200px] flex-col gap-2.5 p-[18px] ${last ? '!border-[var(--mc-accent-ring)] !bg-[#f8f8ff]' : ''}`}
              >
                <span className={`flex h-[34px] w-[34px] items-center justify-center rounded-[10px] ${last ? 'bg-[var(--mc-accent)] text-white' : 'bg-[var(--mc-accent-tint)] text-[var(--mc-accent)]'}`}>
                  <Icon className="h-[18px] w-[18px]" aria-hidden />
                </span>
                <h3 className="text-[15px] font-semibold">{title}</h3>
                <p className="text-[13px] leading-normal text-[var(--mc-muted)]">{text}</p>
              </div>
              {i < all.length - 1 && (
                <span className="hidden items-center text-[#667085] xl:flex" aria-hidden>
                  <ChevronRight className="h-5 w-5" />
                </span>
              )}
            </li>
          ))}
        </ol>
      </section>

      <section className="flex flex-wrap items-stretch gap-5">
        <div className="card flex flex-[1_1_480px] flex-col gap-3.5 p-6">
          <h2 className="text-lg font-semibold tracking-tight">How to read the transcript</h2>
          <ul className="flex flex-col gap-2 rounded-xl bg-[#f6f7fb] px-4 py-3.5 text-[15px] leading-loose">
            {LEGEND.map((l) => (
              <li key={l.kind}>
                <span className={`tok tok-${l.kind}`}>{KIND_LABEL[l.kind]}</span> <span className="text-[13px] text-[var(--mc-muted)]">· {l.text}</span>
              </li>
            ))}
          </ul>
          <p className="text-[13.5px] leading-[1.65] text-[#475467]">
            Tap any underlined phrase to see the rule, why it was flagged, and a better way to say it. Colour is never the only signal: each style also has its own underline.
          </p>
        </div>
        <div className="card flex flex-[1_1_380px] flex-col gap-3.5 p-6">
          <h2 className="text-lg font-semibold tracking-tight">What the coach does and does not do</h2>
          <ul className="flex flex-col gap-2.5 text-[13.5px] leading-relaxed text-[var(--mc-text-2)]">
            <Item ok>Speaks only to the agent, in a calm one-line nudge.</Item>
            <Item ok>Names the rule and offers a safer way to continue.</Item>
            <Item>Does not give legal advice or decide who is at fault.</Item>
            <Item>Does not store your keys, and the demo uses synthetic calls only.</Item>
          </ul>
        </div>
      </section>

      <TableCard title="Which model does what" aside="Live calls use your keys. Recorded runs use none.">
        <Grid cols="1.6fr 2.2fr 3fr" head={['Task', 'Model or method', 'Notes']} />
        {models(facts).map((m) => (
          <Grid key={m.task} cols="1.6fr 2.2fr 3fr" row={[<b key="t" className="font-semibold">{m.task}</b>, m.how, <span key="n" className="text-[#475467]">{m.note}</span>]} />
        ))}
      </TableCard>

      <TableCard title="The rulebook" aside="Illustrative rules for a synthetic demo. Not legal advice.">
        <Grid cols=".7fr 2fr 4fr 1fr" head={['Rule', 'Name', 'What it looks for', 'Kind']} />
        {rules?.map((r) => {
          const kind = (r.kind_default in KIND_LABEL ? r.kind_default : 'violation') as Kind
          return (
            <Grid
              key={r.id}
              cols=".7fr 2fr 4fr 1fr"
              row={[
                <span key="i" className={`chip chip-${kind} w-[42px] justify-center px-0`}>{r.id}</span>,
                <b key="n" className="font-semibold">{r.title}</b>,
                <span key="s" className="text-[#475467]">{r.summary}</span>,
                <span key="k" className="text-[12.5px] text-[var(--mc-muted)]">{KIND_LABEL[kind]}</span>,
              ]}
            />
          )
        })}
        {!rules && !failed && <div className="skeleton m-4 h-24" aria-busy="true" aria-label="Loading rules" />}
        {failed && <p role="status" className="px-6 py-5 text-sm text-[var(--mc-muted)]">The rulebook could not be loaded. Check your connection and reload the page.</p>}
      </TableCard>

      <section className="card flex flex-wrap items-center justify-between gap-6 !border-[var(--mc-accent-ring)] !bg-[#f8f8ff] p-6">
        <div className="max-w-[720px]">
          <div className="lbl text-[var(--mc-accent-dark)]">Next</div>
          <p className="mt-1 text-[15px] font-medium text-[var(--mc-text-2)]">Upload is coming soon.</p>
        </div>
        <Link to="/" className="btn btn-lg btn-primary">Try the featured call</Link>
      </section>
    </div>
  )
}

function Item({ ok = false, children }: { ok?: boolean; children: ReactNode }) {
  return (
    <li className="flex gap-2.5">
      <span aria-hidden className={`font-bold ${ok ? 'text-[var(--mc-good-practice-ink)]' : 'text-[var(--mc-violation-ink)]'}`}>{ok ? '✓' : '✕'}</span>
      <span>
        <span className="sr-only">{ok ? 'Does: ' : 'Does not: '}</span>
        {children}
      </span>
    </li>
  )
}

function TableCard({ title, aside, children }: { title: string; aside: string; children: ReactNode }) {
  return (
    <section className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#eaecf0] px-5 py-[18px] sm:px-6">
        <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
        <span className="text-xs text-[var(--mc-muted)]">{aside}</span>
      </div>
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label={title}>
        <div className="min-w-[760px]" role="table" aria-label={`${title} table`}>{children}</div>
      </div>
    </section>
  )
}

function Grid({ cols, head, row }: { cols: string; head?: string[]; row?: ReactNode[] }) {
  const style = { gridTemplateColumns: cols }
  if (head)
    return (
      <div role="row" className="grid gap-4 border-b border-[#eaecf0] bg-[#f9fafb] px-6 py-2.5" style={style}>
        {head.map((h) => (
          <span key={h} role="columnheader" className="th">{h}</span>
        ))}
      </div>
    )
  return (
    <div role="row" className="grid items-center gap-4 border-b border-[var(--mc-line-soft)] px-6 py-3.5 text-[13.5px] last:border-0" style={style}>
      {row?.map((c, i) => (
        <span key={i} role="cell">{c}</span>
      ))}
    </div>
  )
}
